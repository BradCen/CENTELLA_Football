from __future__ import annotations
import argparse,json,math
from collections import defaultdict
from pathlib import Path
import cv2,numpy as np,pandas as pd
from scipy.optimize import linear_sum_assignment
import alfheim_benchmark as base
import alfheim_benchmark_v2 as v2
import alfheim_benchmark_v9 as v9
import alfheim_benchmark_v10 as v10

OFFSET=23.251115-12.794293
FPS=8.0
CAL=3.0
RED=.015
CONF=.20
MIN_H=9.0
TOP=20
MAX_SPEED=10.0
MAX_GAP_S=.375
SKIP_PENALTY=1.4
BIRTH_PENALTY=2.2
TRANS_WEIGHT=1.0
APP_WEIGHT=.75
NODE_WEIGHT=.9

class KeepAll:
    def keep(self,_): return True

def truth_oos(tb,t): return base.truth_at(tb,float(t)+OFFSET)

def filt(frame,dets):
    out=[]
    for d in dets:
        r=v2.jersey_red_score(frame,d['box']); h=float(d['box'][3]-d['box'][1]); c=float(d.get('conf',0.))
        if r<RED or c<CONF or h<MIN_H: continue
        x=dict(d); x['red_score']=float(r); x['select_score']=.75*r+.25*c
        out.append(x)
    out.sort(key=lambda d:(d['select_score'],d['conf']),reverse=True)
    return out[:TOP]

def build(paths, models=None):
    from ultralytics import YOLO
    detector=YOLO('yolo11n.pt')
    caps={c:cv2.VideoCapture(p) for c,p in paths.items()}
    fps={c:float(x.get(cv2.CAP_PROP_FPS) or 25.) for c,x in caps.items()}
    dur=min((caps[c].get(cv2.CAP_PROP_FRAME_COUNT) or 0)/fps[c] for c in caps)
    times=np.arange(.4,max(.41,dur-.2),1/FPS)
    models = dict(models or {})
    models.update({c:v10.seed_model(c) for c in paths if c not in models})
    keep={c:KeepAll() for c in paths}; frames=[]; stats=defaultdict(list)
    for i,t in enumerate(times):
        ent={}
        for cam,cap in caps.items():
            cap.set(cv2.CAP_PROP_POS_MSEC,float(t*1000)); ok,fr=cap.read()
            if not ok: continue
            raw=v9.detect_native(detector,fr); op=v10.on_pitch(cam,raw,models[cam]); dd=filt(fr,op)
            stats[cam].append(len(dd)); ent[cam]={'t':float(t),'det':dd}
        fu=v10.fuse_frame(ent,keep,models)
        for d in fu:
            d['node_score']=float(np.clip(.65*max(0.,d.get('conf',0.))+.35*float(len(d.get('cams',())))/3.,0.,1.))
        frames.append({'t':float(t),'fused':fu})
        if i%8==0: print(f't={t:.2f}s fused={len(fu)}',flush=True)
    for c in caps.values(): c.release()
    return frames,dur,{str(c):{'mean_selected':float(np.mean(v)) if v else 0.,'max_selected':int(max(v)) if v else 0} for c,v in stats.items()}

def app_cost(a,b):
    fa=np.asarray(a.get('feat',[]),float); fb=np.asarray(b.get('feat',[]),float)
    if fa.size==0 or fb.size==0:return 0.
    den=np.linalg.norm(fa)*np.linalg.norm(fb)+1e-6
    return float(1.-np.dot(fa,fb)/den)

def edge_cost(a,b,dt):
    dist=float(np.linalg.norm(np.asarray(a['xy'])-np.asarray(b['xy']))); speed=dist/max(dt,.04)
    if speed>MAX_SPEED:return None
    motion=dist/max(.75,MAX_SPEED*dt); app=max(0.,app_cost(a,b)); node=max(0.,float(b.get('node_score',0.)))
    cam_bonus=-.18 if set(a.get('cams',())) & set(b.get('cams',())) else 0.
    return TRANS_WEIGHT*motion + APP_WEIGHT*app + SKIP_PENALTY*(dt>.1251) - NODE_WEIGHT*node + cam_bonus

def best_path(frames,blocked):
    nodes=[]
    for ti,f in enumerate(frames):
        for di,d in enumerate(f['fused']):
            if (ti,di) not in blocked:nodes.append((ti,di,d))
    if not nodes:return []
    by_t=defaultdict(list)
    for k,(ti,di,d) in enumerate(nodes):by_t[ti].append(k)
    dp={};prev={}
    for ti in sorted(by_t):
        for k in by_t[ti]:
            _,_,d=nodes[k];best=BIRTH_PENALTY+SKIP_PENALTY;pk=None
            for pt in range(ti-1,max(-1,ti-3),-1):
                dt=frames[ti]['t']-frames[pt]['t']
                if dt>MAX_GAP_S:break
                for q in by_t.get(pt,()):
                    if q not in dp:continue
                    ec=edge_cost(nodes[q][2],d,dt)
                    if ec is None:continue
                    val=dp[q]+ec
                    if val<best:best=val;pk=q
            dp[k]=best;prev[k]=pk
    _,k=min((cost-1.8*math.log1p(1+nodes[idx][0]),idx) for idx,cost in dp.items())
    path=[]
    while k is not None:path.append(k);k=prev.get(k)
    path.reverse();return [(nodes[k][0],nodes[k][1],nodes[k][2]) for k in path]

def extract_tracks(frames,n_tracks=10):
    blocked=set();tracks=[]
    for tid in range(n_tracks*2):
        p=best_path(frames,blocked)
        if len(p)<6:break
        tracks.append({'track_id':tid,'obs':[]})
        for ti,di,d in p:
            blocked.add((ti,di));tracks[-1]['obs'].append({'t':float(frames[ti]['t']),'xy':np.asarray(d['xy'],float),'feat':np.asarray(d['feat'],float),'cams':tuple(d.get('cams',())),'conf':float(d.get('conf',0.))})
        if len(tracks)>=n_tracks:break
    return tracks

def framewise_eval(frames,tb):
    errs=[];matched=gt_points=dets=0
    for f in frames:
        if f['t']<=CAL:continue
        pred=np.asarray([d['xy'] for d in f['fused']],float) if f['fused'] else np.empty((0,2));gt=truth_oos(tb,f['t']);gt_points+=len(gt);dets+=len(pred)
        if len(pred)==0 or not gt:continue
        G=np.asarray([[g['x'],g['y']] for g in gt]);C=np.linalg.norm(pred[:,None,:]-G[None,:,:],axis=2);ri,ci=linear_sum_assignment(C)
        for i,j in zip(ri,ci):
            if C[i,j]<=4.:matched+=1;errs.append(float(C[i,j]))
    a=np.asarray(errs,float);return {'matched':matched,'gt_points':gt_points,'detections':dets,'recall_proxy':matched/max(1,gt_points),'precision_proxy':matched/max(1,dets),'mae_m':float(a.mean()) if len(a) else None,'rmse_m':float(np.sqrt(np.mean(a*a))) if len(a) else None,'p95_m':float(np.percentile(a,95)) if len(a) else None}

def calibration_mapping(tracks,tb):
    target=list(v10.TARGET_IDS);eligible=[];tids=[]
    for tr in tracks:
        cal=[o for o in tr['obs'] if o['t']<=CAL];hold=[o for o in tr['obs'] if o['t']>CAL]
        if len(cal)<6 or len(hold)<3:continue
        row=[]
        for gid in target:
            ee=[]
            for o in cal:
                g={x['id']:x for x in truth_oos(tb,o['t'])}.get(gid)
                if g is not None:ee.append(float(np.linalg.norm(o['xy']-np.asarray([g['x'],g['y']],float))))
            row.append(float(np.median(ee)) if ee else 99.)
        eligible.append(row);tids.append(tr['track_id'])
    if not eligible:return {},[]
    C=np.asarray(eligible);ri,ci=linear_sum_assignment(C);mapping={};diag=[]
    for r,c in zip(ri,ci):mapping[tids[r]]=target[c];diag.append({'track_id':int(tids[r]),'gt_id':int(target[c]),'calibration_median_m':float(C[r,c])})
    return mapping,diag

def mapped_eval(tracks,mapping,tb):
    rows=[]
    for tr in tracks:
        gid=mapping.get(tr['track_id'])
        if gid is None:continue
        for o in tr['obs']:
            if o['t']<=CAL:continue
            g={x['id']:x for x in truth_oos(tb,o['t'])}.get(gid)
            if g is None:continue
            q=np.asarray([g['x'],g['y']],float);e=float(np.linalg.norm(o['xy']-q));rows.append({'t':o['t'],'track_id':tr['track_id'],'gt_id':gid,'pred_x':o['xy'][0],'pred_y':o['xy'][1],'truth_x':g['x'],'truth_y':g['y'],'position_error_m':e})
    a=np.asarray([r['position_error_m'] for r in rows],float);return {'mapped_tracks':len(mapping),'mapped_samples':len(rows),'mae_m':float(a.mean()) if len(a) else None,'rmse_m':float(np.sqrt(np.mean(a*a))) if len(a) else None,'p95_m':float(np.percentile(a,95)) if len(a) else None},rows

def anonymous_eval(tracks,tb):
    switches=matched=total=0;track_rows=[]
    for tr in tracks:
        labels=[]
        for o in tr['obs']:
            if o['t']<=CAL:continue
            gt=truth_oos(tb,o['t'])
            if not gt:continue
            best=min(((int(g['id']),float(np.linalg.norm(o['xy']-np.asarray([g['x'],g['y']])))) for g in gt),key=lambda z:z[1]);labels.append(best)
        if not labels:continue
        prev=None
        for lab,e in labels:
            total+=1;matched+=int(e<=4.)
            if prev is not None and lab!=prev:switches+=1
            prev=lab
        from collections import Counter
        maj=Counter(l for l,_ in labels).most_common(1)[0][0];track_rows.append({'track_id':tr['track_id'],'samples':len(labels),'majority_gt_id':maj,'majority_fraction':sum(l==maj for l,_ in labels)/len(labels),'mean_nearest_error_m':float(np.mean([e for _,e in labels]))})
    return {'tracks_evaluated':len(track_rows),'matched_samples_within_4m':matched,'evaluated_samples':total,'nearest_match_rate':matched/max(1,total),'trajectory_identity_switches':switches,'track_rows':track_rows}

def main():
    ap=argparse.ArgumentParser()
    for i in range(3):ap.add_argument(f'--cam{i}',required=True)
    ap.add_argument('--truth',required=True);ap.add_argument('--out',required=True);ap.add_argument('--geometry-dir',default=None,help='optional directory containing cam0/1/2_geometry_refinement.json')
    a=ap.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    models={}
    if a.geometry_dir:
        gd=Path(a.geometry_dir)
        for cam in range(3):
            p=gd/f'cam{cam}_geometry_refinement.json'
            if p.exists():
                info=json.loads(p.read_text()); H=info.get('chosen_h')
                if H is not None: models[cam]=v10.CameraModel(np.asarray(H,float),None)
    frames,dur,diag=build({0:a.cam0,1:a.cam1,2:a.cam2},models=models);tb=base.load_truth(a.truth,video_start=v10.NATIVE_START)
    tracks=extract_tracks(frames,10);mapping,mapdiag=calibration_mapping(tracks,tb);mm,rows=mapped_eval(tracks,mapping,tb)
    r={'version':'v56-oos-global-anonymous-track-extraction','segment':'0059-0061','duration_s':dur,'sample_fps':FPS,'calibration_seconds':CAL,'inference_uses_ground_truth':False,'truth_usage':'ground truth is used only after anonymous trajectories are constructed for diagnostics/evaluation','geometry_models_loaded':sorted(models.keys()),'detector_thresholds':{'red':RED,'confidence':CONF,'min_height_px':MIN_H,'top_k_per_camera':TOP},'tracking_parameters':{'target_track_count':10,'max_speed_m_s':MAX_SPEED,'max_gap_s':MAX_GAP_S,'skip_penalty':SKIP_PENALTY,'birth_penalty':BIRTH_PENALTY,'appearance_weight':APP_WEIGHT},'framewise_geometry_evaluation':framewise_eval(frames,tb),'anonymous_tracking_diagnostics':anonymous_eval(tracks,tb),'calibration_mapped_holdout_evaluation':mm,'track_identity_mapping':mapdiag,'track_count_extracted':len(tracks),'track_lengths':[len(t['obs']) for t in tracks],'detector_selection_diagnostics':diag}
    (out/'metrics.json').write_text(json.dumps(r,indent=2));pd.DataFrame(rows).to_csv(out/'matched_observations.csv',index=False);pd.DataFrame([{'track_id':t['track_id'],'samples':len(t['obs'])} for t in tracks]).to_csv(out/'tracks_summary.csv',index=False);print(json.dumps(r,indent=2),flush=True)
if __name__=='__main__':main()
