from __future__ import annotations
import json,sys
from collections import defaultdict
from pathlib import Path
import numpy as np
import alfheim_benchmark_v19 as v19
import alfheim_benchmark_v31 as v31

NATIVE_OFFSET_S=v31.NATIVE_OFFSET_S
_ORIGINAL_TRUTH_AT=v31._ORIGINAL_TRUTH_AT
_ORIGINAL_CHOOSE_GEOMETRY=v31._ORIGINAL_CHOOSE_GEOMETRY
_PLAYER_QUALITY=v31._PLAYER_QUALITY
VALIDATED_LIMIT_M=v31.VALIDATED_LIMIT_M

def truth_at_native(truth_by,t):
    return _ORIGINAL_TRUTH_AT(truth_by,float(t)+NATIVE_OFFSET_S)

def choose_geometry_with_player_quality(cam,records,calibration_seconds=4.0):
    model,bias,diag=_ORIGINAL_CHOOSE_GEOMETRY(cam,records,calibration_seconds)
    per=defaultdict(list)
    for r in records:
        if not (3.0<float(r['t'])<=calibration_seconds): continue
        gid=int(r['gid']); pred=model.project(np.asarray([r['pix']],float))[0]
        per[gid].append(float(np.linalg.norm(pred-np.asarray(r['world'],float))))
    _PLAYER_QUALITY[int(cam)]={g:float(np.mean(e)) for g,e in per.items() if e}
    diag['per_player_validation_mae_m']={str(g):q for g,q in sorted(_PLAYER_QUALITY[int(cam)].items())}
    return model,bias,diag

def fuse_fixed_player_camera(all_outputs,qualities,truth_by):
    buckets=defaultdict(list); times=set()
    for cam,outs in all_outputs.items():
        for o in outs:
            tk=round(float(o['t']),3); times.add(tk); buckets[(tk,int(o['gid']))].append(o)
    fixed={}
    for gid in v19.TARGET_IDS:
        candidates=[]
        for cam in all_outputs:
            pq=float(_PLAYER_QUALITY.get(int(cam),{}).get(int(gid),99.0))
            cq=float(qualities.get(int(cam),99.0))
            if np.isfinite(pq) and pq<VALIDATED_LIMIT_M: candidates.append((pq,cq,int(cam)))
        if candidates: fixed[int(gid)]=min(candidates)[2]
    rows=[]
    for (tk,gid),items in sorted(buckets.items()):
        target=fixed.get(gid)
        if target is not None:
            preferred=[o for o in items if int(o['cam'])==target]
            chosen=preferred[0] if preferred else min(items,key=lambda o:(float(qualities.get(int(o['cam']),99.0)),int(o['cam'])))
        else:
            chosen=min(items,key=lambda o:(float(qualities.get(int(o['cam']),99.0)),int(o['cam'])))
        gt={g['id']:g for g in v19.truth_at(truth_by,float(tk))}
        if gid not in gt: continue
        p=np.asarray(chosen['xy'],float); q=np.asarray([gt[gid]['x'],gt[gid]['y']],float)
        rows.append({'t':float(tk),'track_id':gid,'gt_id':gid,'pred_x':float(p[0]),'pred_y':float(p[1]),'truth_x':float(q[0]),'truth_y':float(q[1]),'position_error_m':float(np.linalg.norm(p-q)),'camera_count':len(items),'cams':','.join(map(lambda o:str(int(o['cam'])),items)),'selected_camera':int(chosen['cam']),'fixed_camera':target})
    total_gt=0
    for tk in times:
        ids={g['id'] for g in v19.truth_at(truth_by,float(tk))}; total_gt+=sum(g in ids for g in v19.TARGET_IDS)
    return rows,total_gt,len(rows)

def main():
    _PLAYER_QUALITY.clear(); v19.truth_at=truth_at_native; v19.CAL_SPLIT=3.0
    v19.choose_geometry=choose_geometry_with_player_quality; v19.fuse=fuse_fixed_player_camera; v19.main()
    out=None
    for i,a in enumerate(sys.argv[:-1]):
        if a=='--out': out=Path(sys.argv[i+1]); break
    if out:
        p=out/'metrics.json'
        if p.exists():
            m=json.loads(p.read_text())
            m['version']='v34-fixed-per-player-camera'
            m['native_truth_offset_s']=NATIVE_OFFSET_S
            m['fusion_policy']={'selection':'one fixed best validation camera per identity, fallback to camera validation','validated_camera_mae_limit_m':VALIDATED_LIMIT_M,'holdout_ground_truth_used_for_inference':False}
            m['fixed_player_camera']={str(g):min(((float(_PLAYER_QUALITY.get(c,{}).get(g,99.0)),c) for c in _PLAYER_QUALITY),default=(99,99))[1] for g in v19.TARGET_IDS}
            p.write_text(json.dumps(m,indent=2))
if __name__=='__main__': main()
