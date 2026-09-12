from __future__ import annotations
import argparse, json, math
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from alfheim_benchmark import detect_tiled, load_truth, truth_at
from alfheim_benchmark_v3 import (
    appearance_feature,
    cluster_appearance,
    choose_cluster_subset,
    iterative_calibration,
    project_geometry,
    summarize,
)


def cosine_distance(a, b):
    a=np.asarray(a,float); b=np.asarray(b,float)
    na=np.linalg.norm(a); nb=np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9: return 1.0
    return float(1.0 - np.dot(a,b)/(na*nb))


@dataclass
class Track:
    tid: int
    last_t: float
    last_xy: np.ndarray
    velocity: np.ndarray
    feat: np.ndarray
    obs: list = field(default_factory=list)
    hits: int = 0


def build_tracks(frames, selected, coef, max_gap=0.85):
    """Track selected-team detections without looking at ground truth.

    Association uses only projected camera coordinates + appearance and a
    constant-velocity prediction. This is intentionally independent of the
    sensor labels used later for validation.
    """
    tracks=[]; next_id=1
    for fi,f in enumerate(frames):
        persons=[d for d in f['all_persons'] if d['cluster'] in selected]
        pix=np.asarray([d['foot'] for d in persons],float) if persons else np.empty((0,2))
        xy=project_geometry(pix,coef) if len(pix) else np.empty((0,2))
        feats=[d['feat'] for d in persons]
        t=float(f['t'])
        active=[tr for tr in tracks if 0 < t-tr.last_t <= max_gap]
        assigned_det=set(); assigned_track=set()
        if active and len(xy):
            C=np.full((len(active),len(xy)),1e6,float)
            for i,tr in enumerate(active):
                dt=max(1e-3,t-tr.last_t)
                predicted=tr.last_xy + tr.velocity*dt
                for j,pos in enumerate(xy):
                    spatial=float(np.linalg.norm(pos-predicted))
                    app=cosine_distance(tr.feat,feats[j])
                    # At 4 Hz a footballer normally moves <3 m between samples.
                    # Allow a wider gate for detector jitter / brief misses.
                    gate=min(8.0, max(3.0, 1.0 + 11.0*dt))
                    if spatial <= gate and app <= 0.70:
                        C[i,j]=spatial + 1.8*app
            ri,ci=linear_sum_assignment(C)
            for i,j in zip(ri,ci):
                if C[i,j] >= 1e5: continue
                tr=active[i]; dt=max(1e-3,t-tr.last_t)
                measured=(xy[j]-tr.last_xy)/dt
                speed=float(np.linalg.norm(measured))
                if speed > 14.0: continue
                tr.velocity = 0.65*tr.velocity + 0.35*measured
                tr.last_xy=xy[j].copy(); tr.last_t=t
                tr.feat=0.85*tr.feat + 0.15*np.asarray(feats[j],float)
                tr.hits += 1
                tr.obs.append({'fi':fi,'t':t,'xy':xy[j].copy(),'pix':pix[j].copy(),'det_index':j})
                assigned_det.add(j); assigned_track.add(tr.tid)
        for j,pos in enumerate(xy):
            if j in assigned_det: continue
            tr=Track(next_id,t,pos.copy(),np.zeros(2,float),np.asarray(feats[j],float).copy())
            tr.hits=1; tr.obs.append({'fi':fi,'t':t,'xy':pos.copy(),'pix':pix[j].copy(),'det_index':j})
            tracks.append(tr); next_id+=1
    return tracks


def map_tracks_to_truth(tracks, frames, calibration_seconds, max_median=5.5):
    """Map each camera track to at most one sensor identity using calibration only."""
    cal_tracks=[tr for tr in tracks if sum(o['t']<=calibration_seconds for o in tr.obs)>=2]
    gt_ids=sorted({g['id'] for f in frames if f['t']<=calibration_seconds for g in f['gt']})
    if not cal_tracks or not gt_ids: return {},[]
    C=np.full((len(cal_tracks),len(gt_ids)),1e4,float); detail={}
    for i,tr in enumerate(cal_tracks):
        for j,gid in enumerate(gt_ids):
            ds=[]
            for o in tr.obs:
                if o['t']>calibration_seconds: continue
                gt={g['id']:g for g in frames[o['fi']]['gt']}
                if gid in gt:
                    ds.append(float(np.linalg.norm(o['xy']-np.array([gt[gid]['x'],gt[gid]['y']],float))))
            if len(ds)>=2:
                med=float(np.median(ds)); p90=float(np.percentile(ds,90))
                # Prefer sustained low-error identity evidence over one lucky hit.
                score=med + .20*p90 + .35/max(1,len(ds))
                C[i,j]=score; detail[(i,j)]=(med,p90,len(ds),score)
    ri,ci=linear_sum_assignment(C)
    mapping={}; rows=[]
    for i,j in zip(ri,ci):
        if (i,j) not in detail: continue
        med,p90,n,score=detail[(i,j)]
        if med>max_median: continue
        tid=cal_tracks[i].tid; gid=gt_ids[j]
        mapping[tid]=gid
        rows.append({'track_id':tid,'gt_id':gid,'calibration_median_m':med,'calibration_p90_m':p90,'calibration_samples':n,'assignment_score':score})
    return mapping,rows


def evaluate(tracks, mapping, frames, calibration_seconds, outdir):
    rows=[]
    total_gt=sum(len(f['gt']) for f in frames if f['t']>calibration_seconds)
    total_det=0
    mapped_obs=0
    first_eval=None
    for f in frames:
        if f['t']>calibration_seconds:
            total_det += sum(1 for tr in tracks for o in tr.obs if o['fi']==frames.index(f))
    # Avoid frames.index() ambiguity/cost in actual row pass.
    total_det=sum(1 for tr in tracks for o in tr.obs if o['t']>calibration_seconds)
    for tr in tracks:
        gid=mapping.get(tr.tid)
        if gid is None: continue
        for o in tr.obs:
            if o['t']<=calibration_seconds: continue
            f=frames[o['fi']]; gt={g['id']:g for g in f['gt']}
            if gid not in gt: continue
            g=gt[gid]; err=float(np.linalg.norm(o['xy']-np.array([g['x'],g['y']],float)))
            # Evaluation is identity-frozen: no nearest-GT reassignment here.
            rows.append({'t':o['t'],'track_id':tr.tid,'gt_id':gid,'pred_x':o['xy'][0],'pred_y':o['xy'][1],
                         'truth_x':g['x'],'truth_y':g['y'],'position_error_m':err,'truth_speed':g['speed'],
                         'truth_total_distance':g['total_distance'],'pixel_x':o['pix'][0],'pixel_y':o['pix'][1]})
            mapped_obs+=1
            if first_eval is None: first_eval=o['fi']
    df=pd.DataFrame(rows)
    df.to_csv(outdir/'matched_observations.csv',index=False)
    metrics=summarize(rows,total_gt,total_det)
    metrics['mapped_track_observations']=mapped_obs
    metrics['mapped_tracks']=len(mapping)
    metrics['all_tracks']=len(tracks)
    metrics['identity_frozen_holdout']=True
    # Add continuity diagnostics.
    lengths=[sum(o['t']>calibration_seconds for o in tr.obs) for tr in tracks if tr.tid in mapping]
    metrics['mapped_track_mean_holdout_samples']=float(np.mean(lengths)) if lengths else 0.0
    metrics['mapped_track_max_holdout_samples']=int(max(lengths)) if lengths else 0
    if first_eval is not None:
        img=frames[first_eval]['frame'].copy()
        for tr in tracks:
            gid=mapping.get(tr.tid)
            if gid is None: continue
            cand=[o for o in tr.obs if o['fi']==first_eval]
            for o in cand:
                x,y=map(int,o['pix']); cv2.circle(img,(x,y),10,(0,255,0),3)
                cv2.putText(img,f'T{tr.tid}->GT{gid}',(x+8,y-8),0,.55,(0,255,0),2)
        cv2.imwrite(str(outdir/'annotated_eval_frame.jpg'),img)
    return metrics


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--video',required=True); ap.add_argument('--truth',required=True); ap.add_argument('--out',required=True)
    ap.add_argument('--sample-fps',type=float,default=4.0); ap.add_argument('--calibration-seconds',type=float,default=3.0)
    ap.add_argument('--model',default='yolo11n.pt')
    args=ap.parse_args(); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    from ultralytics import YOLO
    model=YOLO(args.model); truth_by=load_truth(args.truth)
    cap=cv2.VideoCapture(args.video); fps=float(cap.get(cv2.CAP_PROP_FPS) or 25); dur=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))/fps
    times=np.arange(.5,max(.51,dur-.25),1/args.sample_fps); frames=[]
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC,float(t*1000)); ok,frame=cap.read()
        if not ok: continue
        persons=[d for d in detect_tiled(model,frame) if d['cls']=='person']
        for d in persons: d['feat']=appearance_feature(frame,d['box'])
        frames.append({'t':float(t),'frame':frame,'all_persons':persons,'gt':truth_at(truth_by,float(t))})
        print(f't={t:.2f}s people={len(persons)}',flush=True)
    cap.release()
    k=4; cluster_appearance(frames,args.calibration_seconds,k)
    selected,tuning=choose_cluster_subset(frames,args.calibration_seconds,k)
    print('selected_clusters=',sorted(selected),flush=True)
    (out/'cluster_tuning.json').write_text(json.dumps(tuning,indent=2),encoding='utf-8')
    coef,calhist=iterative_calibration(frames,args.calibration_seconds,selected)
    np.save(out/'pixel_to_world_poly2.npy',coef)
    (out/'calibration_history.json').write_text(json.dumps(calhist,indent=2),encoding='utf-8')
    tracks=build_tracks(frames,selected,coef)
    mapping,maprows=map_tracks_to_truth(tracks,frames,args.calibration_seconds)
    print('track_mapping=',maprows,flush=True)
    (out/'track_identity_mapping.json').write_text(json.dumps(maprows,indent=2),encoding='utf-8')
    metrics=evaluate(tracks,mapping,frames,args.calibration_seconds,out)
    metrics.update({'version':'v4-persistent-identity','video_duration_s':dur,'sample_fps':args.sample_fps,
                    'calibration_seconds':args.calibration_seconds,'model':args.model,'selected_clusters':sorted(selected),
                    'calibration_history':calhist})
    (out/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    print(json.dumps(metrics,indent=2),flush=True)

if __name__=='__main__': main()
