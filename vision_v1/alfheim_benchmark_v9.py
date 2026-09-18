from __future__ import annotations
import argparse, json, math
from dataclasses import dataclass, field
from pathlib import Path
import cv2
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from alfheim_benchmark import load_truth, truth_at
from alfheim_benchmark_v2 import jersey_red_score
from alfheim_benchmark_v3 import appearance_feature
from alfheim_benchmark_v7 import summarize_physical

NATIVE_START = pd.Timestamp('2013-11-03 18:01:14.248366')
TARGET_IDS = [1,2,5,7,8,9,10,13,14,15]
FIELD_X = (-5.0, 110.0)
FIELD_Y = (-5.0, 73.0)

# Calibration-only seed landmarks, measured from synchronized native frames.
# World convention: x=0..105 goal-line to goal-line, y=0..68 near to far touchline.
SEED = {
    0: (
        np.float32([[315,247],[620,176],[474,295],[817,212]]),
        np.float32([[0,13.84],[0,54.16],[16.5,13.84],[16.5,54.16]]),
    ),
    1: (
        np.float32([[646,96],[876,778],[489,200],[861,200]]),
        np.float32([[52.5,68],[52.5,0],[43.35,34],[61.65,34]]),
    ),
    2: (
        np.float32([[405,900],[0,390],[1255,273],[878,280]]),
        np.float32([[52.5,0],[52.5,34],[105,0],[88.5,13.84]]),
    ),
}


def H_project(H, pix):
    p=np.asarray(pix,float)
    if len(p)==0: return np.empty((0,2),float)
    q=np.c_[p,np.ones(len(p))] @ np.asarray(H,float).T
    z=q[:,2:3]
    z[np.abs(z)<1e-9]=1e-9
    return q[:,:2]/z


def norm_features(pix):
    p=np.asarray(pix,float)
    u=(p[:,0]-640.)/640.; v=(p[:,1]-480.)/480.
    return np.c_[np.ones(len(p)),u,v,u*u,u*v,v*v]


class CameraModel:
    def __init__(self,H,residual=None):
        self.H=np.asarray(H,float)
        self.residual=None if residual is None else np.asarray(residual,float)
    def project(self,pix):
        p=np.asarray(pix,float)
        base=H_project(self.H,p)
        if self.residual is None or len(p)==0: return base
        return base + norm_features(p) @ self.residual


def fit_camera_model(pix, world, use_residual=True):
    pix=np.asarray(pix,float); world=np.asarray(world,float)
    if len(pix)<4: raise RuntimeError('need >=4 camera pairs')
    H,mask=cv2.findHomography(pix.astype(np.float32),world.astype(np.float32),cv2.RANSAC,2.2,maxIters=4000,confidence=.998)
    if H is None: H,_=cv2.findHomography(pix.astype(np.float32),world.astype(np.float32),0)
    base=H_project(H,pix); err=np.linalg.norm(base-world,axis=1)
    good=err<max(2.8,float(np.percentile(err,80)))
    residual=None
    if use_residual and int(good.sum())>=12:
        X=norm_features(pix[good]); R=world[good]-base[good]
        reg=np.diag([.03,.03,.03,.35,.35,.35])
        residual=np.linalg.solve(X.T@X+reg, X.T@R)
        corr=base+norm_features(pix)@residual
        delta=np.linalg.norm(corr-base,axis=1)
        if float(np.percentile(delta,95))>4.0: residual=None
    return CameraModel(H,residual)


def detect_native(model, frame, imgsz=1280):
    r=model.predict(frame,imgsz=imgsz,conf=.045,iou=.55,classes=[0],device='cpu',verbose=False)[0]
    out=[]
    if r.boxes is None: return out
    for box in r.boxes:
        xy=box.xyxy[0].cpu().numpy().astype(float)
        x1,y1,x2,y2=xy.tolist(); conf=float(box.conf[0].cpu())
        if (x2-x1)<4 or (y2-y1)<10: continue
        foot=np.array([(x1+x2)/2., y2],float)
        out.append({'box':xy,'foot':foot,'conf':conf,'feat':appearance_feature(frame,xy),'red':float(jersey_red_score(frame,xy))})
    return out


def hungarian_pairs(pred, gt, maxcost):
    pred=np.asarray(pred,float)
    if len(pred)==0 or not gt: return []
    G=np.asarray([[g['x'],g['y']] for g in gt],float)
    C=np.linalg.norm(pred[:,None,:]-G[None,:,:],axis=2)
    ri,ci=linear_sum_assignment(C)
    return [(int(i),int(j),float(C[i,j])) for i,j in zip(ri,ci) if C[i,j]<=maxcost]


class TeamClassifier:
    def __init__(self):
        self.mean=None; self.std=None; self.pos=None; self.neg=None; self.red_floor=-1.0; self.threshold=0.0
    def fit(self,pos_feats,neg_feats,pos_red,neg_red):
        P=np.asarray(pos_feats,float); N=np.asarray(neg_feats,float)
        if len(P)<3:
            self.red_floor=float(np.percentile(pos_red,10)) if len(pos_red) else 0.0
            return
        A=np.vstack([P,N]) if len(N) else P
        self.mean=A.mean(0); self.std=A.std(0)+1e-4
        Pz=(P-self.mean)/self.std
        self.pos=np.median(Pz,axis=0)
        if len(N)>=3: self.neg=np.median((N-self.mean)/self.std,axis=0)
        self.red_floor=max(0.0,float(np.percentile(pos_red,5))*.35) if len(pos_red) else 0.0
    def score(self,d):
        if self.pos is None:
            return float(d['red']-self.red_floor)
        z=(np.asarray(d['feat'],float)-self.mean)/self.std
        dp=float(np.sqrt(np.mean((z-self.pos)**2)))
        if self.neg is None: s=1.5-dp
        else:
            dn=float(np.sqrt(np.mean((z-self.neg)**2))); s=dn-dp
        s += .18*np.clip((float(d['red'])-.01)/.04,-1,2)
        return s
    def keep(self,d): return self.score(d)>=self.threshold


def learn_team_classifier(cam_frames, seed_model, calibration_seconds):
    pos=[]; neg=[]; pr=[]; nr=[]
    for f in cam_frames:
        if f['t']>calibration_seconds: continue
        det=f['det']; pred=seed_model.project(np.asarray([d['foot'] for d in det],float)) if det else np.empty((0,2))
        pairs=hungarian_pairs(pred,f['gt'],8.5)
        matched={i:c for i,j,c in pairs}
        if len(pred):
            G=np.asarray([[g['x'],g['y']] for g in f['gt']],float)
            nearest=np.min(np.linalg.norm(pred[:,None,:]-G[None,:,:],axis=2),axis=1) if len(G) else np.full(len(pred),99.)
        else: nearest=[]
        for i,d in enumerate(det):
            if i in matched and matched[i]<=5.5:
                pos.append(d['feat']); pr.append(d['red'])
            elif nearest[i]>=7.0:
                neg.append(d['feat']); nr.append(d['red'])
    clf=TeamClassifier(); clf.fit(pos,neg,pr,nr)
    raw=[]
    for f in cam_frames:
        if f['t']>calibration_seconds: continue
        raw.extend([clf.score(d) for d in f['det']])
    if raw:
        qs=np.unique(np.quantile(raw,np.linspace(.10,.90,21)))
        best=(-1e9,0.0,{})
        for th in qs:
            nm=nd=ng=0; costs=[]
            for f in cam_frames:
                if f['t']>calibration_seconds: continue
                ds=[d for d in f['det'] if clf.score(d)>=th]
                pred=seed_model.project(np.asarray([d['foot'] for d in ds],float)) if ds else np.empty((0,2))
                pairs=hungarian_pairs(pred,f['gt'],8.0)
                nm+=len(pairs); nd+=len(ds); ng+=len(f['gt']); costs += [c for _,_,c in pairs]
            prec=nm/max(1,nd); rec=nm/max(1,ng); f1=2*prec*rec/max(1e-9,prec+rec)
            mae=float(np.mean(costs)) if costs else 99.
            score=f1-.01*mae
            if score>best[0]: best=(score,float(th),{'precision':prec,'recall':rec,'f1':f1,'mae':mae,'n_pos':len(pos),'n_neg':len(neg)})
        clf.threshold=best[1]; info=best[2]
    else: info={'n_pos':len(pos),'n_neg':len(neg)}
    info['threshold']=clf.threshold; info['red_floor']=clf.red_floor
    return clf,info


def collect_geometry_pairs(cam_frames, clf, model, calibration_seconds, gate):
    P=[]; W=[]; F=[]; costs=[]
    for fi,f in enumerate(cam_frames):
        if f['t']>calibration_seconds: continue
        ds=[d for d in f['det'] if clf.keep(d)]
        pix=np.asarray([d['foot'] for d in ds],float) if ds else np.empty((0,2))
        pred=model.project(pix) if len(pix) else np.empty((0,2))
        pairs=hungarian_pairs(pred,f['gt'],gate)
        for i,j,c in pairs:
            P.append(pix[i]); W.append([f['gt'][j]['x'],f['gt'][j]['y']]); F.append(fi); costs.append(c)
    return np.asarray(P,float),np.asarray(W,float),np.asarray(F,int),costs


def calibrate_camera(cam_frames, clf, seed_model, calibration_seconds):
    model=seed_model; history=[]; allP=allW=allF=None
    for it,gate in enumerate([8.0,5.5,4.0,3.0,2.2]):
        P,W,F,costs=collect_geometry_pairs(cam_frames,clf,model,calibration_seconds,gate)
        if len(P)<6: break
        if len(costs)>=10:
            a=np.asarray(costs); lim=min(gate,float(np.percentile(a,88))+.3); keep=a<=lim
            P,W,F=P[keep],W[keep],F[keep]
        if len(P)<4: break
        cand=fit_camera_model(P,W,use_residual=True)
        e=np.linalg.norm(cand.project(P)-W,axis=1)
        model=cand; allP,allW,allF=P,W,F
        history.append({'iteration':it,'gate_m':gate,'pairs':len(P),'train_mae_m':float(e.mean()),'train_p95_m':float(np.percentile(e,95)),'residual':cand.residual is not None})
    if allP is None: raise RuntimeError('camera calibration produced no pairs')
    return model,allP,allW,allF,history


def camera_geometry_eval(cam_frames, clf, model, calibration_seconds, gate=4.0):
    errs=[]; matched=detn=gtn=0
    for f in cam_frames:
        if f['t']<=calibration_seconds: continue
        ds=[d for d in f['det'] if clf.keep(d)]
        pix=np.asarray([d['foot'] for d in ds],float) if ds else np.empty((0,2))
        pred=model.project(pix) if len(pix) else np.empty((0,2))
        pairs=hungarian_pairs(pred,f['gt'],gate)
        errs += [c for _,_,c in pairs]; matched+=len(pairs); detn+=len(pred); gtn+=len(f['gt'])
    if not errs: return {'matched':0,'gt_points':gtn,'detections':detn}
    a=np.asarray(errs,float)
    return {'matched':matched,'gt_points':gtn,'detections':detn,'recall':matched/max(1,gtn),'precision_proxy':matched/max(1,detn),'mae_m':float(a.mean()),'rmse_m':float(np.sqrt(np.mean(a*a))),'p95_m':float(np.percentile(a,95))}


def fuse_frame(cam_entries, classifiers, models, radius=1.35):
    obs=[]
    for cam,f in cam_entries.items():
        ds=[d for d in f['det'] if classifiers[cam].keep(d)]
        if not ds: continue
        pix=np.asarray([d['foot'] for d in ds],float); xy=models[cam].project(pix)
        for d,p in zip(ds,xy):
            if not (FIELD_X[0]<=p[0]<=FIELD_X[1] and FIELD_Y[0]<=p[1]<=FIELD_Y[1]): continue
            obs.append({'cam':cam,'xy':np.asarray(p,float),'feat':np.asarray(d['feat'],float),'conf':d['conf'],'pix':d['foot']})
    n=len(obs); seen=set(); clusters=[]
    for i in range(n):
        if i in seen: continue
        comp={i}; frontier=[i]; seen.add(i)
        while frontier:
            a=frontier.pop()
            for j in range(n):
                if j in seen: continue
                if obs[j]['cam']==obs[a]['cam']: continue
                if np.linalg.norm(obs[j]['xy']-obs[a]['xy'])<=radius:
                    seen.add(j); comp.add(j); frontier.append(j)
        clusters.append(sorted(comp))
    fused=[]
    for comp in clusters:
        items=[obs[i] for i in comp]; per={}
        for o in items:
            if o['cam'] not in per or o['conf']>per[o['cam']]['conf']: per[o['cam']]=o
        items=list(per.values()); w=np.asarray([max(.05,o['conf']) for o in items],float); w/=w.sum()
        xy=sum(wi*o['xy'] for wi,o in zip(w,items)); feat=sum(wi*o['feat'] for wi,o in zip(w,items))
        fused.append({'xy':np.asarray(xy,float),'feat':np.asarray(feat,float),'conf':float(max(o['conf'] for o in items)),'cams':[o['cam'] for o in items]})
    return fused


@dataclass
class WorldTrack:
    tid:int
    obs:list=field(default_factory=list)
    miss_s:float=0.0
    def predict(self,t):
        if not self.obs: return np.zeros(2)
        if len(self.obs)<2: return self.obs[-1]['xy']
        a,b=self.obs[-2],self.obs[-1]; dt=max(1e-3,b['t']-a['t']); v=(b['xy']-a['xy'])/dt
        speed=np.linalg.norm(v)
        if speed>12: v*=12/speed
        return b['xy']+v*max(0,t-b['t'])
    def proto(self):
        if not self.obs: return None
        return np.mean([o['feat'] for o in self.obs[-8:]],axis=0)


def track_world(frames):
    tracks=[]; active=[]; nextid=0; prev_t=None
    for f in frames:
        t=f['t']; det=f['fused']; dt=0.125 if prev_t is None else max(.01,t-prev_t); prev_t=t
        if active and det:
            C=np.full((len(active),len(det)),1e4,float)
            for i,tr in enumerate(active):
                pred=tr.predict(t); proto=tr.proto()
                for j,d in enumerate(det):
                    dist=float(np.linalg.norm(pred-d['xy'])); gate=min(3.0,1.25+12.*dt+0.4*tr.miss_s)
                    if dist>gate: continue
                    app=0.0
                    if proto is not None:
                        den=np.linalg.norm(proto)*np.linalg.norm(d['feat'])+1e-6; app=1-float(np.dot(proto,d['feat'])/den)
                    C[i,j]=dist+.35*max(0,app)
            ri,ci=linear_sum_assignment(C); used_t=set(); used_d=set()
            for i,j in zip(ri,ci):
                if C[i,j]>=1e3: continue
                tr=active[i]; d=det[j]; tr.obs.append({'t':t,'xy':d['xy'],'feat':d['feat'],'cams':d['cams'],'conf':d['conf']}); tr.miss_s=0; used_t.add(i); used_d.add(j)
            for i,tr in enumerate(active):
                if i not in used_t: tr.miss_s+=dt
            for j,d in enumerate(det):
                if j not in used_d:
                    tr=WorldTrack(nextid,[{'t':t,'xy':d['xy'],'feat':d['feat'],'cams':d['cams'],'conf':d['conf']}],0.0); nextid+=1; tracks.append(tr); active.append(tr)
        else:
            for tr in active: tr.miss_s+=dt
            if det:
                for d in det:
                    tr=WorldTrack(nextid,[{'t':t,'xy':d['xy'],'feat':d['feat'],'cams':d['cams'],'conf':d['conf']}],0.0); nextid+=1; tracks.append(tr); active.append(tr)
        active=[tr for tr in active if tr.miss_s<=1.0]
    return tracks


def map_tracks_calibration(tracks, truth_by, calibration_seconds):
    candidates=[]; tids=[]
    for tr in tracks:
        cal=[o for o in tr.obs if o['t']<=calibration_seconds]; hold=[o for o in tr.obs if o['t']>calibration_seconds]
        if len(cal)<6 or len(hold)<3: continue
        row=[]
        for gid in TARGET_IDS:
            errs=[]
            for o in cal:
                gt={g['id']:g for g in truth_at(truth_by,o['t'])}
                if gid in gt: errs.append(np.linalg.norm(o['xy']-np.array([gt[gid]['x'],gt[gid]['y']])))
            row.append(float(np.median(errs)) if errs else 99.)
        candidates.append(row); tids.append(tr.tid)
    if not candidates: return {},[]
    C=np.asarray(candidates,float); ri,ci=linear_sum_assignment(C); mapping={}; rows=[]
    for r,c in zip(ri,ci):
        med=float(C[r,c]); sorted_row=np.sort(C[r]); margin=float(sorted_row[1]-sorted_row[0]) if len(sorted_row)>1 else 99.
        if med<=2.2:
            mapping[tids[r]]=TARGET_IDS[c]; rows.append({'track_id':tids[r],'gt_id':TARGET_IDS[c],'calibration_median_m':med,'identity_margin_m':margin})
    return mapping,rows


def persistent_eval(tracks,mapping,truth_by,all_times,calibration_seconds,fused_count):
    rows=[]; total_gt=sum(len(truth_at(truth_by,t)) for t in all_times if t>calibration_seconds)
    for tr in tracks:
        gid=mapping.get(tr.tid)
        if gid is None: continue
        for o in tr.obs:
            if o['t']<=calibration_seconds: continue
            gt={g['id']:g for g in truth_at(truth_by,o['t'])}
            if gid not in gt: continue
            g=gt[gid]; truth=np.array([g['x'],g['y']],float); err=float(np.linalg.norm(o['xy']-truth))
            rows.append({'t':o['t'],'track_id':tr.tid,'gt_id':gid,'pred_x':o['xy'][0],'pred_y':o['xy'][1],'truth_x':g['x'],'truth_y':g['y'],'position_error_m':err,'truth_speed':g.get('speed',0.0),'truth_total_distance':g.get('total_distance',0.0)})
    metrics=summarize_physical(rows,total_gt,fused_count); mapped_ids=sorted(set(mapping.values()))
    metrics.update({'identity_frozen_holdout':True,'mapped_tracks':len(mapping),'mapped_gt_ids':mapped_ids,'identity_id_coverage':len(mapped_ids)/len(TARGET_IDS),'all_tracks':len(tracks)})
    return metrics,rows


def geometry_fused_eval(frames,truth_by,calibration_seconds,gate=3.0):
    errs=[]; nm=nd=ng=0
    for f in frames:
        if f['t']<=calibration_seconds: continue
        pred=np.asarray([d['xy'] for d in f['fused']],float) if f['fused'] else np.empty((0,2)); gt=truth_at(truth_by,f['t']); pairs=hungarian_pairs(pred,gt,gate)
        errs += [c for _,_,c in pairs]; nm+=len(pairs); nd+=len(pred); ng+=len(gt)
    if not errs:return {'matched':0,'gt_points':ng,'detections':nd}
    a=np.asarray(errs,float)
    return {'matched':nm,'gt_points':ng,'detections':nd,'recall':nm/max(1,ng),'precision_proxy':nm/max(1,nd),'mae_m':float(a.mean()),'rmse_m':float(np.sqrt(np.mean(a*a))),'p95_m':float(np.percentile(a,95))}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--cam0',required=True); ap.add_argument('--cam1',required=True); ap.add_argument('--cam2',required=True); ap.add_argument('--truth',required=True); ap.add_argument('--out',required=True); ap.add_argument('--sample-fps',type=float,default=8.0); ap.add_argument('--calibration-seconds',type=float,default=4.0); ap.add_argument('--model',default='yolo11n.pt'); args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    from ultralytics import YOLO
    detector=YOLO(args.model); truth_by=load_truth(args.truth,video_start=NATIVE_START)
    caps={i:cv2.VideoCapture(getattr(args,f'cam{i}')) for i in range(3)}; durations=[]
    for cap in caps.values():
        fps=float(cap.get(cv2.CAP_PROP_FPS) or 25); durations.append(cap.get(cv2.CAP_PROP_FRAME_COUNT)/fps)
    dur=min(durations); times=np.arange(.4,max(.41,dur-.2),1./args.sample_fps); cams={i:[] for i in range(3)}
    for ti,t in enumerate(times):
        gt=truth_at(truth_by,float(t))
        for cam,cap in caps.items():
            cap.set(cv2.CAP_PROP_POS_MSEC,float(t*1000)); ok,frame=cap.read()
            if not ok: continue
            det=detect_native(detector,frame); cams[cam].append({'t':float(t),'frame':frame if ti==0 else None,'det':det,'gt':gt})
        if ti%8==0: print(f't={t:.2f}s det=' + ','.join(f'c{c}:{len(cams[c][-1]["det"])}' for c in cams if cams[c]),flush=True)
    for cap in caps.values(): cap.release()

    models={}; classifiers={}; diagnostics={}
    for cam in range(3):
        sp,sw=SEED[cam]; seed=CameraModel(cv2.getPerspectiveTransform(sp,sw),None)
        clf,teaminfo=learn_team_classifier(cams[cam],seed,args.calibration_seconds); model,P,W,F,hist=calibrate_camera(cams[cam],clf,seed,args.calibration_seconds)
        models[cam]=model; classifiers[cam]=clf; diagnostics[str(cam)]={'team':teaminfo,'calibration_history':hist,'holdout_geometry':camera_geometry_eval(cams[cam],clf,model,args.calibration_seconds),'pairs':len(P)}
        np.save(out/f'cam{cam}_H.npy',model.H)
        if model.residual is not None: np.save(out/f'cam{cam}_residual.npy',model.residual)
        print('cam',cam,json.dumps(diagnostics[str(cam)],indent=2),flush=True)

    frames=[]
    for idx,t in enumerate(times):
        entries={cam:cams[cam][idx] for cam in range(3) if idx<len(cams[cam]) and abs(cams[cam][idx]['t']-t)<1e-4}
        frames.append({'t':float(t),'fused':fuse_frame(entries,classifiers,models)})
    tracks=track_world(frames); mapping,maprows=map_tracks_calibration(tracks,truth_by,args.calibration_seconds)
    fused_count=sum(len(f['fused']) for f in frames if f['t']>args.calibration_seconds); metrics,rows=persistent_eval(tracks,mapping,truth_by,times,args.calibration_seconds,fused_count)
    metrics['fused_geometry_only']=geometry_fused_eval(frames,truth_by,args.calibration_seconds)
    metrics.update({'version':'v9-native-3cam-world-fusion','video_duration_s':dur,'sample_fps':args.sample_fps,'calibration_seconds':args.calibration_seconds,'camera_diagnostics':diagnostics,'track_identity_mapping':maprows,'native_cameras':[0,1,2],'post_holdout_relinking':False,'truth_source':'20Hz sensor XY'})
    pd.DataFrame(rows).to_csv(out/'matched_observations.csv',index=False); (out/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8'); (out/'track_identity_mapping.json').write_text(json.dumps(maprows,indent=2),encoding='utf-8'); print(json.dumps(metrics,indent=2),flush=True)

if __name__=='__main__': main()
