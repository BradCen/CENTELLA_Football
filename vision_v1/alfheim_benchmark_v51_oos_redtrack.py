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

SEGMENT_VIDEO_START_S = 23.251115 - 12.794293
SAMPLE_FPS = 8.0
CALIBRATION_SECONDS = 3.0
RED_THRESHOLD = 0.035
CONF_THRESHOLD = 0.25
MIN_HEIGHT = 11.0
TOP_K_PER_CAMERA = 14


class _KeepAll:
    def keep(self, _d):
        return True


def truth_at_oos(truth_by, t):
    return base.truth_at(truth_by, float(t) + SEGMENT_VIDEO_START_S)


def image_only_filter(frame, detections):
    selected = []
    for d in detections:
        score = v2.jersey_red_score(frame, d['box'])
        h = float(d['box'][3] - d['box'][1])
        conf = float(d.get('conf', 0.0))
        if score < RED_THRESHOLD or conf < CONF_THRESHOLD or h < MIN_HEIGHT:
            continue
        x = dict(d)
        x['red_score'] = float(score)
        selected.append(x)
    selected.sort(key=lambda d: (d['red_score'], d.get('conf', 0.0)), reverse=True)
    return selected[:TOP_K_PER_CAMERA]


def build_frames(cam_paths):
    from ultralytics import YOLO
    detector = YOLO('yolo11n.pt')
    caps = {c: cv2.VideoCapture(path) for c, path in cam_paths.items()}
    fps = {c: float(cap.get(cv2.CAP_PROP_FPS) or 25.0) for c, cap in caps.items()}
    duration = min((caps[c].get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps[c] for c in caps)
    times = np.arange(0.4, max(0.41, duration - 0.2), 1.0 / SAMPLE_FPS)
    models = {c: v10.seed_model(c) for c in cam_paths}
    keep_all = {c: _KeepAll() for c in cam_paths}
    frames = []
    counts = defaultdict(list)
    for idx, t in enumerate(times):
        entries = {}
        for cam, cap in caps.items():
            cap.set(cv2.CAP_PROP_POS_MSEC, float(t * 1000.0))
            ok, frame = cap.read()
            if not ok:
                continue
            raw = v9.detect_native(detector, frame)
            on_pitch = v10.on_pitch(cam, raw, models[cam])
            det = image_only_filter(frame, on_pitch)
            counts[cam].append(len(det))
            entries[cam] = {'t': float(t), 'det': det}
        fused = v10.fuse_frame(entries, keep_all, models)
        frames.append({'t': float(t), 'fused': fused})
        if idx % 8 == 0:
            print(f't={t:.2f}s selected=' + ','.join(f'c{c}:{len(entries[c]["det"]) if c in entries else 0}' for c in cam_paths) + f' fused={len(fused)}', flush=True)
    for cap in caps.values():
        cap.release()
    return frames, duration, {str(c): {
        'mean_selected': float(np.mean(v)) if v else 0.0,
        'max_selected': int(max(v)) if v else 0,
        'red_threshold': RED_THRESHOLD,
        'confidence_threshold': CONF_THRESHOLD,
        'min_height_px': MIN_HEIGHT,
        'top_k': TOP_K_PER_CAMERA,
    } for c, v in counts.items()}


def framewise_geometry_eval(frames, truth_by, after_s):
    errors = []; matches = 0; gt_points = 0; detections = 0
    for f in frames:
        if f['t'] <= after_s: continue
        pred = np.asarray([d['xy'] for d in f['fused']], float) if f['fused'] else np.empty((0, 2))
        gt = truth_at_oos(truth_by, f['t']); gt_points += len(gt); detections += len(pred)
        if len(pred) == 0 or not gt: continue
        G = np.asarray([[g['x'], g['y']] for g in gt], float); C = np.linalg.norm(pred[:,None,:]-G[None,:,:],axis=2)
        ri, ci = linear_sum_assignment(C)
        for i,j in zip(ri,ci):
            if C[i,j] <= 4.0: errors.append(float(C[i,j])); matches += 1
    a=np.asarray(errors,float)
    return {'matched':matches,'gt_points':gt_points,'detections':detections,'recall_proxy':matches/max(1,gt_points),'precision_proxy':matches/max(1,detections),'mae_m':float(a.mean()) if len(a) else None,'rmse_m':float(np.sqrt(np.mean(a*a))) if len(a) else None,'p95_m':float(np.percentile(a,95)) if len(a) else None}


def map_tracks_for_evaluation(tracks, truth_by, after_s):
    eligible=[]
    for tr in tracks:
        cal=[o for o in tr.obs if o['t']<=after_s]; hold=[o for o in tr.obs if o['t']>after_s]
        if len(cal)>=6 and len(hold)>=3: eligible.append(tr)
    target_ids=list(v10.TARGET_IDS); rows=[]; tids=[]
    for tr in eligible:
        vals=[]
        for gid in target_ids:
            ee=[]
            for o in tr.obs:
                if o['t']>after_s: break
                gt={g['id']:g for g in truth_at_oos(truth_by,o['t'])}
                if gid in gt: ee.append(np.linalg.norm(o['xy']-np.asarray([gt[gid]['x'],gt[gid]['y']],float)))
            vals.append(float(np.median(ee)) if ee else 99.0)
        rows.append(vals); tids.append(tr.tid)
    if not rows: return {}, []
    C=np.asarray(rows,float); ri,ci=linear_sum_assignment(C); mapping={}; diag=[]
    for r,c in zip(ri,ci):
        mapping[tids[r]]=target_ids[c]
        sr=np.sort(C[r]); diag.append({'track_id':int(tids[r]),'gt_id':int(target_ids[c]),'calibration_median_m':float(C[r,c]),'identity_margin_m':float(sr[1]-sr[0]) if len(sr)>1 else 99.0})
    return mapping,diag


def persistent_eval(tracks,mapping,truth_by,after_s):
    errors=[]; by=defaultdict(list)
    for tr in tracks:
        gid=mapping.get(tr.tid)
        if gid is None: continue
        for o in tr.obs:
            if o['t']<=after_s: continue
            gt={g['id']:g for g in truth_at_oos(truth_by,o['t'])}
            if gid not in gt: continue
            q=np.asarray([gt[gid]['x'],gt[gid]['y']],float); e=float(np.linalg.norm(o['xy']-q)); errors.append(e); by[gid].append(e)
    a=np.asarray(errors,float)
    return {'mapped_samples':len(errors),'mapped_tracks':len(mapping),'mae_m':float(a.mean()) if len(a) else None,'rmse_m':float(np.sqrt(np.mean(a*a))) if len(a) else None,'p95_m':float(np.percentile(a,95)) if len(a) else None,'per_player':{str(g):{'samples':len(v),'mae_m':float(np.mean(v)) if v else None} for g,v in sorted(by.items())}}


def main():
    import argparse
    ap=argparse.ArgumentParser()
    for i in range(3): ap.add_argument(f'--cam{i}',required=True)
    ap.add_argument('--truth',required=True); ap.add_argument('--out',required=True)
    args=ap.parse_args(); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    frames,duration,det_diag=build_frames({0:args.cam0,1:args.cam1,2:args.cam2})
    tracks=v10.track_world(frames)
    truth_by=base.load_truth(args.truth,video_start=v10.NATIVE_START)
    geometry=framewise_geometry_eval(frames,truth_by,CALIBRATION_SECONDS)
    mapping,mapping_diag=map_tracks_for_evaluation(tracks,truth_by,CALIBRATION_SECONDS)
    persistent=persistent_eval(tracks,mapping,truth_by,CALIBRATION_SECONDS)
    result={'version':'v51-oos-image-only-redtrack','segment':'0059-0061','duration_s':duration,'sample_fps':SAMPLE_FPS,'calibration_seconds':CALIBRATION_SECONDS,'inference_uses_ground_truth':False,'inference_policy':'YOLO person + static pitch ROI + red-jersey score + confidence/size heuristic + anonymous optical/world tracking','framewise_geometry_evaluation':geometry,'persistent_track_evaluation':persistent,'posthoc_evaluation_mapping':True,'track_count':len(tracks),'mapping_count':len(mapping),'mapping':mapping_diag,'detector_selection_diagnostics':det_diag,'truth_usage':'evaluation only after anonymous tracks are constructed'}
    (out/'metrics.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    pd.DataFrame([{'t':o['t'],'track_id':tr.tid,'pred_x':float(o['xy'][0]),'pred_y':float(o['xy'][1])} for tr in tracks for o in tr.obs]).to_csv(out/'anonymous_tracks.csv',index=False)
    print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__': main()
