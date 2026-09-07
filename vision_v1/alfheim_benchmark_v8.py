from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from alfheim_benchmark import detect_tiled, load_truth, truth_at, rough_project, assign
from alfheim_benchmark_v2 import jersey_red_score, choose_team_threshold
from alfheim_benchmark_v3 import appearance_feature, fit_geometry, project_geometry
import alfheim_benchmark_v5 as v5
import alfheim_benchmark_v6 as v6
from alfheim_benchmark_v7 import summarize_physical


class LocalGeometry:
    """Robust global polynomial + local affine correction.

    Alfheim's stitched panorama is cylindrical/non-linear. A single homography or
    global polynomial cannot model all five source-camera regions. This model
    learns the broad mapping globally, then estimates a local affine transform
    around each query using calibration correspondences only.
    """

    def __init__(self, coef, cal_pix, cal_world, k=16, sx=620.0, sy=260.0):
        self.coef = np.asarray(coef, float)
        self.cal_pix = np.asarray(cal_pix, float)
        self.cal_world = np.asarray(cal_world, float)
        self.k = int(k)
        self.sx = float(sx)
        self.sy = float(sy)

    def global_project(self, pix):
        p = np.asarray(pix, float)
        if len(p) == 0:
            return np.empty((0, 2), float)
        return project_geometry(p, self.coef)

    def _one(self, q, exclude_mask=None):
        q = np.asarray(q, float)
        if exclude_mask is None:
            keep = np.ones(len(self.cal_pix), bool)
        else:
            keep = ~np.asarray(exclude_mask, bool)
        P = self.cal_pix[keep]
        W = self.cal_world[keep]
        if len(P) < 6:
            return self.global_project(q[None, :])[0]

        d = np.sqrt(((P[:, 0] - q[0]) / self.sx) ** 2 + ((P[:, 1] - q[1]) / self.sy) ** 2)
        order = np.argsort(d)
        kk = min(self.k, len(order))
        idx = order[:kk]
        Pn = P[idx]
        Wn = W[idx]
        dn = d[idx]

        # If the query lies well outside calibrated support, do not extrapolate a
        # local model wildly; fall back to the robust global polynomial.
        if float(np.median(dn[: min(5, len(dn))])) > 2.35:
            return self.global_project(q[None, :])[0]

        # Centered local affine map. The intercept is the prediction at q.
        X = np.column_stack([
            np.ones(len(Pn)),
            (Pn[:, 0] - q[0]) / self.sx,
            (Pn[:, 1] - q[1]) / self.sy,
        ])
        scale = max(0.18, float(np.median(dn)) + 0.08)
        wt = np.exp(-0.5 * (dn / scale) ** 2) + 0.03
        A = X.T @ (wt[:, None] * X)
        A += np.diag([1e-6, 2e-3, 2e-3])
        B = X.T @ (wt[:, None] * Wn)
        try:
            beta = np.linalg.solve(A, B)
            local = beta[0]
        except np.linalg.LinAlgError:
            local = self.global_project(q[None, :])[0]

        # Blend with global model when local support is weak.
        g = self.global_project(q[None, :])[0]
        support = float(np.median(dn[: min(6, len(dn))]))
        alpha = float(np.clip(1.0 - support / 2.2, 0.25, 0.94))
        return alpha * local + (1.0 - alpha) * g

    def project(self, pix):
        p = np.asarray(pix, float)
        if len(p) == 0:
            return np.empty((0, 2), float)
        return np.asarray([self._one(q) for q in p], float)


def team_persons(frame_entry, threshold):
    return [d for d in frame_entry['all_persons'] if float(d['team_score']) >= threshold]


def collect_pairs(frames, calibration_seconds, threshold, projector=None, max_cost=12.0):
    pix_all = []
    world_all = []
    frame_ids = []
    costs = []
    for fi, f in enumerate(frames):
        if f['t'] > calibration_seconds:
            continue
        persons = team_persons(f, threshold)
        pix = np.asarray([d['foot'] for d in persons], float) if persons else np.empty((0, 2), float)
        if len(pix) == 0 or not f['gt']:
            continue
        pred = rough_project(pix) if projector is None else projector(pix)
        matches = assign(pred, f['gt'], max_cost)
        for i, j, c in matches:
            g = f['gt'][j]
            pix_all.append(pix[i])
            world_all.append([g['x'], g['y']])
            frame_ids.append(fi)
            costs.append(float(c))
    return np.asarray(pix_all, float), np.asarray(world_all, float), np.asarray(frame_ids, int), costs


def robust_pair_filter(pix, world, frame_ids):
    if len(pix) < 12:
        return pix, world, frame_ids, np.ones(len(pix), bool)
    coef, mask = fit_geometry(pix, world)
    err = np.linalg.norm(project_geometry(pix, coef) - world, axis=1)
    med = float(np.median(err))
    mad = float(np.median(np.abs(err - med))) + 1e-6
    lim = min(3.0, max(1.05, med + 2.5 * 1.4826 * mad))
    good = err <= lim
    if int(good.sum()) < 12:
        good = mask
    return pix[good], world[good], frame_ids[good], good


def tune_local_k(coef, pix, world, frame_ids):
    candidates = [8, 12, 16, 22, 30]
    rows = []
    unique_frames = sorted(set(frame_ids.tolist()))
    # Leave one calibration frame out at a time. This prevents a point from
    # evaluating against the exact same-frame correspondences used to fit it.
    for k in candidates:
        errs = []
        for fi in unique_frames:
            test = frame_ids == fi
            if int((~test).sum()) < 8 or int(test.sum()) == 0:
                continue
            model = LocalGeometry(coef, pix[~test], world[~test], k=k)
            pred = model.project(pix[test])
            errs.extend(np.linalg.norm(pred - world[test], axis=1).tolist())
        if errs:
            a = np.asarray(errs, float)
            rows.append({'k': k, 'cv_mae_m': float(a.mean()), 'cv_p95_m': float(np.percentile(a, 95)), 'n': len(a)})
    if not rows:
        return 16, []
    best = min(rows, key=lambda r: (r['cv_mae_m'], r['cv_p95_m']))
    return int(best['k']), rows


def calibrate_local_geometry(frames, calibration_seconds, threshold):
    # Stage 1: rough field model, then progressively tighter re-assignment.
    pix, world, fids, costs = collect_pairs(frames, calibration_seconds, threshold, None, 12.0)
    if len(pix) < 12:
        raise RuntimeError(f'Insufficient calibration pairs: {len(pix)}')

    history = []
    coef = None
    model = None
    for it, max_cost in enumerate([8.0, 5.0, 3.5, 2.6]):
        pix, world, fids, _ = robust_pair_filter(pix, world, fids)
        coef, mask = fit_geometry(pix, world)
        k, cv = tune_local_k(coef, pix, world, fids)
        model = LocalGeometry(coef, pix, world, k=k)
        fit_err = np.linalg.norm(model.project(pix) - world, axis=1)
        history.append({
            'iteration': it,
            'pairs': int(len(pix)),
            'k': int(k),
            'train_mae_m': float(fit_err.mean()),
            'train_p95_m': float(np.percentile(fit_err, 95)),
            'max_assignment_m_next': float(max_cost),
            'cv': cv,
        })
        pix2, world2, fids2, costs2 = collect_pairs(
            frames, calibration_seconds, threshold, model.project, max_cost
        )
        if len(pix2) < 12:
            break
        pix, world, fids = pix2, world2, fids2

    pix, world, fids, _ = robust_pair_filter(pix, world, fids)
    coef, _ = fit_geometry(pix, world)
    k, cv = tune_local_k(coef, pix, world, fids)
    model = LocalGeometry(coef, pix, world, k=k)
    return model, pix, world, fids, history, cv


def attach_world_local(tracks, model):
    for tr in tracks:
        if not tr.obs:
            continue
        pix = np.asarray([o['pix'] for o in tr.obs], float)
        xy = model.project(pix)
        for o, p in zip(tr.obs, xy):
            o['xy'] = np.asarray(p, float)


def persistent_evaluate(tracks, mapping, frames, calibration_seconds, outdir):
    rows = []
    total_gt = sum(len(f['gt']) for f in frames if f['t'] > calibration_seconds)
    total_det = sum(1 for tr in tracks for o in tr.obs if o['t'] > calibration_seconds)
    first_eval = None
    for tr in tracks:
        gid = mapping.get(tr.tid)
        if gid is None:
            continue
        for o in tr.obs:
            if o['t'] <= calibration_seconds:
                continue
            gt = {g['id']: g for g in frames[o['fi']]['gt']}
            if gid not in gt:
                continue
            g = gt[gid]
            truth = np.array([g['x'], g['y']], float)
            err = float(np.linalg.norm(o['xy'] - truth))
            rows.append({
                't': o['t'], 'track_id': tr.tid, 'gt_id': gid,
                'pred_x': o['xy'][0], 'pred_y': o['xy'][1],
                'truth_x': g['x'], 'truth_y': g['y'],
                'position_error_m': err, 'truth_speed': g['speed'],
                'truth_total_distance': g['total_distance'],
                'pixel_x': o['pix'][0], 'pixel_y': o['pix'][1],
            })
            if first_eval is None:
                first_eval = o['fi']
    pd.DataFrame(rows).to_csv(outdir / 'matched_observations.csv', index=False)
    metrics = summarize_physical(rows, total_gt, total_det)
    crossing = [tr for tr in tracks if tr.start_t <= calibration_seconds < tr.end_t]
    mapped_ids = sorted(set(mapping.values()))
    gt_ids = sorted({g['id'] for f in frames if f['t'] > calibration_seconds for g in f['gt']})
    metrics.update({
        'identity_frozen_holdout': True,
        'mapped_tracks': len(mapping),
        'mapped_gt_ids': mapped_ids,
        'gt_ids_in_holdout': len(gt_ids),
        'identity_id_coverage': len(mapped_ids) / max(1, len(gt_ids)),
        'all_tracks': len(tracks),
        'crossing_tracks': len(crossing),
        'mapped_track_observations': len(rows),
        'track_mean_samples': float(np.mean([len(t.obs) for t in tracks])) if tracks else 0.0,
        'track_median_samples': float(np.median([len(t.obs) for t in tracks])) if tracks else 0.0,
        'track_max_samples': int(max([len(t.obs) for t in tracks], default=0)),
    })

    if first_eval is not None:
        img = frames[first_eval]['frame'].copy()
        for tr in tracks:
            gid = mapping.get(tr.tid)
            if gid is None:
                continue
            for o in tr.obs:
                if o['fi'] != first_eval:
                    continue
                x, y = map(int, o['pix'])
                cv2.circle(img, (x, y), 10, (0, 255, 0), 3)
                cv2.putText(img, f'T{tr.tid}->GT{gid}', (x + 6, y - 6), 0, .55, (0, 255, 0), 2)
        cv2.imwrite(str(outdir / 'annotated_eval_frame.jpg'), img)
    return metrics


def geometry_diagnostic(frames, calibration_seconds, threshold, model, max_cost=6.0):
    errs = []
    gt_total = det_total = matched = 0
    regions = {}
    for f in frames:
        if f['t'] <= calibration_seconds:
            continue
        persons = team_persons(f, threshold)
        pix = np.asarray([d['foot'] for d in persons], float) if persons else np.empty((0, 2), float)
        pred = model.project(pix) if len(pix) else np.empty((0, 2), float)
        G = np.asarray([[g['x'], g['y']] for g in f['gt']], float) if f['gt'] else np.empty((0, 2), float)
        gt_total += len(G); det_total += len(pred)
        if len(G) == 0 or len(pred) == 0:
            continue
        C = np.linalg.norm(pred[:, None, :] - G[None, :, :], axis=2)
        ri, ci = linear_sum_assignment(C)
        for r, c in zip(ri, ci):
            d = float(C[r, c])
            if d > max_cost:
                continue
            errs.append(d); matched += 1
            # Pixel band is a better diagnostic for a stitched panorama than
            # arbitrary world-x thirds.
            band = int(np.clip(pix[r, 0] // 890, 0, 4))
            regions.setdefault(str(band), []).append(d)
    if not errs:
        return {'matched': 0, 'gt_points': gt_total, 'detections': det_total}
    a = np.asarray(errs, float)
    return {
        'matched': matched,
        'gt_points': gt_total,
        'detections': det_total,
        'recall': matched / max(1, gt_total),
        'precision_proxy': matched / max(1, det_total),
        'mae_m': float(a.mean()),
        'rmse_m': float(np.sqrt(np.mean(a * a))),
        'p95_m': float(np.percentile(a, 95)),
        'pixel_bands': {k: {'n': len(v), 'mae_m': float(np.mean(v)), 'p95_m': float(np.percentile(v, 95))} for k, v in regions.items()},
        'note': 'holdout GT is used only to measure geometry; it never tunes the model or assigns persistent identity',
    }


def add_stable_distance_metrics(metrics, min_truth_m=5.0):
    # Percentage error is meaningless when observed truth distance is near zero.
    for prefix in ['', 'raw_']:
        tkey = f'{prefix}distance_truth_m'
        pkey = f'{prefix}distance_pred_m'
        ekey = f'{prefix}distance_error_pct'
        if tkey in metrics and pkey in metrics:
            truth = float(metrics[tkey]); pred = float(metrics[pkey])
            metrics[f'{prefix}distance_abs_error_m'] = abs(pred - truth)
            if truth < min_truth_m:
                metrics.pop(ekey, None)
                metrics[f'{prefix}distance_error_pct_status'] = f'suppressed: truth distance < {min_truth_m} m'
    return metrics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--video', required=True)
    ap.add_argument('--truth', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--sample-fps', type=float, default=12.0)
    ap.add_argument('--calibration-seconds', type=float, default=4.0)
    ap.add_argument('--model', default='yolo11n.pt')
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    from ultralytics import YOLO
    detector = YOLO(args.model)
    truth_by = load_truth(args.truth)
    cap = cv2.VideoCapture(args.video)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25)
    dur = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) / fps
    times = np.arange(.5, max(.51, dur - .25), 1.0 / args.sample_fps)
    frames = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t * 1000))
        ok, frame = cap.read()
        if not ok:
            continue
        persons = [d for d in detect_tiled(detector, frame) if d['cls'] == 'person']
        for d in persons:
            d['feat'] = appearance_feature(frame, d['box'])
            d['team_score'] = jersey_red_score(frame, d['box'])
            d['cluster'] = 0
        frames.append({'t': float(t), 'frame': frame, 'all_persons': persons, 'gt': truth_at(truth_by, float(t))})
        print(f't={t:.3f}s people={len(persons)}', flush=True)
    cap.release()

    threshold, tuning = choose_team_threshold(frames, args.calibration_seconds)
    (out / 'team_threshold_tuning.json').write_text(json.dumps(tuning, indent=2), encoding='utf-8')
    print('team_threshold=', threshold, flush=True)

    model, cal_pix, cal_world, cal_fids, history, cv = calibrate_local_geometry(
        frames, args.calibration_seconds, threshold
    )
    np.save(out / 'pixel_to_world_global_poly2.npy', model.coef)
    pd.DataFrame({
        'pixel_x': cal_pix[:, 0], 'pixel_y': cal_pix[:, 1],
        'world_x': cal_world[:, 0], 'world_y': cal_world[:, 1],
        'frame_id': cal_fids,
    }).to_csv(out / 'calibration_pairs.csv', index=False)
    (out / 'calibration_history_v8.json').write_text(json.dumps(history, indent=2), encoding='utf-8')
    (out / 'local_k_cv.json').write_text(json.dumps(cv, indent=2), encoding='utf-8')
    print('calibration_pairs=', len(cal_pix), 'local_k=', model.k, flush=True)

    # Freeze team selection before holdout. Strict V6 tracker gets only red-team
    # detections and runs in image space; no ground-truth data participates.
    for f in frames:
        f['all_persons'] = team_persons(f, threshold)
        for d in f['all_persons']:
            d['cluster'] = 0
    raw_tracks = v6.build_tracks_pixel_strict(frames, {0}, max_age=1.75)
    tracks = raw_tracks  # no post-hoc relinking in holdout
    attach_world_local(tracks, model)
    mapping, maprows = v6.map_tracks_to_truth_motion(tracks, frames, args.calibration_seconds, max_median=2.6)
    (out / 'track_identity_mapping.json').write_text(json.dumps(maprows, indent=2), encoding='utf-8')
    print(f'tracks={len(tracks)} mapping={maprows}', flush=True)

    metrics = persistent_evaluate(tracks, mapping, frames, args.calibration_seconds, out)
    metrics = add_stable_distance_metrics(metrics)
    metrics['geometry_only_diagnostic'] = geometry_diagnostic(frames, args.calibration_seconds, threshold, model)
    metrics.update({
        'version': 'v8-red-team-local-nonlinear-geometry',
        'video_duration_s': dur,
        'sample_fps': args.sample_fps,
        'calibration_seconds': args.calibration_seconds,
        'model': args.model,
        'team_threshold': threshold,
        'calibration_pairs': int(len(cal_pix)),
        'local_k': int(model.k),
        'raw_tracklets': len(raw_tracks),
        'post_relinking_disabled': True,
        'distance_truth_source': 'sensor_xy_deltas',
        'calibration_history': history,
    })
    (out / 'metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    print(json.dumps(metrics, indent=2), flush=True)


if __name__ == '__main__':
    main()
