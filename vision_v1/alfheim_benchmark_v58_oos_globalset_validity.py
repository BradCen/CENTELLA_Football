from __future__ import annotations
# V58 rerun trigger: anonymous validity-gated trajectory selection remains GT-free.
import argparse,json,math
from collections import defaultdict
from pathlib import Path
import numpy as np,pandas as pd
from scipy.optimize import linear_sum_assignment
import alfheim_benchmark as base
import alfheim_benchmark_v56_oos_globaltrack as v56

CAL=v56.CAL
EDGE_LIMIT=.82
STATIC_LIMIT=.88
MIN_LEN=8

def path_features(tr):
    obs=tr['obs']
    if not obs:return {'score':-1e9,'valid':False,'reason':'empty'}
    xy=np.asarray([o['xy'] for o in obs],float)
    conf=float(np.mean([o.get('conf',0.) for o in obs]))
    cams=set(c for o in obs for c in o.get('cams',()))
    edge=[]; corner=[]
    for x,y in xy:
        edge.append(min(x+1,106-x+1,y+1,69-y+1))
        corner.append(min(np.hypot(x,y),np.hypot(x, y-68),np.hypot(x-105,y),np.hypot(x-105,y-68)))
    edge_frac=float(np.mean(np.asarray(edge)<2.0)); corner_frac=float(np.mean(np.asarray(corner)<6.0))
    dif=np.linalg.norm(np.diff(xy,axis=0),axis=1) if len(xy)>1 else np.zeros(1)
    near_zero=float(np.mean(dif<0.08))
    speed=float(np.mean(dif/.125)) if len(dif) else 0.
    spatial_span=float(np.linalg.norm(np.ptp(xy,axis=0))) if len(xy)>1 else 0.
    invalid=[]
    if len(obs)<MIN_LEN: invalid.append('short')
    if near_zero>=STATIC_LIMIT and spatial_span<1.0: invalid.append('static')
    if edge_frac>=EDGE_LIMIT and len(cams)<2 and speed<0.65: invalid.append('edge_static')
    score=(1.05*math.log1p(len(obs))+.9*conf+.32*min(2,len(cams))-1.45*edge_frac-1.35*corner_frac-.55*near_zero+.08*min(3.,speed))
    return {'score':float(score),'valid':not invalid,'reason':','.join(invalid),'length':len(obs),'mean_conf':conf,'camera_count':len(cams),'edge_fraction':edge_frac,'corner_fraction':corner_frac,'near_zero_fraction':near_zero,'mean_speed_m_s':speed,'spatial_span_m':spatial_span}

def conflict(a,b,radius=2.5):
    A={round(o['t'],3):o['xy'] for o in a['obs']};B={round(o['t'],3):o['xy'] for o in b['obs']};common=set(A)&set(B)
    if not common:return 0.0
    return float(np.mean([np.linalg.norm(A[t]-B[t])<radius for t in common]))

def select_global(candidates,n=10):
    scored=[(path_features(t)['score'],t) for t in candidates if path_features(t)['valid']]
    ranked=[t for _,t in sorted(scored,key=lambda x:x[0],reverse=True)]
    chosen=[]
    for tr in ranked:
        if any(conflict(tr,old)>=.35 for old in chosen):continue
        chosen.append(tr)
        if len(chosen)>=n:break
    return chosen

def main():
    ap=argparse.ArgumentParser()
    for i in range(3):ap.add_argument(f'--cam{i}',required=True)
    ap.add_argument('--truth',required=True);ap.add_argument('--out',required=True)
    a=ap.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    frames,dur,diag=v56.build({0:a.cam0,1:a.cam1,2:a.cam2})
    candidates=[];blocked=set()
    for tid in range(35):
        p=v56.best_path(frames,blocked)
        if len(p)<MIN_LEN:break
        obs=[]
        for ti,di,d in p:
            blocked.add((ti,di));obs.append({'t':float(frames[ti]['t']),'xy':np.asarray(d['xy'],float),'feat':np.asarray(d['feat'],float),'cams':tuple(d.get('cams',())),'conf':float(d.get('conf',0.))})
        candidates.append({'track_id':tid,'obs':obs})
    tracks=select_global(candidates,10)
    tb=base.load_truth(a.truth,video_start=v56.v9.NATIVE_START)
    anon=v56.anonymous_eval(tracks,tb);mapping,mapdiag=v56.calibration_mapping(tracks,tb);mm,rows=v56.mapped_eval(tracks,mapping,tb);ff=v56.framewise_eval(frames,tb)
    r={'version':'v58-oos-global-anonymous-validity-gated-set','segment':'0059-0061','duration_s':dur,'sample_fps':v56.FPS,'calibration_seconds':CAL,'inference_uses_ground_truth':False,'truth_usage':'ground truth is used only after anonymous trajectories are constructed for diagnostics/evaluation','validity_policy':{'min_track_length':MIN_LEN,'edge_fraction_limit':EDGE_LIMIT,'static_fraction_limit':STATIC_LIMIT,'edge_static_requires_multi_camera':True},'candidate_tracks':len(candidates),'valid_candidate_tracks':sum(path_features(t)['valid'] for t in candidates),'selected_tracks':len(tracks),'candidate_scores':[{'track_id':int(t['track_id']),'features':path_features(t)} for t in candidates],'selected_source_track_ids':[int(t['track_id']) for t in tracks],'framewise_geometry_evaluation':ff,'anonymous_tracking_diagnostics':anon,'calibration_mapped_holdout_evaluation':mm,'track_identity_mapping':mapdiag,'track_lengths':[len(t['obs']) for t in tracks],'detector_selection_diagnostics':diag}
    (out/'metrics.json').write_text(json.dumps(r,indent=2));pd.DataFrame(rows).to_csv(out/'matched_observations.csv',index=False);pd.DataFrame([{'track_id':t['track_id'],'samples':len(t['obs']),'score':path_features(t)['score']} for t in tracks]).to_csv(out/'tracks_summary.csv',index=False);print(json.dumps(r,indent=2),flush=True)

if __name__=='__main__':main()
