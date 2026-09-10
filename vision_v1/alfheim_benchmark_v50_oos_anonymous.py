from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

import alfheim_benchmark as base
import alfheim_benchmark_v10 as v10

SEGMENT_VIDEO_START_S = 23.251115 - 12.794293
SAMPLE_FPS = 8.0
CALIBRATION_SECONDS = 3.0


def truth_at_oos(truth_by, t: float):
    return base.truth_at(truth_by, float(t) + SEGMENT_VIDEO_START_S)


def framewise_geometry_eval(frames, truth_by, after_s: float):
    errors = []
    matches = 0
    gt_points = 0
    detections = 0
    for f in frames:
        if f['t'] <= after_s:
            continue
        pred = np.asarray([d['xy'] for d in f['fused']], float) if f['fused'] else np.empty((0, 2))
        gt = truth_at_oos(truth_by, f['t'])
        gt_points += len(gt)
        detections += len(pred)
        if len(pred) == 0 or not gt:
            continue
        G = np.asarray([[g['x'], g['y']] for g in gt], float)
        C = np.linalg.norm(pred[:, None, :] - G[None, :, :], axis=2)
        ri, ci = linear_sum_assignment(C)
        # No inference-time GT gate; 4m is evaluation-only and matches the historical benchmark convention.
        for i, j in zip(ri, ci):
            if C[i, j] <= 4.0:
                errors.append(float(C[i, j]))
                matches += 1
    a = np.asarray(errors, float)
    return {
        'matched': matches,
        'gt_points': gt_points,
        'detections': detections,
        'recall_proxy': matches / max(1, gt_points),
        'precision_proxy': matches / max(1, detections),
        'mae_m': float(a.mean()) if len(a) else None,
        'rmse_m': float(np.sqrt(np.mean(a * a))) if len(a) else None,
        'p95_m': float(np.percentile(a, 95)) if len(a) else None,
    }


def map_tracks_for_evaluation(tracks, truth_by, calibration_seconds: float):
    """Map anonymous tracks to randomized GT IDs strictly for post-hoc evaluation."""
    eligible = []
    for tr in tracks:
        cal = [o for o in tr.obs if o['t'] <= calibration_seconds]
        hold = [o for o in tr.obs if o['t'] > calibration_seconds]
        if len(cal) >= 6 and len(hold) >= 3:
            eligible.append(tr)
    if not eligible:
        return {}, []

    target_ids = list(v10.TARGET_IDS)
    rows = []
    tids = []
    for tr in eligible:
        vals = []
        for gid in target_ids:
            ee = []
            for o in tr.obs:
                if o['t'] > calibration_seconds:
                    break
                gt = {g['id']: g for g in truth_at_oos(truth_by, o['t'])}
                if gid in gt:
                    ee.append(np.linalg.norm(o['xy'] - np.asarray([gt[gid]['x'], gt[gid]['y']], float)))
            vals.append(float(np.median(ee)) if ee else 99.0)
        rows.append(vals)
        tids.append(tr.tid)
    C = np.asarray(rows, float)
    ri, ci = linear_sum_assignment(C)
    mapping = {}
    diag = []
    for r, c in zip(ri, ci):
        mapping[tids[r]] = target_ids[c]
        sr = np.sort(C[r])
        margin = float(sr[1] - sr[0]) if len(sr) > 1 else 99.0
        diag.append({
            'track_id': int(tids[r]),
            'gt_id': int(target_ids[c]),
            'calibration_median_m': float(C[r, c]),
            'identity_margin_m': margin,
        })
    return mapping, diag


def persistent_eval(tracks, mapping, truth_by, after_s: float):
    errors = []
    by_player = defaultdict(list)
    for tr in tracks:
        gid = mapping.get(tr.tid)
        if gid is None:
            continue
        for o in tr.obs:
            if o['t'] <= after_s:
                continue
            gt = {g['id']: g for g in truth_at_oos(truth_by, o['t'])}
            if gid not in gt:
                continue
            q = np.asarray([gt[gid]['x'], gt[gid]['y']], float)
            e = float(np.linalg.norm(o['xy'] - q))
            errors.append(e)
            by_player[gid].append(e)
    a = np.asarray(errors, float)
    per_player = {str(g): {
        'samples': len(v),
        'mae_m': float(np.mean(v)) if v else None,
        'p95_m': float(np.percentile(v, 95)) if v else None,
    } for g, v in sorted(by_player.items())}
    return {
        'mapped_samples': len(errors),
        'mapped_tracks': len(mapping),
        'mae_m': float(a.mean()) if len(a) else None,
        'rmse_m': float(np.sqrt(np.mean(a * a))) if len(a) else None,
        'p95_m': float(np.percentile(a, 95)) if len(a) else None,
        'per_player': per_player,
    }


def build_frames(cam_paths):
    import cv2
    from ultralytics import YOLO
    detector = YOLO('yolo11n.pt')
    caps = {c: cv2.VideoCapture(path) for c, path in cam_paths.items()}
    fps = {c: float(cap.get(cv2.CAP_PROP_FPS) or 25.0) for c, cap in caps.items()}
    duration = min((caps[c].get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps[c] for c in caps)
    times = np.arange(0.4, max(0.41, duration - 0.2), 1.0 / SAMPLE_FPS)
    frames = []
    models = {c: v10.seed_model(c) for c in cam_paths}

    for idx, t in enumerate(times):
        entries = {}
        for cam, cap in caps.items():
            cap.set(cv2.CAP_PROP_POS_MSEC, float(t * 1000.0))
            ok, frame = cap.read()
            if not ok:
                continue
            raw = base.detect_native(detector, frame)
            det = v10.on_pitch(cam, raw, models[cam])
            entries[cam] = {'t': float(t), 'det': det}
        fused = v10.fuse_frame(entries, {0: None, 1: None, 2: None}, models)
        frames.append({'t': float(t), 'fused': fused})
        if idx % 8 == 0:
            print(f't={t:.2f}s fused={len(fused)}', flush=True)
    for cap in caps.values():
        cap.release()
    return frames, duration


def main():
    import argparse
    ap = argparse.ArgumentParser()
    for i in range(3):
        ap.add_argument(f'--cam{i}', required=True)
    ap.add_argument('--truth', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    frames, duration = build_frames({0: args.cam0, 1: args.cam1, 2: args.cam2})
    # The tracker sees only video detections and static seed geometry. No truth is passed here.
    tracks = v10.track_world(frames)
    truth_by = base.load_truth(args.truth, video_start=v10.NATIVE_START)

    geometry = framewise_geometry_eval(frames, truth_by, CALIBRATION_SECONDS)
    mapping, mapping_diag = map_tracks_for_evaluation(tracks, truth_by, CALIBRATION_SECONDS)
    persistent = persistent_eval(tracks, mapping, truth_by, CALIBRATION_SECONDS)

    rows = []
    for tr in tracks:
        gid = mapping.get(tr.tid)
        if gid is None:
            continue
        for o in tr.obs:
            if o['t'] <= CALIBRATION_SECONDS:
                continue
            gt = {g['id']: g for g in truth_at_oos(truth_by, o['t'])}
            if gid not in gt:
                continue
            rows.append({
                't': o['t'], 'track_id': tr.tid, 'gt_id': gid,
                'pred_x': float(o['xy'][0]), 'pred_y': float(o['xy'][1]),
                'truth_x': float(gt[gid]['x']), 'truth_y': float(gt[gid]['y']),
                'position_error_m': float(np.linalg.norm(o['xy'] - np.asarray([gt[gid]['x'], gt[gid]['y']], float))),
                'camera_count': len(o['cams']), 'cams': ','.join(map(str, o['cams'])),
            })

    result = {
        'version': 'v50-oos-anonymous-video-only-inference',
        'segment': '0059-0061',
        'duration_s': duration,
        'sample_fps': SAMPLE_FPS,
        'calibration_seconds': CALIBRATION_SECONDS,
        'inference_uses_ground_truth': False,
        'inference_uses_static_seed_geometry_only': True,
        'framewise_geometry_evaluation': geometry,
        'persistent_track_evaluation': persistent,
        'posthoc_evaluation_mapping': True,
        'mapping_count': len(mapping),
        'track_count': len(tracks),
        'mapping': mapping_diag,
        'truth_usage': 'evaluation only after anonymous tracks are constructed',
        'note': 'GT/randomized player IDs are never used to initialize or update tracks during inference.',
    }
    (out / 'metrics.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    pd.DataFrame(rows).to_csv(out / 'matched_observations.csv', index=False)
    (out / 'track_identity_mapping.json').write_text(json.dumps(mapping_diag, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
