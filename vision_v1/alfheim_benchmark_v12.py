from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

import alfheim_benchmark_v9 as v9
import alfheim_benchmark_v10 as v10
import alfheim_benchmark_v11 as v11
from alfheim_benchmark import load_truth, truth_at

NATIVE_START=v9.NATIVE_START
TARGET_IDS=v9.TARGET_IDS
TRAIN_END=3.0


def label_examples(frames, model, end_t, start_t=-1e9):
    pos=[]; neg=[]; diag={'positive':0,'negative':0,'ambiguous':0}
    for f in frames:
        if not (start_t < f['t'] <= end_t): continue
        ds=f['det']
        if not ds: continue
        pred=model.project(np.asarray([d['foot'] for d in ds],float))
        pairs=v9.hungarian_pairs(pred,f['gt'],4.5)
        matched={i:c for i,j,c in pairs if c<=3.7}
        G=np.asarray([[g['x'],g['y']] for g in f['gt']],float)
        nearest=np.min(np.linalg.norm(pred[:,None,:]-G[None,:,:],axis=2),axis=1) if len(G) else np.full(len(ds),99.)
        for i,d in enumerate(ds):
            if i in matched:
                pos.append(d['kit_feat']); diag['positive']+=1
            elif nearest[i]>=5.7:
                neg.append(d['kit_feat']); diag['negative']+=1
            else:
                diag['ambiguous']+=1
    return pos,neg,diag


class RidgeKitClassifier:
    def __init__(self,med,scale,w,b,pos_z,neg_z):
        self.med=np.asarray(med,float);self.scale=np.asarray(scale,float);self.w=np.asarray(w,float);self.b=float(b)
        self.pos_z=np.asarray(pos_z,float);self.neg_z=np.asarray(neg_z,float);self.threshold=0.0
    def raw_score(self,d):
        z=(np.asarray(d['kit_feat'],float)-self.med)/self.scale
        linear=float(z@self.w+self.b)
        # Local prototype margin makes the classifier robust to mild nonlinear
        # colour changes caused by scale/illumination without using holdout GT.
        dp=np.linalg.norm(self.pos_z-z,axis=1); dn=np.linalg.norm(self.neg_z-z,axis=1)
        kp=float(np.mean(np.partition(dp,min(2,len(dp)-1))[:min(3,len(dp))]))
        kn=float(np.mean(np.partition(dn,min(4,len(dn)-1))[:min(5,len(dn))]))
        return linear + .45*(kn-kp)
    def annotate(self,frames,max_per_frame=11):
        for f in frames:
            for d in f['det']:
                d['team_score_v12']=self.raw_score(d);d['team_keep']=False
            cand=[d for d in f['det'] if d['team_score_v12']>=self.threshold]
            cand.sort(key=lambda d:(d['team_score_v12'],d['conf']),reverse=True)
            for d in cand[:max_per_frame]: d['team_keep']=True
    def keep(self,d):return bool(d.get('team_keep',False))


def fit_pooled_classifier(cams):
    all_pos=[];all_neg=[];per={}
    for cam in range(3):
        p,n,diag=label_examples(cams[cam],v10.seed_model(cam),TRAIN_END)
        all_pos+=p;all_neg+=n;per[str(cam)]=diag
    X=np.asarray(all_pos+all_neg,float);y=np.r_[np.ones(len(all_pos)),np.zeros(len(all_neg))]
    if len(all_pos)<20 or len(all_neg)<20:raise RuntimeError('Insufficient calibration labels')
    med,scale=v11.robust_scale(X);Z=(X-med)/scale
    P=Z[y==1];N=Z[y==0];mp=P.mean(axis=0);mn=N.mean(axis=0)
    Cp=np.cov(P,rowvar=False) if len(P)>1 else np.eye(Z.shape[1]);Cn=np.cov(N,rowvar=False) if len(N)>1 else np.eye(Z.shape[1])
    cov=.5*(Cp+Cn);lam=max(.35,float(np.median(np.diag(cov)))*.8)
    w=np.linalg.solve(cov+lam*np.eye(cov.shape[0]),mp-mn)
    # Equal class priors: imbalance must not move the decision boundary.
    b=-.5*float((mp+mn)@w)
    clf=RidgeKitClassifier(med,scale,w,b,P,N)
    return clf,{'pooled_positive':len(P),'pooled_negative':len(N),'per_camera_train_labels':per,'ridge_lambda':lam}


def frame_selection(f,clf,threshold,max_per_frame=11):
    scored=[(clf.raw_score(d),d) for d in f['det']]
    cand=[x for x in scored if x[0]>=threshold]
    cand.sort(key=lambda x:(x[0],x[1]['conf']),reverse=True)
    return [d for s,d in cand[:max_per_frame]]


def tune_camera_threshold(cam,frames,clf):
    vals=[]
    for f in frames:
        if TRAIN_END < f['t'] <= 4.0:
            vals += [clf.raw_score(d) for d in f['det']]
    if not vals:return 1e9,{'enabled':False,'reason':'no_validation_scores'}
    cand=np.unique(np.r_[np.quantile(vals,np.linspace(.02,.98,49)),min(vals)-1e-6,max(vals)+1e-6])
    rows=[];max_matches=1
    model=v10.seed_model(cam)
    for th in cand:
        nm=nd=0;cost=[];counts=[]
        for f in frames:
            if not (TRAIN_END < f['t'] <= 4.0):continue
            ds=frame_selection(f,clf,float(th));counts.append(len(ds));nd+=len(ds)
            pred=model.project(np.asarray([d['foot'] for d in ds],float)) if ds else np.empty((0,2))
            pairs=v9.hungarian_pairs(pred,f['gt'],4.8);nm+=len(pairs);cost += [c for _,_,c in pairs]
        max_matches=max(max_matches,nm)
        rows.append({'threshold':float(th),'matches':nm,'detections':nd,'precision':nm/max(1,nd),'mae':float(np.mean(cost)) if cost else 99.,'avg_per_frame':float(np.mean(counts)) if counts else 0.})
    best=None
    for q in rows:
        cov=q['matches']/max_matches;p=q['precision'];beta2=.5**2
        f05=(1+beta2)*p*cov/max(1e-9,beta2*p+cov)
        q['coverage_proxy']=cov;q['f05']=f05
        feasible=q['matches']>=4 and p>=.50 and q['avg_per_frame']<=9.5
        q['feasible']=feasible;q['objective']=f05+.10*cov-.010*q['mae']
        rank=(1 if feasible else 0,q['objective'],p,q['matches'])
        if best is None or rank>best[0]:best=(rank,q)
    q=best[1];q['enabled']=bool(q['feasible'])
    if not q['enabled']:q['reason']='temporal_validation_health_gate'
    return float(q['threshold']),q


def stable_calibrate(cam,frames,clf):
    seed=v10.seed_model(cam);candidates=[('seed',seed)]
    model=seed
    for it,gate in enumerate([5.0,3.5,2.6]):
        P,W,c=v10.collect_pairs(frames,clf,model,TRAIN_END,gate)
        if len(P)<8:break
        model=v10.fit_pure_h(P,W,cam,1.25)
        candidates.append((f'refine_{it}',model))
    scored=[]
    for name,m in candidates:
        q=v10.geom_quality(frames,clf,m,TRAIN_END,4.0,4.0)
        # Validation coverage matters as well as MAE.
        score=q['mae_m']+1.4*(1-q['precision_proxy'])-.025*q['matched']
        scored.append({'name':name,'score':score,'validation':q,'model':m})
    best=min(scored,key=lambda x:x['score'])
    hist=[{'name':x['name'],'score':x['score'],'validation':x['validation']} for x in scored]
    return best['model'],hist


def main():
    ap=argparse.ArgumentParser()
    for i in range(3):ap.add_argument(f'--cam{i}',required=True)
    ap.add_argument('--truth',required=True);ap.add_argument('--out',required=True);ap.add_argument('--sample-fps',type=float,default=8.0);ap.add_argument('--calibration-seconds',type=float,default=4.0);ap.add_argument('--model',default='yolo11n.pt')
    args=ap.parse_args();out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    from ultralytics import YOLO
    detector=YOLO(args.model);truth_by=load_truth(args.truth,video_start=NATIVE_START)
    caps={i:cv2.VideoCapture(getattr(args,f'cam{i}')) for i in range(3)};dur=min(cap.get(cv2.CAP_PROP_FRAME_COUNT)/float(cap.get(cv2.CAP_PROP_FPS) or 30) for cap in caps.values());times=np.arange(.4,max(.41,dur-.2),1./args.sample_fps);cams={i:[] for i in range(3)}
    for ti,t in enumerate(times):
        gt=truth_at(truth_by,float(t))
        for cam,cap in caps.items():
            cap.set(cv2.CAP_PROP_POS_MSEC,float(t*1000));ok,frame=cap.read()
            if not ok:continue
            raw=v9.detect_native(detector,frame)
            for d in raw:d['kit_feat']=v11.kit_feature(frame,d['box'])
            det=v10.on_pitch(cam,raw);cams[cam].append({'t':float(t),'det':det,'gt':gt})
        if ti%8==0:print(f't={t:.2f}s pitch_det='+','.join(f'c{c}:{len(cams[c][-1]["det"])}' for c in range(3)),flush=True)
    for cap in caps.values():cap.release()

    baseclf,traininfo=fit_pooled_classifier(cams);classifiers={};models={};diagnostics={};enabled=[]
    for cam in range(3):
        # Same pooled appearance model, camera-specific threshold chosen only on
        # the reserved 3-4 s calibration validation interval.
        import copy
        clf=copy.deepcopy(baseclf);th,val=tune_camera_threshold(cam,cams[cam],clf);clf.threshold=th;clf.annotate(cams[cam])
        diagnostics[str(cam)]={'team_validation':val}
        if not val.get('enabled',False):
            print('cam',cam,'DISABLED',json.dumps(val),flush=True);continue
        model,hist=stable_calibrate(cam,cams[cam],clf);hold=v10.holdout_geom(cams[cam],clf,model,4.0)
        classifiers[cam]=clf;models[cam]=model;enabled.append(cam);diagnostics[str(cam)].update({'geometry_selection':hist,'holdout_geometry':hold});np.save(out/f'cam{cam}_H.npy',model.H)
        print('cam',cam,json.dumps(diagnostics[str(cam)],indent=2),flush=True)
    if not enabled:raise RuntimeError('No camera passed temporal calibration validation')

    frames=[]
    for idx,t in enumerate(times):
        entries={c:cams[c][idx] for c in enabled if idx<len(cams[c])};frames.append({'t':float(t),'fused':v10.fuse_frame(entries,classifiers,models)})
    tracks=v10.track_world(frames);mapping,maprows=v10.map_tracks(tracks,truth_by,4.0);fused_count=sum(len(f['fused']) for f in frames if f['t']>4.0);metrics,rows=v10.persistent_eval(tracks,mapping,truth_by,times,4.0,fused_count)
    metrics['fused_geometry_only']=v10.geometry_eval(frames,truth_by,4.0);metrics.update({'version':'v12-supervised-kit-temporal-validation','video_duration_s':dur,'sample_fps':args.sample_fps,'calibration_seconds':4.0,'classifier_training':traininfo,'camera_diagnostics':diagnostics,'track_identity_mapping':maprows,'enabled_cameras':enabled,'post_holdout_relinking':False,'truth_source':'20Hz sensor XY'})
    pd.DataFrame(rows).to_csv(out/'matched_observations.csv',index=False);(out/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8');(out/'track_identity_mapping.json').write_text(json.dumps(maprows,indent=2),encoding='utf-8');print(json.dumps(metrics,indent=2),flush=True)

if __name__=='__main__':main()
