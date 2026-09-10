from __future__ import annotations
import json
from collections import defaultdict
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
RED=0.015
CONF=0.20
MIN_H=9.0
TOP=20
class KeepAll:
    def keep(self,_): return True

def truth_at_oos(tb,t): return base.truth_at(tb,float(t)+OFFSET)

def filt(frame,dets):
    a=[]
    for d in dets:
        r=v2.jersey_red_score(frame,d['box']); h=float(d['box'][3]-d['box'][1]); c=float(d.get('conf',0.0))
        if r<RED or c<CONF or h<MIN_H: continue
        x=dict(d); x['red_score']=float(r)
        # Red evidence is primary, detector confidence breaks ties.
        x['select_score']=0.75*r+0.25*c
        a.append(x)
    a.sort(key=lambda d:(d['select_score'],d['conf']),reverse=True)
    return a[:TOP]

def build(paths):
    from ultralytics import YOLO
    detector=YOLO('yolo11n.pt'); caps={c:cv2.VideoCapture(p) for c,p in paths.items()}
    fps={c:float(x.get(cv2.CAP_PROP_FPS) or 25.) for c,x in caps.items()}; dur=min((caps[c].get(cv2.CAP_PROP_FRAME_COUNT) or 0)/fps[c] for c in caps)
    times=np.arange(.4,max(.41,dur-.2),1/SAMPLE_FPS); models={c:v10.seed_model(c) for c in paths}; keep={c:KeepAll() for c in paths}; frames=[]; stats=defaultdict(list)
    for i,t in enumerate(times):
        ent={}
        for cam,cap in caps.items():
            cap.set(cv2.CAP_PROP_POS_MSEC,float(t*1000)); ok,fr=cap.read()
            if not ok: continue
            raw=v9.detect_native(detector,fr); op=v10.on_pitch(cam,raw,models[cam]); dd=filt(fr,op); stats[cam].append(len(dd)); ent[cam]={'t':float(t),'det':dd}
        fu=v10.fuse_frame(ent,keep,models); frames.append({'t':float(t),'fused':fu})
        if i%8==0: print(f't={t:.2f}s fused={len(fu)}',flush=True)
    for c in caps.values(): c.release()
    diag={str(c):{'mean_selected':float(np.mean(v)) if v else 0,'max_selected':int(max(v)) if v else 0} for c,v in stats.items()}
    return frames,dur,diag

def frame_eval(frames,tb):
    es=[];m=g=d=0
    for f in frames:
        if f['t']<=CAL: continue
        p=np.asarray([x['xy'] for x in f['fused']],float) if f['fused'] else np.empty((0,2)); gt=truth_at_oos(tb,f['t']); g+=len(gt); d+=len(p)
        if len(p)==0 or not gt: continue
        G=np.asarray([[x['x'],x['y']] for x in gt]); C=np.linalg.norm(p[:,None,:]-G[None,:,:],axis=2);ri,ci=linear_sum_assignment(C)
        for i,j in zip(ri,ci):
            if C[i,j]<=4: es.append(float(C[i,j]));m+=1
    a=np.asarray(es,float); return {'matched':m,'gt_points':g,'detections':d,'recall_proxy':m/max(1,g),'precision_proxy':m/max(1,d),'mae_m':float(a.mean()) if len(a) else None,'rmse_m':float(np.sqrt(np.mean(a*a))) if len(a) else None,'p95_m':float(np.percentile(a,95)) if len(a) else None}

def posthoc(tracks,tb):
    # Evaluation-only majority association from full OOS trajectory; inference never sees GT.
    rows=[]; switches=0; total=0; by=defaultdict(list)
    for tr in tracks:
        labels=[]
        for o in tr.obs:
            gt=truth_at_oos(tb,o['t'])
            if not gt: continue
            ds=[(int(g['id']),float(np.linalg.norm(o['xy']-np.asarray([g['x'],g['y']],float)))) for g in gt]
            if ds:
                lab,e=min(ds,key=lambda z:z[1]); labels.append((o['t'],lab,e))
        if not labels: continue
        from collections import Counter
        best=Counter(l for _,l,_ in labels).most_common(1)[0][0]
        prev=None
        for t,l,e in labels:
            total+=1; by[best].append(e if l==best else min(e+20,100))
            if prev is not None and l!=prev: switches+=1
            prev=l
        med=float(np.median([e for _,l,e in labels if l==best])) if any(l==best for _,l,e in labels) else 99.
        rows.append({'track_id':tr.tid,'posthoc_gt_id':best,'samples':len(labels),'majority_fraction':sum(l==best for _,l,_ in labels)/len(labels),'majority_median_error_m':med})
    return {'tracks_evaluated':len(rows),'trajectory_identity_switches':switches,'rows':rows}

def main():
    import argparse
    ap=argparse.ArgumentParser()
    for i in range(3): ap.add_argument(f'--cam{i}',required=True)
    ap.add_argument('--truth',required=True);ap.add_argument('--out',required=True);a=ap.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    fr,dur,diag=build({0:a.cam0,1:a.cam1,2:a.cam2}); tb=base.load_truth(a.truth,video_start=v10.NATIVE_START); tracks=v10.track_world(fr)
    r={'version':'v52-oos-image-only-redtrack-balanced','segment':'0059-0061','duration_s':dur,'sample_fps':SAMPLE_FPS,'calibration_seconds':CAL,'inference_uses_ground_truth':False,'thresholds':{'red':RED,'confidence':CONF,'min_height_px':MIN_H,'top_k_per_camera':TOP},'framewise_geometry_evaluation':frame_eval(fr,tb),'posthoc_track_association':posthoc(tracks,tb),'track_count':len(tracks),'detector_selection_diagnostics':diag,'truth_usage':'evaluation only after anonymous tracks are constructed'}
    (out/'metrics.json').write_text(json.dumps(r,indent=2));pd.DataFrame([{'t':o['t'],'track_id':tr.tid,'pred_x':float(o['xy'][0]),'pred_y':float(o['xy'][1]),'cams':','.join(map(str,o['cams']))} for tr in tracks for o in tr.obs]).to_csv(out/'anonymous_tracks.csv',index=False);print(json.dumps(r,indent=2),flush=True)
if __name__=='__main__':main()
