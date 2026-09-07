from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

import alfheim_benchmark_v9 as v9
import alfheim_benchmark_v10 as v10
from alfheim_benchmark import load_truth, truth_at

NATIVE_START = v9.NATIVE_START
TARGET_IDS = v9.TARGET_IDS


def kit_feature(frame, box):
    """Lighting-tolerant upper-torso colour descriptor.

    V9/V10 appearance crops contained a lot of green pitch.  This descriptor
    uses only the central upper body and removes grass-coloured pixels before
    computing colour statistics.  No sensor information is used here.
    """
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = map(float, box)
    bw = max(3.0, x2-x1); bh = max(6.0, y2-y1)
    xa=max(0,int(x1+.18*bw)); xb=min(w,int(x2-.18*bw))
    ya=max(0,int(y1+.05*bh)); yb=min(h,int(y1+.52*bh))
    crop=frame[ya:yb,xa:xb]
    if crop.size == 0:
        return np.zeros(29,np.float32)
    crop=cv2.resize(crop,(24,32),interpolation=cv2.INTER_AREA)
    hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
    lab=cv2.cvtColor(crop,cv2.COLOR_BGR2LAB)
    H,S,V=cv2.split(hsv); B,G,R=cv2.split(crop)
    # Remove saturated green turf. Keep white fabric (low saturation) and dark
    # kit pixels because both are identity-bearing.
    green=(H>=30)&(H<=95)&(S>42)&(V>35)
    valid=(V>28)&(~green)
    if int(valid.sum()) < 35:
        valid=V>28
    b=B[valid].astype(float); g=G[valid].astype(float); r=R[valid].astype(float)
    den=r+g+b+1e-6; rc=r/den; gc=g/den; bc=b/den
    hh=H[valid].astype(float); ss=S[valid].astype(float); vv=V[valid].astype(float)
    weights=(.25+.75*ss/255.)*(.35+.65*vv/255.)
    hist,_=np.histogram(hh,bins=10,range=(0,180),weights=weights)
    hist=hist/(hist.sum()+1e-8)
    def q(a,p): return float(np.percentile(a,p)) if len(a) else 0.0
    chrom=[q(rc,25),q(rc,50),q(rc,75),q(gc,25),q(gc,50),q(gc,75),q(bc,25),q(bc,50),q(bc,75)]
    La=lab[:,:,1][valid].astype(float); Lb=lab[:,:,2][valid].astype(float)
    extra=[
        q(La,50)/255., q(Lb,50)/255., float(np.mean(ss))/255., float(np.mean(vv))/255.,
        float(((S<48)&(V>135)).mean()),                       # white
        float((V<82).mean()),                                # dark
        float((((H<13)|(H>168))&(S>60)&(V>55)).mean()),      # red
        float(((H>=95)&(H<=135)&(S>45)&(V>35)).mean()),      # blue
        float(((H>=16)&(H<=35)&(S>65)&(V>80)).mean()),       # yellow/ref
        float(valid.mean()),
    ]
    return np.r_[hist,chrom,extra].astype(np.float32)


def robust_scale(X):
    X=np.asarray(X,float); med=np.median(X,axis=0); mad=np.median(np.abs(X-med),axis=0)
    scale=1.4826*mad
    # Stable fallback for nearly constant dimensions.
    std=X.std(axis=0)
    scale=np.where(scale>1e-3,scale,np.where(std>1e-3,std,1.0))
    return med,scale


def kmeans_np(Z,k,seed=100):
    Z=np.asarray(Z,float); n=len(Z); rng=np.random.default_rng(seed+k)
    # kmeans++ deterministic under fixed RNG.
    centers=[Z[int(rng.integers(n))]]
    while len(centers)<k:
        D=np.min(np.stack([np.sum((Z-c)**2,axis=1) for c in centers]),axis=0)
        s=float(D.sum())
        idx=int(rng.integers(n)) if s<=1e-12 else int(rng.choice(n,p=D/s))
        centers.append(Z[idx])
    C=np.asarray(centers,float)
    labels=np.zeros(n,int)
    for _ in range(80):
        D=np.linalg.norm(Z[:,None,:]-C[None,:,:],axis=2); new=np.argmin(D,axis=1)
        newC=C.copy()
        for j in range(k):
            pts=Z[new==j]
            if len(pts): newC[j]=np.median(pts,axis=0)
        if np.array_equal(new,labels) and np.max(np.abs(newC-C))<1e-6: break
        labels=new; C=newC
    return C,labels


class KitClassifier:
    def __init__(self, med, scale, centers, selected_clusters, max_per_frame=11):
        self.med=np.asarray(med,float); self.scale=np.asarray(scale,float); self.centers=np.asarray(centers,float)
        self.selected_clusters=set(int(x) for x in selected_clusters); self.max_per_frame=int(max_per_frame)
    def annotate(self, frames):
        for f in frames:
            if not f['det']: continue
            Z=np.asarray([(d['kit_feat']-self.med)/self.scale for d in f['det']],float)
            D=np.linalg.norm(Z[:,None,:]-self.centers[None,:,:],axis=2); lab=np.argmin(D,axis=1)
            for d,l,row in zip(f['det'],lab,D):
                d['kit_cluster']=int(l)
                ds=float(np.min(row[list(self.selected_clusters)])) if self.selected_clusters else 99.
                other=[i for i in range(len(self.centers)) if i not in self.selected_clusters]
                do=float(np.min(row[other])) if other else ds+5.
                d['kit_margin']=do-ds
                d['team_keep']=False
            cand=[d for d in f['det'] if d['kit_cluster'] in self.selected_clusters]
            # A football team cannot contribute more than eleven players to one
            # camera frame.  If a kit cluster also catches staff/reflections,
            # keep the eleven most cluster-confident observations.
            cand.sort(key=lambda d:(d['kit_margin'],d['conf']),reverse=True)
            for d in cand[:self.max_per_frame]: d['team_keep']=True
    def keep(self,d): return bool(d.get('team_keep',False))


def eval_subset(frames, labels_by_frame, subset, seed_model, calibration_seconds):
    nm=nd=0; costs=[]; per_frame=[]
    for f,labs in zip(frames,labels_by_frame):
        if f['t']>calibration_seconds: continue
        idx=[i for i,l in enumerate(labs) if int(l) in subset]
        if len(idx)>11:
            # For calibration scoring only, do not reward cluster subsets that
            # routinely contain more than one entire football team.
            idx=idx[:11]
        ds=[f['det'][i] for i in idx]
        pix=np.asarray([d['foot'] for d in ds],float) if ds else np.empty((0,2))
        pred=seed_model.project(pix) if len(pix) else np.empty((0,2))
        pairs=v9.hungarian_pairs(pred,f['gt'],5.0)
        nm+=len(pairs); nd+=len(ds); costs += [c for _,_,c in pairs]; per_frame.append(len(ds))
    return {'matches':nm,'detections':nd,'precision':nm/max(1,nd),'mae':float(np.mean(costs)) if costs else 99.,'avg_per_frame':float(np.mean(per_frame)) if per_frame else 0.}


def learn_kit_classifier(cam,frames,calibration_seconds):
    feats=[]; refs=[]
    for fi,f in enumerate(frames):
        if f['t']>calibration_seconds: continue
        for di,d in enumerate(f['det']): feats.append(d['kit_feat']); refs.append((fi,di))
    X=np.asarray(feats,float)
    if len(X)<20: return None,{'enabled':False,'reason':'too_few_calibration_detections'}
    med,scale=robust_scale(X); Z=(X-med)/scale
    best=None; best_pack=None
    for k in [3,4,5,6]:
        if len(Z)<k*4: continue
        centers,labels=kmeans_np(Z,k,seed=700+cam*17)
        labels_by=[np.empty(0,int) for _ in frames]
        by={}
        for (fi,di),lab in zip(refs,labels): by.setdefault(fi,{})[di]=int(lab)
        for fi,f in enumerate(frames):
            if f['t']<=calibration_seconds:
                labels_by[fi]=np.asarray([by.get(fi,{}).get(i,-1) for i in range(len(f['det']))],int)
            elif f['det']:
                ZZ=np.asarray([(d['kit_feat']-med)/scale for d in f['det']],float)
                labels_by[fi]=np.argmin(np.linalg.norm(ZZ[:,None,:]-centers[None,:,:],axis=2),axis=1)
        max_matches=1; rows=[]
        for r in range(1,min(k,3)+1):
            for tup in itertools.combinations(range(k),r):
                q=eval_subset(frames,labels_by,set(tup),v10.seed_model(cam),calibration_seconds)
                max_matches=max(max_matches,q['matches']); q.update({'clusters':list(tup),'k':k}); rows.append(q)
        for q in rows:
            cov=q['matches']/max_matches
            p=q['precision']; beta2=.5**2
            f05=(1+beta2)*p*cov/max(1e-9,beta2*p+cov)
            q['coverage_proxy']=cov; q['f05']=f05
            # Precision first: V10 cam2 kept 550 detections for 11 matches.
            q['objective']=f05 + .08*cov - .012*q['mae'] - .018*max(0.,q['avg_per_frame']-8.)
            feasible=(q['matches']>=6 and q['precision']>=.42 and q['avg_per_frame']<=11.0)
            q['feasible']=feasible
            rank=(1 if feasible else 0,q['objective'],q['precision'],q['matches'])
            if best is None or rank>best[0]: best=(rank,q); best_pack=(med,scale,centers)
    if best is None: return None,{'enabled':False,'reason':'no_cluster_model'}
    q=best[1]; clf=KitClassifier(*best_pack,q['clusters']); clf.annotate(frames)
    # Re-evaluate exact annotated/capped classifier on calibration.
    nm=nd=0; costs=[]
    for f in frames:
        if f['t']>calibration_seconds:continue
        ds=[d for d in f['det'] if clf.keep(d)]; nd+=len(ds)
        pred=v10.seed_model(cam).project(np.asarray([d['foot'] for d in ds],float)) if ds else np.empty((0,2))
        pairs=v9.hungarian_pairs(pred,f['gt'],5.0);nm+=len(pairs);costs += [c for _,_,c in pairs]
    precision=nm/max(1,nd); mae=float(np.mean(costs)) if costs else 99.
    enabled=bool(nm>=6 and precision>=.38 and mae<=3.5)
    info={'enabled':enabled,'k':q['k'],'selected_clusters':q['clusters'],'matches':nm,'detections':nd,'precision':precision,'mae_m':mae,'selection':q}
    if not enabled: info['reason']='camera_team_health_gate'
    return clf,info


def geom_calibrate(cam,frames,clf,calibration_seconds):
    return v10.calibrate_camera_cv(cam,frames,clf,calibration_seconds)


def two_camera_geometry(frames,truth_by,calibration_seconds):
    return v10.geometry_eval(frames,truth_by,calibration_seconds)


def main():
    ap=argparse.ArgumentParser()
    for i in range(3): ap.add_argument(f'--cam{i}',required=True)
    ap.add_argument('--truth',required=True); ap.add_argument('--out',required=True)
    ap.add_argument('--sample-fps',type=float,default=8.0); ap.add_argument('--calibration-seconds',type=float,default=4.0); ap.add_argument('--model',default='yolo11n.pt')
    args=ap.parse_args(); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    from ultralytics import YOLO
    detector=YOLO(args.model); truth_by=load_truth(args.truth,video_start=NATIVE_START)
    caps={i:cv2.VideoCapture(getattr(args,f'cam{i}')) for i in range(3)}
    dur=min(cap.get(cv2.CAP_PROP_FRAME_COUNT)/float(cap.get(cv2.CAP_PROP_FPS) or 30) for cap in caps.values())
    times=np.arange(.4,max(.41,dur-.2),1./args.sample_fps); cams={i:[] for i in range(3)}
    for ti,t in enumerate(times):
        gt=truth_at(truth_by,float(t))
        for cam,cap in caps.items():
            cap.set(cv2.CAP_PROP_POS_MSEC,float(t*1000)); ok,frame=cap.read()
            if not ok: continue
            raw=v9.detect_native(detector,frame)
            for d in raw: d['kit_feat']=kit_feature(frame,d['box'])
            det=v10.on_pitch(cam,raw)
            cams[cam].append({'t':float(t),'det':det,'gt':gt})
        if ti%8==0: print(f't={t:.2f}s pitch_det='+','.join(f'c{c}:{len(cams[c][-1]["det"])}' for c in range(3)),flush=True)
    for cap in caps.values(): cap.release()

    classifiers={}; models={}; diagnostics={}; enabled=[]
    for cam in range(3):
        clf,team=learn_kit_classifier(cam,cams[cam],args.calibration_seconds)
        diagnostics[str(cam)]={'team':team}
        if clf is None or not team.get('enabled',False):
            print('cam',cam,'DISABLED',json.dumps(team),flush=True); continue
        model,hist=geom_calibrate(cam,cams[cam],clf,args.calibration_seconds)
        hold=v10.holdout_geom(cams[cam],clf,model,args.calibration_seconds)
        # Geometry health is calibration-independent only for reporting here;
        # enabling is based solely on calibration team health above to avoid
        # tuning on holdout truth.
        classifiers[cam]=clf; models[cam]=model; enabled.append(cam)
        diagnostics[str(cam)].update({'calibration_history':hist,'holdout_geometry':hold})
        np.save(out/f'cam{cam}_H.npy',model.H)
        print('cam',cam,json.dumps(diagnostics[str(cam)],indent=2),flush=True)
    if not enabled: raise RuntimeError('No healthy native camera after calibration')

    frames=[]; frames01=[]
    for idx,t in enumerate(times):
        entries={c:cams[c][idx] for c in enabled if idx<len(cams[c])}
        fused=v10.fuse_frame(entries,classifiers,models)
        frames.append({'t':float(t),'fused':fused})
        entries01={c:cams[c][idx] for c in enabled if c in (0,1) and idx<len(cams[c])}
        fused01=v10.fuse_frame(entries01,classifiers,models) if entries01 else []
        frames01.append({'t':float(t),'fused':fused01})

    tracks=v10.track_world(frames); mapping,maprows=v10.map_tracks(tracks,truth_by,args.calibration_seconds)
    fused_count=sum(len(f['fused']) for f in frames if f['t']>args.calibration_seconds)
    metrics,rows=v10.persistent_eval(tracks,mapping,truth_by,times,args.calibration_seconds,fused_count)
    metrics['fused_geometry_only']=v10.geometry_eval(frames,truth_by,args.calibration_seconds)
    metrics['diagnostic_cam01_geometry']=two_camera_geometry(frames01,truth_by,args.calibration_seconds)
    metrics.update({'version':'v11-kit-cluster-camera-health','video_duration_s':dur,'sample_fps':args.sample_fps,'calibration_seconds':args.calibration_seconds,'camera_diagnostics':diagnostics,'track_identity_mapping':maprows,'enabled_cameras':enabled,'post_holdout_relinking':False,'truth_source':'20Hz sensor XY'})
    pd.DataFrame(rows).to_csv(out/'matched_observations.csv',index=False)
    (out/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8'); (out/'track_identity_mapping.json').write_text(json.dumps(maprows,indent=2),encoding='utf-8')
    print(json.dumps(metrics,indent=2),flush=True)


if __name__=='__main__': main()
