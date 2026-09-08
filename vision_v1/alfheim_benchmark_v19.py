from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

import alfheim_benchmark_v9 as v9
import alfheim_benchmark_v10 as v10
from alfheim_benchmark import load_truth, truth_at
from alfheim_benchmark_v7 import summarize_physical

NATIVE_START = v9.NATIVE_START
TARGET_IDS = v9.TARGET_IDS
CAL_SPLIT = 3.0


def box_iou(a, b):
    a=np.asarray(a,float);b=np.asarray(b,float)
    x1=max(a[0],b[0]);y1=max(a[1],b[1]);x2=min(a[2],b[2]);y2=min(a[3],b[3])
    inter=max(0.,x2-x1)*max(0.,y2-y1)
    aa=max(0.,a[2]-a[0])*max(0.,a[3]-a[1]);bb=max(0.,b[2]-b[0])*max(0.,b[3]-b[1])
    return inter/max(1e-6,aa+bb-inter)


def cosdist(a,b):
    a=np.asarray(a,float);b=np.asarray(b,float)
    na=np.linalg.norm(a);nb=np.linalg.norm(b)
    if na<1e-8 or nb<1e-8:return 1.0
    return float(1.0-np.dot(a,b)/(na*nb))


def clip_box(b,w,h):
    b=np.asarray(b,float).copy()
    b[[0,2]]=np.clip(b[[0,2]],0,w-1);b[[1,3]]=np.clip(b[[1,3]],0,h-1)
    if b[2]-b[0]<4 or b[3]-b[1]<9:return None
    return b


def foot_of(b):
    b=np.asarray(b,float)
    return np.asarray([(b[0]+b[2])/2.0,b[3]],float)


def seed_points(gray,bbox,max_corners=45):
    h,w=gray.shape[:2];b=clip_box(bbox,w,h)
    if b is None:return np.empty((0,1,2),np.float32)
    x1,y1,x2,y2=b
    # Keep features near the player body rather than the surrounding grass.
    cx=(x1+x2)/2.;bw=x2-x1;bh=y2-y1
    rx1=int(max(0,cx-.36*bw));rx2=int(min(w-1,cx+.36*bw))
    ry1=int(max(0,y1+.03*bh));ry2=int(min(h-1,y1+.92*bh))
    mask=np.zeros_like(gray,np.uint8);mask[ry1:ry2+1,rx1:rx2+1]=255
    pts=cv2.goodFeaturesToTrack(gray,mask=mask,maxCorners=max_corners,qualityLevel=.008,minDistance=2.5,blockSize=5)
    if pts is not None and len(pts)>=4:return pts.astype(np.float32)
    # Tiny/distant players may not contain enough Shi-Tomasi corners.
    xs=np.linspace(rx1,rx2,3);ys=np.linspace(ry1,ry2,5)
    return np.asarray([[[x,y]] for y in ys for x in xs],np.float32)


def reset_state(state,gray,d,t,calibration=True):
    state['bbox']=np.asarray(d['box'],float)
    state['pts']=seed_points(gray,state['bbox'])
    state['fail_frames']=0
    state['last_detector_t']=float(t)
    state['last_t']=float(t)
    if calibration:
        state['cal_feats'].append(np.asarray(d['feat'],float))
        if len(state['cal_feats'])>20:state['cal_feats']=state['cal_feats'][-20:]
    return state


def flow_step(state,prev_gray,gray):
    if state.get('bbox') is None:return False
    pts=state.get('pts')
    if pts is None or len(pts)<4:
        state['pts']=seed_points(prev_gray,state['bbox']);pts=state['pts']
    if pts is None or len(pts)<4:
        state['fail_frames']+=1;return False
    nxt,st,err=cv2.calcOpticalFlowPyrLK(prev_gray,gray,pts,None,winSize=(21,21),maxLevel=3,
        criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,20,.02))
    if nxt is None or st is None:
        state['fail_frames']+=1;return False
    old=pts.reshape(-1,2);new=nxt.reshape(-1,2);ok=st.reshape(-1).astype(bool)
    if err is not None:ok &= err.reshape(-1)<35
    old=old[ok];new=new[ok]
    if len(new)<4:
        state['fail_frames']+=1;return False
    M,inl=cv2.estimateAffinePartial2D(old,new,method=cv2.RANSAC,ransacReprojThreshold=2.2,maxIters=500,confidence=.995)
    b=np.asarray(state['bbox'],float)
    if M is not None:
        scale=float(np.sqrt(M[0,0]**2+M[0,1]**2))
        if .78<=scale<=1.28:
            corners=np.asarray([[b[0],b[1]],[b[2],b[1]],[b[2],b[3]],[b[0],b[3]]],float)
            q=np.c_[corners,np.ones(4)]@M.T
            nb=np.asarray([q[:,0].min(),q[:,1].min(),q[:,0].max(),q[:,1].max()],float)
        else:
            d=np.median(new-old,axis=0);nb=b+np.asarray([d[0],d[1],d[0],d[1]])
    else:
        d=np.median(new-old,axis=0);nb=b+np.asarray([d[0],d[1],d[0],d[1]])
    h,w=gray.shape[:2];nb=clip_box(nb,w,h)
    if nb is None:
        state['fail_frames']+=1;return False
    state['bbox']=nb;state['pts']=new.reshape(-1,1,2).astype(np.float32);state['fail_frames']=0
    return True


def confident_pairs(cam,dets,gt,seed):
    if not dets or not gt:return []
    pix=np.asarray([d['foot'] for d in dets],float);pred=seed.project(pix)
    G=np.asarray([[g['x'],g['y']] for g in gt],float);C=np.linalg.norm(pred[:,None,:]-G[None,:,:],axis=2)
    ri,ci=linear_sum_assignment(C);out=[]
    for i,j in zip(ri,ci):
        c=float(C[i,j])
        row=np.sort(C[i]);col=np.sort(C[:,j])
        rm=float(row[1]-row[0]) if len(row)>1 else 99.;cm=float(col[1]-col[0]) if len(col)>1 else 99.
        # Geometry is hand-seeded, so accept extremely close matches even with a
        # modest margin, but require clearer exclusivity for 3-4.5 m matches.
        good=(c<=2.8 and rm>=.18 and cm>=.18) or (c<=4.4 and rm>=.55 and cm>=.55)
        if good:out.append((int(i),int(j),c,rm,cm))
    return out


def choose_geometry(cam,records,calibration_seconds=4.0):
    seed=v10.seed_model(cam)
    train=[r for r in records if r['t']<=CAL_SPLIT];val=[r for r in records if CAL_SPLIT<r['t']<=calibration_seconds]
    cand=[('seed',seed)]
    if len(train)>=12:
        P=np.asarray([r['pix'] for r in train],float);W=np.asarray([r['world'] for r in train],float)
        for rr in (1.55,1.25,1.0):
            cand.append((f'refine_{rr}',v10.fit_pure_h(P,W,cam,rr)))
    def quality(m):
        if not val:return {'n':0,'mae_m':99.,'p95_m':99.}
        P=np.asarray([r['pix'] for r in val],float);W=np.asarray([r['world'] for r in val],float)
        e=np.linalg.norm(m.project(P)-W,axis=1)
        return {'n':len(e),'mae_m':float(e.mean()),'p95_m':float(np.percentile(e,95))}
    scored=[]
    for name,m in cand:
        q=quality(m);sc=q['mae_m']+.16*q['p95_m'];scored.append((sc,name,m,q))
    scored.sort(key=lambda x:x[0]);_,name,model,q=scored[0]
    residual=[]
    for r in val:
        p=model.project(np.asarray([r['pix']],float))[0];residual.append(np.asarray(r['world'],float)-p)
    bias=np.median(np.asarray(residual,float),axis=0) if residual else np.zeros(2,float)
    return model,bias,{'chosen':name,'validation':q,'bias_m':bias.tolist(),'train_pairs':len(train),'validation_pairs':len(val),
        'candidates':[{'name':n,'score':float(s),'validation':qq} for s,n,_,qq in scored]}


def detector_correct(states,dets,gray,model,bias,t):
    gids=[g for g,s in states.items() if s.get('bbox') is not None and s.get('fail_frames',0)<=12]
    if not gids or not dets:return 0
    C=np.full((len(gids),len(dets)),1e6,float)
    margins=np.zeros(len(gids),float)
    for ii,gid in enumerate(gids):
        s=states[gid];b=s['bbox'];h=max(12.,b[3]-b[1]);c0=np.asarray([(b[0]+b[2])/2.,(b[1]+b[3])/2.])
        proto=np.median(np.asarray(s['cal_feats'],float),axis=0) if s['cal_feats'] else None
        vals=[]
        flow_world=model.project(np.asarray([foot_of(b)],float))[0]+bias
        for j,d in enumerate(dets):
            db=np.asarray(d['box'],float);c1=np.asarray([(db[0]+db[2])/2.,(db[1]+db[3])/2.])
            dn=float(np.linalg.norm(c1-c0)/h);iou=box_iou(b,db);app=cosdist(proto,d['feat']) if proto is not None else 0.0
            dw=model.project(np.asarray([d['foot']],float))[0]+bias;world_gap=float(np.linalg.norm(dw-flow_world))
            if dn>1.35 and iou<.015:continue
            if app>.48 and dn>.38:continue
            if world_gap>4.0 and dn>.45:continue
            cost=1.35*dn+.52*(1-iou)+.58*max(0.,app)+.10*world_gap
            C[ii,j]=cost;vals.append(cost)
        if len(vals)>=2:
            a=np.sort(np.asarray(vals,float));margins[ii]=float(a[1]-a[0])
        else:margins[ii]=99.
    ri,ci=linear_sum_assignment(C);n=0
    for ii,j in zip(ri,ci):
        if C[ii,j]>=1e5:continue
        # In a crossing, do not let a detector overwrite a healthy optical lock.
        if margins[ii]<.10 and states[gids[ii]].get('fail_frames',0)==0:continue
        gid=gids[ii];s=states[gid];d=dets[j]
        if C[ii,j]>2.75:continue
        old=np.asarray(s['bbox'],float);new=np.asarray(d['box'],float)
        # Strong detector correction, while retaining a little optical inertia.
        blend=.78 if s.get('fail_frames',0)>0 else .62
        dd=dict(d);dd['box']=blend*new+(1-blend)*old
        reset_state(s,gray,dd,t,calibration=False);n+=1
    return n


def process_camera(path,cam,detector,truth_by,sample_fps=8.0,calibration_seconds=4.0,imgsz=1280):
    cap=cv2.VideoCapture(path);fps=float(cap.get(cv2.CAP_PROP_FPS) or 30.);n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0);duration=n/fps if n else 0.
    eval_stride=max(1,int(round(fps/sample_fps)));detect_stride=eval_stride
    seed=v10.seed_model(cam);states={gid:{'gid':gid,'bbox':None,'pts':None,'fail_frames':99,'cal_feats':[],'last_t':None} for gid in TARGET_IDS}
    records=[];outputs=[];cal_seen=defaultdict(int);corrections=0;prev_gray=None;fi=0;geometry=None;bias=np.zeros(2);gdiag=None
    while True:
        ok,frame=cap.read()
        if not ok:break
        t=fi/fps;gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        if prev_gray is not None:
            for s in states.values():
                if s.get('bbox') is not None:
                    flow_step(s,prev_gray,gray);s['last_t']=float(t)
                    if len(s.get('pts',[]))<7 or fi%12==0:s['pts']=seed_points(gray,s['bbox'])

        dets=[]
        if fi%detect_stride==0:
            dets=v10.on_pitch(cam,v9.detect_native(detector,frame,imgsz=imgsz),seed)
            if t<=calibration_seconds+1e-6:
                gt=truth_at(truth_by,float(t));pairs=confident_pairs(cam,dets,gt,seed)
                for i,j,c,rm,cm in pairs:
                    gid=int(gt[j]['id']);q=np.asarray([gt[j]['x'],gt[j]['y']],float);d=dets[i]
                    records.append({'t':float(t),'gid':gid,'pix':np.asarray(d['foot'],float),'world':q,'seed_err':c})
                    reset_state(states[gid],gray,d,t,calibration=True);cal_seen[gid]+=1
            else:
                if geometry is None:
                    geometry,bias,gdiag=choose_geometry(cam,records,calibration_seconds)
                corrections+=detector_correct(states,dets,gray,geometry,bias,t)

        if t>calibration_seconds and fi%eval_stride==0:
            if geometry is None:geometry,bias,gdiag=choose_geometry(cam,records,calibration_seconds)
            for gid,s in states.items():
                if s.get('bbox') is None or s.get('fail_frames',99)>8:continue
                # An identity must have calibration evidence and be reasonably
                # fresh at the calibration boundary; no holdout GT reacquisition.
                if cal_seen[gid]<2:continue
                b=clip_box(s['bbox'],frame.shape[1],frame.shape[0])
                if b is None:continue
                p=geometry.project(np.asarray([foot_of(b)],float))[0]+bias
                if not (-2<=p[0]<=107 and -2<=p[1]<=70):continue
                outputs.append({'cam':cam,'t':float(t),'gid':gid,'xy':np.asarray(p,float),'flow_fail_frames':int(s['fail_frames'])})
        prev_gray=gray;fi+=1
    cap.release()
    if geometry is None:geometry,bias,gdiag=choose_geometry(cam,records,calibration_seconds)
    return outputs,{'fps':fps,'frames':fi,'duration_s':duration,'eval_stride':eval_stride,'sample_fps_actual':fps/eval_stride,
        'calibration_pairs':len(records),'calibration_seen':{str(k):int(v) for k,v in cal_seen.items()},'detector_corrections_holdout':corrections,'geometry':gdiag},geometry


def fuse(all_outputs,qualities,truth_by):
    buckets=defaultdict(list);times=set()
    for cam,outs in all_outputs.items():
        for o in outs:
            tk=round(o['t'],3);times.add(tk);buckets[(tk,o['gid'])].append(o)
    rows=[]
    for (tk,gid),items in sorted(buckets.items()):
        pts=np.asarray([o['xy'] for o in items],float);cams=[o['cam'] for o in items]
        if len(items)==1:p=pts[0];used=cams
        else:
            D=np.linalg.norm(pts[:,None,:]-pts[None,:,:],axis=2)
            w=np.asarray([1./(.18+qualities[o['cam']]**2) for o in items],float)
            med=int(np.argmin((D*w[None,:]).sum(axis=1)));keep=D[med]<=2.6
            if not np.any(keep):keep[med]=True
            ww=w[keep];ww/=ww.sum();p=(pts[keep]*ww[:,None]).sum(axis=0);used=[cams[i] for i in np.where(keep)[0]]
        gt={g['id']:g for g in truth_at(truth_by,float(tk))}
        if gid not in gt:continue
        q=np.asarray([gt[gid]['x'],gt[gid]['y']],float);err=float(np.linalg.norm(p-q))
        rows.append({'t':float(tk),'track_id':gid,'gt_id':gid,'pred_x':float(p[0]),'pred_y':float(p[1]),'truth_x':float(q[0]),'truth_y':float(q[1]),'position_error_m':err,'camera_count':len(used),'cams':','.join(map(str,used))})
    total_gt=0
    for tk in times:
        ids={g['id'] for g in truth_at(truth_by,float(tk))};total_gt+=sum(gid in ids for gid in TARGET_IDS)
    return rows,total_gt,len(rows)


def main():
    ap=argparse.ArgumentParser()
    for i in range(3):ap.add_argument(f'--cam{i}',required=True)
    ap.add_argument('--truth',required=True);ap.add_argument('--out',required=True);ap.add_argument('--sample-fps',type=float,default=8.0);ap.add_argument('--calibration-seconds',type=float,default=4.0);ap.add_argument('--model',default='yolo11n.pt');ap.add_argument('--imgsz',type=int,default=1280)
    args=ap.parse_args();out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    from ultralytics import YOLO
    detector=YOLO(args.model);truth_by=load_truth(args.truth,video_start=NATIVE_START)
    all_outputs={};diag={};qualities={}
    for cam in range(3):
        outs,d,m=process_camera(getattr(args,f'cam{cam}'),cam,detector,truth_by,args.sample_fps,args.calibration_seconds,args.imgsz)
        all_outputs[cam]=outs;diag[str(cam)]=d;q=d['geometry']['validation']['mae_m'];qualities[cam]=float(q if np.isfinite(q) and q<20 else 9.0);np.save(out/f'cam{cam}_H.npy',m.H)
        print('cam',cam,json.dumps(d,indent=2),flush=True)
    rows,total_gt,total_det=fuse(all_outputs,qualities,truth_by);metrics=summarize_physical(rows,total_gt,total_det)
    ids=sorted(set(int(r['gt_id']) for r in rows));metrics.update({'version':'v19-calibration-locked-optical-flow','identity_frozen_holdout':True,'post_holdout_gt_relinking':False,'identity_id_coverage':len(ids)/len(TARGET_IDS),'mapped_gt_ids':ids,'camera_diagnostics':diag,'truth_source':'20Hz sensor XY','tracking_method':'per-player Lucas-Kanade optical flow at every frame; detector corrections are geometry+appearance gated; player identity is assigned only during t<=4s calibration','note':'holdout GT is evaluation only'})
    pd.DataFrame(rows).to_csv(out/'matched_observations.csv',index=False);(out/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8');print(json.dumps(metrics,indent=2),flush=True)

if __name__=='__main__':main()
