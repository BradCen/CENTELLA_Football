from __future__ import annotations
import cv2
import numpy as np
import pandas as pd
import alfheim_benchmark_v4 as v4
from alfheim_benchmark_v3 import summarize


def evaluate_fixed(tracks, mapping, frames, calibration_seconds, outdir):
    rows=[]
    total_gt=sum(len(f['gt']) for f in frames if f['t']>calibration_seconds)
    total_det=sum(1 for tr in tracks for o in tr.obs if o['t']>calibration_seconds)
    first_eval=None
    for tr in tracks:
        gid=mapping.get(tr.tid)
        if gid is None:
            continue
        for o in tr.obs:
            if o['t']<=calibration_seconds:
                continue
            f=frames[o['fi']]
            gt={g['id']:g for g in f['gt']}
            if gid not in gt:
                continue
            g=gt[gid]
            err=float(np.linalg.norm(o['xy']-np.array([g['x'],g['y']],float)))
            rows.append({
                't':o['t'],'track_id':tr.tid,'gt_id':gid,
                'pred_x':o['xy'][0],'pred_y':o['xy'][1],
                'truth_x':g['x'],'truth_y':g['y'],'position_error_m':err,
                'truth_speed':g['speed'],'truth_total_distance':g['total_distance'],
                'pixel_x':o['pix'][0],'pixel_y':o['pix'][1]
            })
            if first_eval is None:
                first_eval=o['fi']
    pd.DataFrame(rows).to_csv(outdir/'matched_observations.csv',index=False)
    metrics=summarize(rows,total_gt,total_det)
    metrics.update({
        'mapped_track_observations':len(rows),
        'mapped_tracks':len(mapping),
        'all_tracks':len(tracks),
        'identity_frozen_holdout':True,
    })
    lengths=[sum(o['t']>calibration_seconds for o in tr.obs) for tr in tracks if tr.tid in mapping]
    metrics['mapped_track_mean_holdout_samples']=float(np.mean(lengths)) if lengths else 0.0
    metrics['mapped_track_max_holdout_samples']=int(max(lengths)) if lengths else 0
    if first_eval is not None:
        img=frames[first_eval]['frame'].copy()
        for tr in tracks:
            gid=mapping.get(tr.tid)
            if gid is None: continue
            for o in tr.obs:
                if o['fi']!=first_eval: continue
                x,y=map(int,o['pix'])
                cv2.circle(img,(x,y),10,(0,255,0),3)
                cv2.putText(img,f'T{tr.tid}->GT{gid}',(x+8,y-8),0,.55,(0,255,0),2)
        cv2.imwrite(str(outdir/'annotated_eval_frame.jpg'),img)
    return metrics

v4.evaluate=evaluate_fixed

if __name__=='__main__':
    v4.main()
