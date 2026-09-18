from __future__ import annotations

import argparse
import copy
import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

import alfheim_benchmark_v9 as v9
from alfheim_benchmark import load_truth, truth_at
from alfheim_benchmark_v7 import summarize_physical

NATIVE_START = v9.NATIVE_START
TARGET_IDS = v9.TARGET_IDS
SEED = v9.SEED

# The field itself is the strongest free detector of spectators/staff.  V9 let
# every YOLO person in the 1280x960 image enter the team classifier; on cam2
# that meant >50 people in some frames although only a small part of the team
# was on the pitch.  Project through the static line-based seed calibration and
# reject feet that clearly land outside the playable surface.
ROI_X = (-2.0, 107.0)
ROI_Y = (-2.0, 70.0)
OUT_X = (-1.0, 106.0)
OUT_Y = (-1.0, 69.0)


def seed_model(cam: int) -> v9.CameraModel:
    sp, sw = SEED[cam]
    return v9.CameraModel(cv2.getPerspectiveTransform(sp, sw), None)


def on_pitch(cam: int, detections: list[dict], model: v9.CameraModel | None = None) -> list[dict]:
    if not detections:
        return []
    model = model or seed_model(cam)
    pix = np.asarray([d['foot'] for d in detections], float)
    xy = model.project(pix)
    keep = []
    for d, p in zip(detections, xy):
        if ROI_X[0] <= p[0] <= ROI_X[1] and ROI_Y[0] <= p[1] <= ROI_Y[1]:
            x = dict(d)
            x['seed_xy'] = np.asarray(p, float)
            keep.append(x)
    return keep


def hungarian(pred, gt, gate):
    pred = np.asarray(pred, float)
    if len(pred) == 0 or not gt:
        return []
    G = np.asarray([[g['x'], g['y']] for g in gt], float)
    C = np.linalg.norm(pred[:, None, :] - G[None, :, :], axis=2)
    ri, ci = linear_sum_assignment(C)
    return [(int(i), int(j), float(C[i, j])) for i, j in zip(ri, ci) if C[i, j] <= gate]


def collect_team_examples(frames: list[dict], model: v9.CameraModel, calibration_seconds: float):
    pos_f, neg_f, pos_r, neg_r = [], [], [], []
    for f in frames:
        if f['t'] > calibration_seconds:
            continue
        ds = f['det']
        if not ds:
            continue
        pred = model.project(np.asarray([d['foot'] for d in ds], float))
        pairs = hungarian(pred, f['gt'], 5.5)
        matched = {i: c for i, _, c in pairs if c <= 4.0}
        G = np.asarray([[g['x'], g['y']] for g in f['gt']], float)
        nearest = np.min(np.linalg.norm(pred[:, None, :] - G[None, :, :], axis=2), axis=1) if len(G) else np.full(len(ds), 99.0)
        for i, d in enumerate(ds):
            if i in matched:
                pos_f.append(d['feat']); pos_r.append(d['red'])
            elif nearest[i] >= 6.5:
                neg_f.append(d['feat']); neg_r.append(d['red'])
    return pos_f, neg_f, pos_r, neg_r


def tune_threshold(clf: v9.TeamClassifier, frames: list[dict], model: v9.CameraModel, calibration_seconds: float):
    scores = []
    for f in frames:
        if f['t'] <= calibration_seconds:
            scores.extend(clf.score(d) for d in f['det'])
    if not scores:
        return 0.0, {'matches': 0, 'detections': 0}
    qs = np.unique(np.r_[np.quantile(scores, np.linspace(.03, .97, 31)), 0.0])
    rows = []
    max_matches = 1
    for th in qs:
        nm = nd = 0; costs = []
        for f in frames:
            if f['t'] > calibration_seconds:
                continue
            ds = [d for d in f['det'] if clf.score(d) >= th]
            pred = model.project(np.asarray([d['foot'] for d in ds], float)) if ds else np.empty((0, 2))
            pairs = hungarian(pred, f['gt'], 4.5)
            nm += len(pairs); nd += len(ds); costs += [c for _, _, c in pairs]
        max_matches = max(max_matches, nm)
        rows.append({'threshold': float(th), 'matches': nm, 'detections': nd,
                     'precision': nm/max(1, nd), 'mae': float(np.mean(costs)) if costs else 99.0})
    # Visible-target recall proxy: best number any threshold could match in these
    # same calibration frames.  This avoids penalising a side camera for players
    # physically outside its field of view.
    best = None
    for r in rows:
        rec = r['matches']/max_matches
        p = r['precision']; beta2 = .35**2
        f035 = (1+beta2)*p*rec/max(1e-9, beta2*p+rec)
        r['visible_recall_proxy'] = rec
        r['f035'] = f035
        r['objective'] = f035 - .012*r['mae']
        if best is None or r['objective'] > best['objective']:
            best = r
    return float(best['threshold']), best


def learn_classifiers(cams: dict[int, list[dict]], calibration_seconds: float):
    local_examples = {}
    all_pos=[]; all_neg=[]; all_pr=[]; all_nr=[]
    for cam in range(3):
        ex = collect_team_examples(cams[cam], seed_model(cam), calibration_seconds)
        local_examples[cam] = ex
        p,n,pr,nr=ex; all_pos += p; all_neg += n; all_pr += pr; all_nr += nr

    pooled = v9.TeamClassifier(); pooled.fit(all_pos, all_neg, all_pr, all_nr)
    result={}; info={}
    for cam in range(3):
        p,n,pr,nr=local_examples[cam]
        # Native cameras share the same colour pipeline.  Keep strong local
        # models for cam0/1, but cam2 in V9 had only 14 positives and collapsed;
        # sparse cameras inherit the pooled team prototype.
        if len(p) >= 35:
            clf=v9.TeamClassifier(); clf.fit(p,n,pr,nr); source='local'
        else:
            clf=copy.deepcopy(pooled); source='pooled'
        th,tune=tune_threshold(clf,cams[cam],seed_model(cam),calibration_seconds)
        clf.threshold=th
        result[cam]=clf
        info[str(cam)]={'source':source,'positive_examples':len(p),'negative_examples':len(n),'threshold_tuning':tune}
    return result,info


def selected(frame: dict, clf: v9.TeamClassifier):
    return [d for d in frame['det'] if clf.keep(d)]


def collect_pairs(frames, clf, model, end_t, gate, start_t=-1e9):
    P=[]; W=[]; costs=[]
    for f in frames:
        if not (start_t < f['t'] <= end_t):
            continue
        ds=selected(f,clf)
        pix=np.asarray([d['foot'] for d in ds],float) if ds else np.empty((0,2))
        pred=model.project(pix) if len(pix) else np.empty((0,2))
        for i,j,c in hungarian(pred,f['gt'],gate):
            P.append(pix[i]); W.append([f['gt'][j]['x'],f['gt'][j]['y']]); costs.append(c)
    return np.asarray(P,float),np.asarray(W,float),costs


def fit_pure_h(P, W, cam, ransac=1.35):
    sp,sw=SEED[cam]
    # Static pitch-line landmarks anchor the physical projective geometry.  They
    # are repeated modestly so moving-player correspondences cannot drag a
    # mathematically valid homography away from the known white lines.
    P2=np.vstack([P, np.repeat(sp,3,axis=0)]) if len(P) else np.repeat(sp,3,axis=0)
    W2=np.vstack([W, np.repeat(sw,3,axis=0)]) if len(W) else np.repeat(sw,3,axis=0)
    H,mask=cv2.findHomography(P2.astype(np.float32),W2.astype(np.float32),cv2.RANSAC,ransac,maxIters=6000,confidence=.999)
    if H is None:
        H=cv2.getPerspectiveTransform(sp,sw)
    return v9.CameraModel(H,None)


def geom_quality(frames, clf, model, lo, hi, gate=4.0):
    errs=[]; nm=nd=0
    for f in frames:
        if not (lo < f['t'] <= hi): continue
        ds=selected(f,clf); nd += len(ds)
        pred=model.project(np.asarray([d['foot'] for d in ds],float)) if ds else np.empty((0,2))
        pairs=hungarian(pred,f['gt'],gate); nm += len(pairs); errs += [c for _,_,c in pairs]
    if not errs: return {'matched':0,'detections':nd,'mae_m':99.,'p95_m':99.}
    a=np.asarray(errs,float)
    return {'matched':nm,'detections':nd,'precision_proxy':nm/max(1,nd),'mae_m':float(a.mean()),'p95_m':float(np.percentile(a,95))}


def calibrate_camera_cv(cam, frames, clf, calibration_seconds):
    seed=seed_model(cam)
    split=max(2.5,calibration_seconds-1.0)
    model=seed; history=[]
    # Fit only on the earlier portion first; the last calibration second is a
    # genuine model-selection set and remains separate from the holdout.
    for it,gate in enumerate([5.0,3.5,2.5]):
        P,W,costs=collect_pairs(frames,clf,model,split,gate)
        if len(P)<8: break
        cand=fit_pure_h(P,W,cam)
        q=geom_quality(frames,clf,cand,split,calibration_seconds)
        history.append({'phase':'cv','iteration':it,'gate_m':gate,'pairs':len(P),'validation':q})
        model=cand
    q_seed=geom_quality(frames,clf,seed,split,calibration_seconds)
    q_ref=geom_quality(frames,clf,model,split,calibration_seconds)
    maxm=max(1,q_seed['matched'],q_ref['matched'])
    def obj(q): return q['mae_m'] + 2.0*(1-q['matched']/maxm) + .5*(1-q.get('precision_proxy',0.0))
    refined_wins=obj(q_ref)+.05 < obj(q_seed)
    chosen=model if refined_wins else seed
    history.append({'phase':'selection','seed':q_seed,'refined':q_ref,'refined_wins':refined_wins})

    # Pure homography has only eight DoF, so after selecting refinement using
    # calibration-only CV we may safely refit it on the whole calibration set.
    if refined_wins:
        for it,gate in enumerate([3.5,2.5,1.9]):
            P,W,costs=collect_pairs(frames,clf,chosen,calibration_seconds,gate)
            if len(P)<8: break
            chosen=fit_pure_h(P,W,cam,1.15)
            e=np.linalg.norm(chosen.project(P)-W,axis=1)
            history.append({'phase':'final','iteration':it,'gate_m':gate,'pairs':len(P),'train_mae_m':float(e.mean()),'train_p95_m':float(np.percentile(e,95))})
    return chosen,history


def holdout_geom(frames,clf,model,calibration_seconds,gate=3.0):
    errs=[]; nm=nd=0
    for f in frames:
        if f['t']<=calibration_seconds: continue
        ds=selected(f,clf); nd+=len(ds)
        pred=model.project(np.asarray([d['foot'] for d in ds],float)) if ds else np.empty((0,2))
        pairs=hungarian(pred,f['gt'],gate); nm+=len(pairs); errs += [c for _,_,c in pairs]
    if not errs:return {'matched':0,'detections':nd}
    a=np.asarray(errs,float)
    return {'matched':nm,'detections':nd,'precision_proxy':nm/max(1,nd),'mae_m':float(a.mean()),'rmse_m':float(np.sqrt(np.mean(a*a))),'p95_m':float(np.percentile(a,95))}


def mutual_edges(obs, radius=2.35):
    edges=[]
    for ca in range(3):
        A=[i for i,o in enumerate(obs) if o['cam']==ca]
        for cb in range(ca+1,3):
            B=[i for i,o in enumerate(obs) if o['cam']==cb]
            if not A or not B: continue
            D=np.array([[np.linalg.norm(obs[i]['xy']-obs[j]['xy']) for j in B] for i in A])
            ai=np.argmin(D,axis=1); bj=np.argmin(D,axis=0)
            for ia,jb0 in enumerate(ai):
                if bj[jb0]!=ia: continue
                d=float(D[ia,jb0])
                if d<=radius: edges.append((A[ia],B[jb0],d))
    return edges


def fuse_frame(entries,classifiers,models,radius=2.35):
    obs=[]
    for cam,f in entries.items():
        ds=selected(f,classifiers[cam])
        if not ds: continue
        pix=np.asarray([d['foot'] for d in ds],float); xy=models[cam].project(pix)
        for d,p in zip(ds,xy):
            if not (OUT_X[0]<=p[0]<=OUT_X[1] and OUT_Y[0]<=p[1]<=OUT_Y[1]): continue
            obs.append({'cam':cam,'xy':np.asarray(p,float),'feat':np.asarray(d['feat'],float),'conf':float(d['conf'])})
    parent=list(range(len(obs)))
    def find(a):
        while parent[a]!=a:
            parent[a]=parent[parent[a]]; a=parent[a]
        return a
    def union(a,b):
        a,b=find(a),find(b)
        if a!=b: parent[b]=a
    for a,b,d in sorted(mutual_edges(obs,radius),key=lambda x:x[2]): union(a,b)
    groups={}
    for i in range(len(obs)): groups.setdefault(find(i),[]).append(i)
    fused=[]
    for ids in groups.values():
        # Never let a transitive component contribute two detections from the
        # same camera; keep its strongest observation.
        per={}
        for i in ids:
            o=obs[i]
            if o['cam'] not in per or o['conf']>per[o['cam']]['conf']: per[o['cam']]=o
        items=list(per.values()); w=np.asarray([max(.08,o['conf']) for o in items],float); w/=w.sum()
        xy=sum(wi*o['xy'] for wi,o in zip(w,items)); feat=sum(wi*o['feat'] for wi,o in zip(w,items))
        fused.append({'xy':np.asarray(xy,float),'feat':np.asarray(feat,float),'conf':max(o['conf'] for o in items),'cams':tuple(sorted(o['cam'] for o in items))})
    return fused


@dataclass
class Track:
    tid:int
    obs:list=field(default_factory=list)
    miss:float=0.0
    def pred(self,t):
        if len(self.obs)<2:return self.obs[-1]['xy']
        a,b=self.obs[-2],self.obs[-1]; dt=max(.04,b['t']-a['t']); vel=(b['xy']-a['xy'])/dt
        s=np.linalg.norm(vel)
        if s>10.5:vel*=10.5/s
        return b['xy']+vel*max(0.,t-b['t'])
    def proto(self):
        if not self.obs:return None
        return np.median(np.asarray([o['feat'] for o in self.obs[-10:]]),axis=0)


def track_world(frames):
    tracks=[]; active=[]; nextid=0; prev=None
    for f in frames:
        t=f['t']; det=f['fused']; dt=.125 if prev is None else max(.04,t-prev); prev=t
        used_t=set(); used_d=set()
        if active and det:
            C=np.full((len(active),len(det)),1e5,float)
            for i,tr in enumerate(active):
                pred=tr.pred(t); proto=tr.proto(); last=tr.obs[-1]
                for j,d in enumerate(det):
                    dist=float(np.linalg.norm(pred-d['xy']))
                    # Normal 8 Hz displacement is small.  V9's ~2.75 m gate
                    # allowed an identity to hop to a neighbouring red shirt.
                    gate=min(3.0,1.45+1.15*tr.miss+2.0*max(0.,dt-.125))
                    if dist>gate: continue
                    app=0.0
                    if proto is not None:
                        den=np.linalg.norm(proto)*np.linalg.norm(d['feat'])+1e-6
                        app=1-float(np.dot(proto,d['feat'])/den)
                    cam_bonus=-.10 if set(last['cams']) & set(d['cams']) else 0.0
                    C[i,j]=dist+.22*max(0.,app)+cam_bonus
            ri,ci=linear_sum_assignment(C)
            for i,j in zip(ri,ci):
                if C[i,j]>=1e4: continue
                tr=active[i]; d=det[j]
                tr.obs.append({'t':t,'xy':d['xy'],'feat':d['feat'],'cams':d['cams'],'conf':d['conf']}); tr.miss=0.; used_t.add(i); used_d.add(j)
        for i,tr in enumerate(active):
            if i not in used_t: tr.miss+=dt
        for j,d in enumerate(det):
            if j in used_d: continue
            o={'t':t,'xy':d['xy'],'feat':d['feat'],'cams':d['cams'],'conf':d['conf']}
            tr=Track(nextid,[o],0.); nextid+=1; tracks.append(tr); active.append(tr)
        active=[tr for tr in active if tr.miss<=1.25]
    return tracks


def map_tracks(tracks,truth_by,calibration_seconds):
    rows=[]; tids=[]
    for tr in tracks:
        cal=[o for o in tr.obs if o['t']<=calibration_seconds]; hold=[o for o in tr.obs if o['t']>calibration_seconds]
        if len(cal)<6 or len(hold)<3: continue
        vals=[]
        for gid in TARGET_IDS:
            ee=[]
            for o in cal:
                gt={g['id']:g for g in truth_at(truth_by,o['t'])}
                if gid in gt:ee.append(np.linalg.norm(o['xy']-np.asarray([gt[gid]['x'],gt[gid]['y']])))
            vals.append(float(np.median(ee)) if ee else 99.)
        rows.append(vals); tids.append(tr.tid)
    if not rows:return {},[]
    C=np.asarray(rows,float); ri,ci=linear_sum_assignment(C); mapping={}; diag=[]
    for r,c in zip(ri,ci):
        med=float(C[r,c]); sr=np.sort(C[r]); margin=float(sr[1]-sr[0]) if len(sr)>1 else 99.
        if med<=1.8 and margin>=.35:
            mapping[tids[r]]=TARGET_IDS[c]; diag.append({'track_id':tids[r],'gt_id':TARGET_IDS[c],'calibration_median_m':med,'identity_margin_m':margin})
    return mapping,diag


def persistent_eval(tracks,mapping,truth_by,times,calibration_seconds,fused_count):
    rows=[]; total_gt=sum(len(truth_at(truth_by,t)) for t in times if t>calibration_seconds)
    for tr in tracks:
        gid=mapping.get(tr.tid)
        if gid is None:continue
        for o in tr.obs:
            if o['t']<=calibration_seconds:continue
            gt={g['id']:g for g in truth_at(truth_by,o['t'])}
            if gid not in gt:continue
            g=gt[gid]; q=np.asarray([g['x'],g['y']],float); err=float(np.linalg.norm(o['xy']-q))
            rows.append({'t':o['t'],'track_id':tr.tid,'gt_id':gid,'pred_x':o['xy'][0],'pred_y':o['xy'][1],'truth_x':g['x'],'truth_y':g['y'],'position_error_m':err,'truth_speed':g.get('speed',0.),'truth_total_distance':g.get('total_distance',0.)})
    m=summarize_physical(rows,total_gt,fused_count); ids=sorted(set(mapping.values()))
    m.update({'identity_frozen_holdout':True,'mapped_tracks':len(mapping),'mapped_gt_ids':ids,'identity_id_coverage':len(ids)/len(TARGET_IDS),'all_tracks':len(tracks)})
    return m,rows


def geometry_eval(frames,truth_by,calibration_seconds,gate=3.0):
    errs=[]; nm=nd=ng=0
    for f in frames:
        if f['t']<=calibration_seconds:continue
        pred=np.asarray([d['xy'] for d in f['fused']],float) if f['fused'] else np.empty((0,2)); gt=truth_at(truth_by,f['t']); pairs=hungarian(pred,gt,gate)
        nm+=len(pairs);nd+=len(pred);ng+=len(gt);errs += [c for _,_,c in pairs]
    if not errs:return {'matched':0,'gt_points':ng,'detections':nd}
    a=np.asarray(errs,float);return {'matched':nm,'gt_points':ng,'detections':nd,'recall':nm/max(1,ng),'precision_proxy':nm/max(1,nd),'mae_m':float(a.mean()),'rmse_m':float(np.sqrt(np.mean(a*a))),'p95_m':float(np.percentile(a,95))}


def main():
    ap=argparse.ArgumentParser();
    for i in range(3):ap.add_argument(f'--cam{i}',required=True)
    ap.add_argument('--truth',required=True);ap.add_argument('--out',required=True);ap.add_argument('--sample-fps',type=float,default=8.0);ap.add_argument('--calibration-seconds',type=float,default=4.0);ap.add_argument('--model',default='yolo11n.pt');args=ap.parse_args()
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    from ultralytics import YOLO
    detector=YOLO(args.model);truth_by=load_truth(args.truth,video_start=NATIVE_START)
    caps={i:cv2.VideoCapture(getattr(args,f'cam{i}')) for i in range(3)};dur=min(cap.get(cv2.CAP_PROP_FRAME_COUNT)/float(cap.get(cv2.CAP_PROP_FPS) or 30) for cap in caps.values());times=np.arange(.4,max(.41,dur-.2),1./args.sample_fps);cams={i:[] for i in range(3)}
    for ti,t in enumerate(times):
        gt=truth_at(truth_by,float(t))
        for cam,cap in caps.items():
            cap.set(cv2.CAP_PROP_POS_MSEC,float(t*1000));ok,frame=cap.read()
            if not ok:continue
            raw=v9.detect_native(detector,frame);det=on_pitch(cam,raw)
            cams[cam].append({'t':float(t),'det':det,'gt':gt})
        if ti%8==0:print(f't={t:.2f}s pitch_det='+','.join(f'c{c}:{len(cams[c][-1]["det"])}' for c in range(3)),flush=True)
    for cap in caps.values():cap.release()

    classifiers,teaminfo=learn_classifiers(cams,args.calibration_seconds);models={};diagnostics={}
    for cam in range(3):
        model,hist=calibrate_camera_cv(cam,cams[cam],classifiers[cam],args.calibration_seconds);models[cam]=model
        diagnostics[str(cam)]={'team':teaminfo[str(cam)],'calibration_history':hist,'holdout_geometry':holdout_geom(cams[cam],classifiers[cam],model,args.calibration_seconds)}
        np.save(out/f'cam{cam}_H.npy',model.H);print('cam',cam,json.dumps(diagnostics[str(cam)],indent=2),flush=True)

    frames=[]
    for idx,t in enumerate(times):
        entries={c:cams[c][idx] for c in range(3) if idx<len(cams[c])}
        frames.append({'t':float(t),'fused':fuse_frame(entries,classifiers,models)})
    tracks=track_world(frames);mapping,maprows=map_tracks(tracks,truth_by,args.calibration_seconds);fused_count=sum(len(f['fused']) for f in frames if f['t']>args.calibration_seconds);metrics,rows=persistent_eval(tracks,mapping,truth_by,times,args.calibration_seconds,fused_count)
    metrics['fused_geometry_only']=geometry_eval(frames,truth_by,args.calibration_seconds);metrics.update({'version':'v10-pitch-roi-pooled-team-pure-H-mutual-fusion','video_duration_s':dur,'sample_fps':args.sample_fps,'calibration_seconds':args.calibration_seconds,'camera_diagnostics':diagnostics,'track_identity_mapping':maprows,'native_cameras':[0,1,2],'post_holdout_relinking':False,'truth_source':'20Hz sensor XY'})
    pd.DataFrame(rows).to_csv(out/'matched_observations.csv',index=False);(out/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8');(out/'track_identity_mapping.json').write_text(json.dumps(maprows,indent=2),encoding='utf-8');print(json.dumps(metrics,indent=2),flush=True)


if __name__=='__main__':main()
