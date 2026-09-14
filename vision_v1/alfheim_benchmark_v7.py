from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

import alfheim_benchmark_v5 as v5
import alfheim_benchmark_v6 as v6  # patches V5 with strict tracker + motion identity mapper


def summarize_physical(rows, total_gt, total_det):
    """Use sensor XY itself as physical truth for speed/distance.

    Alfheim's cumulative-distance field can stay flat across sub-second samples,
    so differentiating it produces bogus near-zero ground-truth distances.
    """
    if not rows:
        return {'matched': 0, 'gt_points': total_gt, 'detections': total_det, 'recall': 0.0}
    e = pd.DataFrame(rows).sort_values(['gt_id', 't'])
    pos = e.position_error_m.to_numpy(float)
    out = {
        'matched': int(len(e)), 'gt_points': int(total_gt), 'detections': int(total_det),
        'recall': float(len(e) / max(1, total_gt)),
        'precision_proxy': float(len(e) / max(1, total_det)),
        'position_mae_m': float(np.mean(pos)),
        'position_rmse_m': float(np.sqrt(np.mean(pos ** 2))),
        'position_p95_m': float(np.percentile(pos, 95)),
    }
    raw_err=[]; raw_pred=raw_true=0.0
    smooth_err=[]; smooth_pred=smooth_true=0.0
    per_player={}
    for pid,g in e.groupby('gt_id'):
        g=g.drop_duplicates('t').sort_values('t')
        if len(g)<2: continue
        t=g.t.to_numpy(float)
        pred=g[['pred_x','pred_y']].to_numpy(float)
        truth=g[['truth_x','truth_y']].to_numpy(float)
        dt=np.diff(t)
        dp=np.linalg.norm(np.diff(pred,axis=0),axis=1)
        dg=np.linalg.norm(np.diff(truth,axis=0),axis=1)
        # Accept native 6 Hz intervals and short detector gaps; reject long gaps.
        good=(dt>=0.12)&(dt<=0.75)&(dg/dt<13.5)&(dp/dt<15.0)
        if not np.any(good): continue
        pv=dp[good]/dt[good]; gv=dg[good]/dt[good]
        raw_err.extend((pv-gv).tolist()); raw_pred+=float(dp[good].sum()); raw_true+=float(dg[good].sum())
        # Simple robust 3-point median on positions before derivative.
        sp=pred.copy()
        if len(sp)>=3:
            for k in range(1,len(sp)-1):
                sp[k]=np.median(pred[k-1:k+2],axis=0)
        dp2=np.linalg.norm(np.diff(sp,axis=0),axis=1)
        good2=(dt>=0.12)&(dt<=0.75)&(dg/dt<13.5)&(dp2/dt<15.0)
        if np.any(good2):
            pv2=dp2[good2]/dt[good2]; gv2=dg[good2]/dt[good2]
            smooth_err.extend((pv2-gv2).tolist()); smooth_pred+=float(dp2[good2].sum()); smooth_true+=float(dg[good2].sum())
        per_player[str(int(pid))]={
            'samples':int(len(g)),
            'position_mae_m':float(g.position_error_m.mean()),
            'truth_distance_observed_m':float(dg[good].sum()),
            'pred_distance_observed_m':float(dp[good].sum()),
        }
    if raw_err:
        a=np.asarray(raw_err,float)
        out.update({
            'raw_speed_mae_mps':float(np.mean(np.abs(a))),
            'raw_speed_rmse_mps':float(np.sqrt(np.mean(a*a))),
            'raw_speed_bias_mps':float(np.mean(a)),
            'raw_speed_samples':int(len(a)),
            'raw_distance_pred_m':raw_pred,
            'raw_distance_truth_m':raw_true,
            'raw_distance_error_pct':float(100*(raw_pred-raw_true)/max(raw_true,1e-6)),
        })
    if smooth_err:
        a=np.asarray(smooth_err,float)
        out.update({
            'speed_mae_mps':float(np.mean(np.abs(a))),
            'speed_rmse_mps':float(np.sqrt(np.mean(a*a))),
            'speed_bias_mps':float(np.mean(a)),
            'speed_samples':int(len(a)),
            'distance_pred_m':smooth_pred,
            'distance_truth_m':smooth_true,
            'distance_error_pct':float(100*(smooth_pred-smooth_true)/max(smooth_true,1e-6)),
        })
    out['per_player']=per_player
    return out


def geometry_diagnostic(tracks, frames, calibration_seconds, max_cost=8.0):
    """Diagnostic only: Hungarian match projected detections to GT per frame.

    This intentionally uses holdout GT solely to quantify geometry/detection error.
    It is NEVER used to assign persistent player identity or tune a holdout track.
    """
    by_frame={}
    for tr in tracks:
        for o in tr.obs:
            if o['t']<=calibration_seconds or 'xy' not in o: continue
            by_frame.setdefault(o['fi'],[]).append(np.asarray(o['xy'],float))
    errs=[]; matched=0; gt_total=0; pred_total=0
    region_errs={}
    for fi,preds_list in by_frame.items():
        gt=frames[fi]['gt']; gt_total+=len(gt); pred_total+=len(preds_list)
        if not gt or not preds_list: continue
        P=np.asarray(preds_list,float)
        G=np.asarray([[g['x'],g['y']] for g in gt],float)
        C=np.linalg.norm(P[:,None,:]-G[None,:,:],axis=2)
        ri,ci=linear_sum_assignment(C)
        for r,c in zip(ri,ci):
            d=float(C[r,c])
            if d>max_cost: continue
            errs.append(d); matched+=1
            # World-x region exposes stitched-panorama geometry problems.
            rx='left' if G[c,0]<35 else ('center' if G[c,0]<70 else 'right')
            region_errs.setdefault(rx,[]).append(d)
    if not errs:
        return {'matched':0,'gt_points':gt_total,'detections':pred_total}
    a=np.asarray(errs,float)
    return {
        'matched':matched,'gt_points':gt_total,'detections':pred_total,
        'recall':matched/max(1,gt_total),'precision_proxy':matched/max(1,pred_total),
        'mae_m':float(a.mean()),'rmse_m':float(np.sqrt(np.mean(a*a))),
        'p95_m':float(np.percentile(a,95)),
        'regions':{k:{'n':len(v),'mae_m':float(np.mean(v)),'p95_m':float(np.percentile(v,95))} for k,v in region_errs.items()},
        'note':'diagnostic uses holdout GT for measurement only; persistent identity remains frozen from calibration',
    }


# Critical V7 change: do NOT let a permissive post-pass reconnect fragments that
# the strict physical tracker deliberately split.
def no_relink(tracks):
    return tracks


_original_evaluate=v5.evaluate

def evaluate_v7(tracks,mapping,frames,calibration_seconds,outdir):
    # v5.evaluate resolves its global summarize symbol at runtime.
    old=v5.summarize
    v5.summarize=summarize_physical
    try:
        metrics=_original_evaluate(tracks,mapping,frames,calibration_seconds,outdir)
    finally:
        v5.summarize=old
    metrics['geometry_only_diagnostic']=geometry_diagnostic(tracks,frames,calibration_seconds)
    metrics['distance_truth_source']='sensor_xy_deltas'
    metrics['post_relinking_disabled']=True
    return metrics

v5.relink_tracklets=no_relink
v5.evaluate=evaluate_v7
v5.summarize=summarize_physical

if __name__=='__main__':
    v5.main()
