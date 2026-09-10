from __future__ import annotations
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import cv2
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
import alfheim_benchmark as base
import alfheim_benchmark_v2 as v2
import alfheim_benchmark_v9 as v9
import alfheim_benchmark_v10 as v10

OFFSET=23.251115-12.794293
SAMPLE_FPS=8.0
CAL=3.0
RED=.015
CONF=.20
MIN_H=9.0
TOP=20
CONFIRM_HITS=3
TENTATIVE_MAX_AGE=2
MAX_MISS=.75
MAX_ACTIVE=24

class KeepAll:
    def keep(self,_): return True

def truth_at(tb,t): return base.truth_at(tb,float(t)+OFFSET)

def filt(frame,dets):
    out=[]
    for d in dets:
        r=v2.jersey_red_score(frame,d['box']); h=float(d['box'][3]-d['box'][1]); c=float(d.get('conf',0.0))
        if r<RED or c<CONF or h<MIN_H: continue
        x=dict(d); x['red_score']=float(r); x['select_score']=.75*r+.25*c; out.append(x)
    out.sort(key=lambda d:(d['select_score'],d['conf']),reverse=True)
    return out[:TOP]

def build_frames(paths):
    from ultralytics import YOLO
    detector=YOLO('yolo11n.pt'); caps={c:cv2.VideoCapture(p) for c,p in paths.items()}
    fps={c:float(x.get(cv2.CAP_PROP_FPS) or 25.) for c,x in caps.items()}; dur=min((caps[c].get(cv2.CAP_PROP_FRAME_COUNT) or 0)/fps[c] for c in caps)
    times=np.arange(.4,max(.41,dur-.2),1/SAMPLE_FPS); models={c:v10.seed_model(c) for c in paths}; keep={c:KeepAll() for c in paths}; frames=[]
    for idx,t in enumerate(times):
        ent={}
        for cam,cap in caps.items():
            cap.set(cv2.CAP_PROP_POS_MSEC,float(t*1000)); ok,fr=cap.read()
            if not ok: continue
            raw=v9.detect_native(detector,fr); on=v10.on_pitch(cam,raw,models[cam]); dd=filt(fr,on); ent[cam]={'t':float(t),'det':dd}
        fused=v10.fuse_frame(ent,keep,models); frames.append({'t':float(t),'fused':fused})
        if idx%8==0: print(f't={t:.2f}s fused={len(fused)}',flush=True)
    for c in caps.values(): c.release()
    return frames,dur

@dataclass
class Tr:
    tid:int; obs:list=field(default_factory=list); miss:float=0.; hits:int=1; confirmed:bool=False
    def xy(self): return self.obs[-1]['xy']
    def proto(self): return np.median(np.asarray([o['feat'] for o in self.obs[-8:]]),axis=0) if self.obs else None
    def pred(self,t):
        if len(self.obs)<2:return self.xy()
        a,b=self.obs[-2],self.obs[-1];dt=max(.04,b['t']-a['t']);v=(b['xy']-a['xy'])/dt;s=float(np.linalg.norm(v));
        if s>10.5:v*=10.5/s
        return b['xy']+v*max(0.,t-b['t'])

def persist_track(frames):
    active=[];tent=[];nextid=0;prev_t=None
    for f in frames:
        t=f['t']; det=f['fused']; dt=.125 if prev_t is None else max(.04,t-prev_t); prev_t=t
        alltr=active+tent; used_t=set(); used_d=set(); C=np.full((len(alltr),len(det)),1e5,float)
        for i,tr in enumerate(alltr):
            pred=tr.pred(t); proto=tr.proto()
            gate=3.2 if tr.confirmed else 2.4
            gate+=min(1.3,tr.miss*2.0)
            for j,d in enumerate(det):
                dist=float(np.linalg.norm(pred-d['xy']))
                if dist>gate: continue
                app=0.
                if proto is not None:
                    den=np.linalg.norm(proto)*np.linalg.norm(d['feat'])+1e-6
                    app=1-float(np.dot(proto,d['feat'])/den)
                C[i,j]=dist+.20*max(0.,app)-.10*(len(set(tr.obs[-1]['cams']) & set(d['cams'])) if tr.obs else 0)
        if len(alltr) and len(det):
            ri,ci=linear_sum_assignment(C)
            for i,j in zip(ri,ci):
                if C[i,j]>=1e4: continue
                tr=alltr[i]; d=det[j]; tr.obs.append({'t':t,'xy':np.asarray(d['xy'],float),'feat':np.asarray(d['feat'],float),'cams':d['cams'],'conf':float(d['conf'])}); tr.miss=0.; tr.hits+=1; used_t.add(i); used_d.add(j)
                if not tr.confirmed and tr.hits>=CONFIRM_HITS: tr.confirmed=True
        for i,tr in enumerate(alltr):
            if i not in used_t: tr.miss+=dt
        # unmatched detections become tentative, not immediately reportable players
        for j,d in enumerate(det):
            if j in used_d: continue
            tent.append(Tr(nextid,[{'t':t,'xy':np.asarray(d['xy'],float),'feat':np.asarray(d['feat'],float),'cams':d['cams'],'conf':float(d['conf'])}],0.,1,False)); nextid+=1
        # prune tentative tracks that never persist; confirmed tracks get longer grace period
        tent=[tr for tr in tent if tr.miss<=TENTATIVE_MAX_AGE/SAMPLE_FPS and not tr.confirmed]
        newly=[tr for tr in tent if tr.confirmed]; tent=[tr for tr in tent if not tr.confirmed]; active.extend(newly)
        active=[tr for tr in active if tr.miss<=MAX_MISS]
        if len(active)>MAX_ACTIVE:
            active=sorted(active,key=lambda tr:(-len(tr.obs),tr.miss))[:MAX_ACTIVE]
    return active

def eval_tracks(tracks,tb):
    # Evaluation-only posthoc identity mapping from the longest stable tracks.
    candidates=[tr for tr in tracks if tr.confirmed and len(tr.obs)>=6 and any(o['t']>CAL for o in tr.obs)]
    tids=[tr.tid for tr in candidates]; target=list(v10.TARGET_IDS); M=[]
    for tr in candidates:
        row=[]
        for gid in target:
            ee=[]
            for o in tr.obs:
                if o['t']>CAL: break
                gt={g['id']:g for g in truth_at(tb,o['t'])}
                if gid in gt: ee.append(np.linalg.norm(o['xy']-np.asarray([gt[gid]['x'],gt[gid]['y']],float)))
            row.append(float(np.median(ee)) if ee else 99.)
        M.append(row)
    mapping={}
    if M:
        ri,ci=linear_sum_assignment(np.asarray(M,float))
        for r,c in zip(ri,ci):
            if M[r][c]<3.0: mapping[tids[r]]=target[c]
    rows=[]
    for tr in candidates:
        gid=mapping.get(tr.tid)
        if gid is None: continue
        for o in tr.obs:
            if o['t']<=CAL:continue
            gt={g['id']:g for g in truth_at(tb,o['t'])}
            if gid not in gt:continue
            q=np.asarray([gt[gid]['x'],gt[gid]['y']],float);e=float(np.linalg.norm(o['xy']-q));rows.append({'t':o['t'],'track_id':tr.tid,'gt_id':gid,'pred_x':o['xy'][0],'pred_y':o['xy'][1],'truth_x':q[0],'truth_y':q[1],'position_error_m':e})
    a=np.asarray([r['position_error_m'] for r in rows],float)
    gt_count=sum(len(truth_at(tb,t)) for t in sorted({o['t'] for tr in tracks for o in tr.obs}) if t>CAL)
    return {'candidate_tracks':len(candidates),'mapped_tracks':len(mapping),'mapped_samples':len(rows),'gt_points':gt_count,'mae_m':float(a.mean()) if len(a) else None,'rmse_m':float(np.sqrt(np.mean(a*a))) if len(a) else None,'p95_m':float(np.percentile(a,95)) if len(a) else None,'mapping':mapping},rows

def main():
    import argparse
    ap=argparse.ArgumentParser();
    for i in range(3):ap.add_argument(f'--cam{i}',required=True)
    ap.add_argument('--truth',required=True);ap.add_argument('--out',required=True);args=ap.parse_args();out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    frames,dur=build_frames({0:args.cam0,1:args.cam1,2:args.cam2}); tb=base.load_truth(args.truth,video_start=v10.NATIVE_START); tracks=persist_track(frames); metrics,rows=eval_tracks(tracks,tb)
    metrics.update({'version':'v53-oos-persistent-anonymous-redtrack','segment':'0059-0061','duration_s':dur,'sample_fps':SAMPLE_FPS,'calibration_seconds':CAL,'inference_uses_ground_truth':False,'confirmation_hits':CONFIRM_HITS,'tentative_max_age':TENTATIVE_MAX_AGE,'max_miss_s':MAX_MISS,'max_active_tracks':MAX_ACTIVE,'truth_usage':'evaluation only after anonymous tracks are constructed'})
    (out/'metrics.json').write_text(json.dumps(metrics,indent=2));pd.DataFrame(rows).to_csv(out/'matched_observations.csv',index=False);pd.DataFrame([{'track_id':tr.tid,'samples':len(tr.obs),'confirmed':tr.confirmed} for tr in tracks]).to_csv(out/'tracks_summary.csv',index=False);print(json.dumps(metrics,indent=2),flush=True)
if __name__=='__main__':main()
