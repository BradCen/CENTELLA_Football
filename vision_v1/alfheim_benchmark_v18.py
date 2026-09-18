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


def sample_track_video(path, cam, model_path, sample_fps=8.0, tracker='bytetrack.yaml', imgsz=960):
    """Run MOT on every video frame, but retain observations at sample_fps.

    Tracking on full frame rate is the important difference from V13-V17:
    identity continuity is not asked to jump across 125 ms detector snapshots.
    """
    from ultralytics import YOLO
    model = YOLO(model_path)
    cap = cv2.VideoCapture(path)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = n / fps if n else 0.0
    stride = max(1, int(round(fps / sample_fps)))
    seed = v10.seed_model(cam)
    obs = []
    fi = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        # Full-frame persistent MOT. Low conf lets ByteTrack recover weak distant
        # players using its second association stage.
        r = model.track(frame, persist=True, tracker=tracker, imgsz=imgsz,
                        conf=0.035, iou=0.55, classes=[0], device='cpu', verbose=False)[0]
        if fi % stride == 0 and r.boxes is not None and r.boxes.id is not None:
            ids = r.boxes.id.int().cpu().tolist()
            xyxy = r.boxes.xyxy.cpu().numpy().astype(float)
            confs = r.boxes.conf.cpu().numpy().astype(float)
            t = fi / fps
            det = []
            for tid, box, cf in zip(ids, xyxy, confs):
                x1,y1,x2,y2 = box.tolist()
                if (x2-x1) < 4 or (y2-y1) < 10:
                    continue
                foot = np.asarray([(x1+x2)/2.0, y2], float)
                det.append({'tid':int(tid),'foot':foot,'conf':float(cf),'box':box})
            # Reject spectators/staff geometrically before any identity mapping.
            if det:
                pix = np.asarray([d['foot'] for d in det], float)
                xy = seed.project(pix)
                for d,p in zip(det,xy):
                    if v10.ROI_X[0] <= p[0] <= v10.ROI_X[1] and v10.ROI_Y[0] <= p[1] <= v10.ROI_Y[1]:
                        obs.append({'cam':cam,'t':float(t),'tid':d['tid'],'foot':d['foot'],
                                    'seed_xy':np.asarray(p,float),'conf':d['conf']})
        fi += 1
    cap.release()
    return obs, {'fps':fps,'frames':fi,'duration_s':duration,'sample_stride':stride,
                 'sample_fps_actual':fps/stride,'tracker':tracker,'imgsz':imgsz}


def track_gid_stats(track_obs, gid, truth_by, end_t=4.0):
    errs=[]
    for o in track_obs:
        if o['t'] > end_t:
            continue
        gt={g['id']:g for g in truth_at(truth_by,o['t'])}
        if gid not in gt:
            continue
        q=np.asarray([gt[gid]['x'],gt[gid]['y']],float)
        errs.append(float(np.linalg.norm(o['seed_xy']-q)))
    if not errs:
        return 99.0,99.0,0
    a=np.asarray(errs,float)
    return float(np.median(a)),float(np.percentile(a,85)),len(a)


def map_tracks(obs, truth_by, calibration_seconds=4.0):
    by=defaultdict(list)
    for o in obs:
        by[o['tid']].append(o)
    tids=[]; rows=[]; ns=[]
    for tid,oo in by.items():
        n=sum(o['t']<=calibration_seconds for o in oo)
        if n < 5:
            continue
        tids.append(tid); ns.append(n)
        row=[]
        for gid in TARGET_IDS:
            med,p85,k=track_gid_stats(oo,gid,truth_by,calibration_seconds)
            # Long calibration support is valuable; a short accidental pass near
            # a sensor path must not beat a persistent correct track.
            support_pen=max(0.0,8-k)*0.12
            row.append(med + 0.18*p85 + support_pen)
        rows.append(row)
    if not rows:
        return {},[]
    C=np.asarray(rows,float)
    ri,ci=linear_sum_assignment(C)
    mapping={};diag=[]
    for r,c in zip(ri,ci):
        tid=tids[r];gid=TARGET_IDS[c]
        med,p85,n=track_gid_stats(by[tid],gid,truth_by,calibration_seconds)
        sr=np.sort(C[r]);margin=float(sr[1]-sr[0]) if len(sr)>1 else 99.0
        # Mapping uses calibration only. Broad enough for the hand-measured seed
        # homography, strict enough to exclude rival-team tracks.
        if med <= 3.6 and p85 <= 5.0 and n >= 5 and margin >= 0.35:
            mapping[tid]=gid
            diag.append({'track_id':tid,'gt_id':gid,'cal_median_seed_m':med,
                         'cal_p85_seed_m':p85,'cal_samples':n,'cost_margin':margin,
                         'total_samples':len(by[tid]),
                         'holdout_samples':sum(o['t']>calibration_seconds for o in by[tid])})
    return mapping,diag


def fit_geometry(cam, obs, mapping, truth_by, calibration_seconds=4.0):
    seed=v10.seed_model(cam)
    P=[];W=[]
    for o in obs:
        gid=mapping.get(o['tid'])
        if gid is None or o['t']>CAL_SPLIT:
            continue
        gt={g['id']:g for g in truth_at(truth_by,o['t'])}
        if gid in gt:
            P.append(o['foot']);W.append([gt[gid]['x'],gt[gid]['y']])
    candidates=[('seed',seed)]
    if len(P)>=10:
        Pn=np.asarray(P,float);Wn=np.asarray(W,float)
        for rr in (1.4,1.05):
            candidates.append((f'refine_{rr}',v10.fit_pure_h(Pn,Wn,cam,rr)))

    def val(model):
        es=[]
        for o in obs:
            gid=mapping.get(o['tid'])
            if gid is None or not (CAL_SPLIT < o['t'] <= calibration_seconds):
                continue
            gt={g['id']:g for g in truth_at(truth_by,o['t'])}
            if gid not in gt: continue
            p=model.project(np.asarray([o['foot']],float))[0]
            q=np.asarray([gt[gid]['x'],gt[gid]['y']],float)
            es.append(float(np.linalg.norm(p-q)))
        if not es:return {'n':0,'mae_m':99.0,'p95_m':99.0,'bias':[0.0,0.0]}
        a=np.asarray(es,float)
        # Bias is recomputed below for chosen model using vector residuals.
        return {'n':len(a),'mae_m':float(a.mean()),'p95_m':float(np.percentile(a,95))}

    scored=[]
    for name,m in candidates:
        q=val(m);score=q['mae_m']+0.18*q['p95_m']
        scored.append((score,name,m,q))
    scored.sort(key=lambda x:x[0]);_,name,chosen,q=scored[0]

    # Calibration-only constant residual corrects systematic box-bottom/line
    # landmark bias without fitting a flexible holdout-dependent warp.
    residuals=[]
    for o in obs:
        gid=mapping.get(o['tid'])
        if gid is None or not (CAL_SPLIT < o['t'] <= calibration_seconds):continue
        gt={g['id']:g for g in truth_at(truth_by,o['t'])}
        if gid not in gt:continue
        p=chosen.project(np.asarray([o['foot']],float))[0]
        qxy=np.asarray([gt[gid]['x'],gt[gid]['y']],float)
        residuals.append(qxy-p)
    bias=np.median(np.asarray(residuals,float),axis=0) if residuals else np.zeros(2)
    return chosen,bias,{'chosen':name,'validation':q,'bias_m':bias.tolist(),
                        'candidates':[{'name':n,'score':float(s),'validation':qq} for s,n,_,qq in scored],
                        'train_pairs':len(P)}


def fuse_holdout(all_obs, mappings, models, biases, qualities, truth_by, calibration_seconds=4.0):
    buckets=defaultdict(list)
    sample_times=set()
    for cam,obs in all_obs.items():
        m=mappings[cam];model=models[cam];bias=biases[cam]
        mapped=[o for o in obs if o['t']>calibration_seconds and o['tid'] in m]
        if mapped:
            pix=np.asarray([o['foot'] for o in mapped],float)
            xy=model.project(pix)+bias[None,:]
            for o,p in zip(mapped,xy):
                gid=m[o['tid']];tk=round(o['t'],3);sample_times.add(tk)
                buckets[(tk,gid)].append({'cam':cam,'xy':np.asarray(p,float),'conf':o['conf']})

    rows=[];outputs=0
    for (tk,gid),items in sorted(buckets.items()):
        gt={g['id']:g for g in truth_at(truth_by,float(tk))}
        if gid not in gt:continue
        # One observation per camera; fuse compatible cameras, otherwise trust
        # the calibration-better camera rather than averaging an outlier.
        per={}
        for z in items:
            if z['cam'] not in per or z['conf']>per[z['cam']]['conf']:per[z['cam']]=z
        items=list(per.values());pts=np.asarray([z['xy'] for z in items],float)
        if len(items)==1:
            p=pts[0];cams=[items[0]['cam']]
        else:
            # pairwise-consistent set around the weighted medoid
            ws=np.asarray([max(.05,z['conf'])/(0.25+qualities[z['cam']]**2) for z in items],float)
            D=np.linalg.norm(pts[:,None,:]-pts[None,:,:],axis=2)
            medoid=int(np.argmin((D*ws[None,:]).sum(axis=1)))
            keep=D[medoid]<=2.4
            if not np.any(keep):keep[medoid]=True
            pp=pts[keep];ww=ws[keep];ww/=ww.sum();p=(pp*ww[:,None]).sum(axis=0)
            cams=[items[i]['cam'] for i in np.where(keep)[0]]
        q=np.asarray([gt[gid]['x'],gt[gid]['y']],float);err=float(np.linalg.norm(p-q));outputs+=1
        rows.append({'t':float(tk),'track_id':gid,'gt_id':gid,'pred_x':float(p[0]),'pred_y':float(p[1]),
                     'truth_x':float(q[0]),'truth_y':float(q[1]),'position_error_m':err,
                     'camera_count':len(cams),'cams':','.join(map(str,cams))})

    total_gt=0
    for tk in sorted(sample_times):
        ids={g['id'] for g in truth_at(truth_by,float(tk))}
        total_gt+=sum(gid in ids for gid in TARGET_IDS)
    return rows,total_gt,outputs


def main():
    ap=argparse.ArgumentParser()
    for i in range(3):ap.add_argument(f'--cam{i}',required=True)
    ap.add_argument('--truth',required=True);ap.add_argument('--out',required=True)
    ap.add_argument('--sample-fps',type=float,default=8.0);ap.add_argument('--calibration-seconds',type=float,default=4.0)
    ap.add_argument('--model',default='yolo11n.pt');ap.add_argument('--tracker',default='bytetrack.yaml');ap.add_argument('--imgsz',type=int,default=960)
    args=ap.parse_args();out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    truth_by=load_truth(args.truth,video_start=NATIVE_START)

    all_obs={};mappings={};models={};biases={};diag={};qualities={}
    for cam in range(3):
        obs,meta=sample_track_video(getattr(args,f'cam{cam}'),cam,args.model,args.sample_fps,args.tracker,args.imgsz)
        mapping,mapdiag=map_tracks(obs,truth_by,args.calibration_seconds)
        model,bias,gdiag=fit_geometry(cam,obs,mapping,truth_by,args.calibration_seconds)
        all_obs[cam]=obs;mappings[cam]=mapping;models[cam]=model;biases[cam]=bias
        q=float(gdiag['validation']['mae_m']) if gdiag['validation']['n'] else 9.0;qualities[cam]=q
        diag[str(cam)]={'mot':meta,'raw_sampled_observations':len(obs),'unique_track_ids':len({o['tid'] for o in obs}),
                        'mapped_ids':sorted(set(mapping.values())),'mapped_tracks':mapdiag,'geometry':gdiag}
        np.save(out/f'cam{cam}_H.npy',model.H)
        print('cam',cam,json.dumps(diag[str(cam)],indent=2),flush=True)

    rows,total_gt,total_det=fuse_holdout(all_obs,mappings,models,biases,qualities,truth_by,args.calibration_seconds)
    metrics=summarize_physical(rows,total_gt,total_det)
    mapped_ids=sorted(set().union(*[set(m.values()) for m in mappings.values()]))
    metrics.update({'version':'v18-full-frame-bytetrack','identity_frozen_holdout':True,'post_holdout_gt_relinking':False,
                    'tracker':args.tracker,'tracking_frame_rate':'every video frame','evaluation_sample_fps':args.sample_fps,
                    'identity_id_coverage':len(mapped_ids)/len(TARGET_IDS),'mapped_gt_ids':mapped_ids,
                    'camera_diagnostics':diag,'truth_source':'20Hz sensor XY',
                    'note':'MOT runs on every frame; player-ID mapping and geometry use only t<=4s; holdout GT is evaluation only'})
    pd.DataFrame(rows).to_csv(out/'matched_observations.csv',index=False)
    (out/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    print(json.dumps(metrics,indent=2),flush=True)

if __name__=='__main__':main()
