from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from alfheim_benchmark import detect_tiled, load_truth, truth_at
from alfheim_benchmark_v3 import (
    appearance_feature,
    cluster_appearance,
    choose_cluster_subset,
    iterative_calibration,
    project_geometry,
    summarize,
)


def cosine_distance(a, b):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < 1e-9 or nb < 1e-9:
        return 1.0
    return float(1.0 - np.dot(a, b) / (na * nb))


def box_height(box):
    return max(4.0, float(box[3] - box[1]))


def kf_predict(x, P, dt):
    F = np.array([
        [1.0, 0.0, dt, 0.0],
        [0.0, 1.0, 0.0, dt],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ], float)
    # Pixel acceleration process noise. The panorama is fixed, so motion in
    # image space is substantially smoother than our imperfect world mapping.
    q = 45.0
    q2, q3, q4 = dt * dt, dt ** 3, dt ** 4
    Q = q * np.array([
        [q4 / 4, 0, q3 / 2, 0],
        [0, q4 / 4, 0, q3 / 2],
        [q3 / 2, 0, q2, 0],
        [0, q3 / 2, 0, q2],
    ], float)
    return F @ x, F @ P @ F.T + Q


def kf_update(x, P, z, sigma):
    H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], float)
    R = np.eye(2, dtype=float) * float(sigma * sigma)
    y = np.asarray(z, float) - H @ x
    S = H @ P @ H.T + R
    K = P @ H.T @ np.linalg.inv(S)
    xn = x + K @ y
    Pn = (np.eye(4) - K @ H) @ P
    return xn, Pn


@dataclass
class Track:
    tid: int
    state: np.ndarray
    cov: np.ndarray
    feat: np.ndarray
    cluster: int
    last_box: tuple
    state_t: float
    last_seen_t: float
    hits: int = 1
    misses: int = 0
    obs: list = field(default_factory=list)

    @property
    def start_t(self):
        return float(self.obs[0]['t'])

    @property
    def end_t(self):
        return float(self.obs[-1]['t'])


def make_track(tid, fi, t, det):
    px, py = map(float, det['foot'])
    h = box_height(det['box'])
    x = np.array([px, py, 0.0, 0.0], float)
    P = np.diag([max(36.0, h * h * .16), max(36.0, h * h * .16), 1600.0, 1600.0])
    tr = Track(
        tid=tid,
        state=x,
        cov=P,
        feat=np.asarray(det['feat'], float).copy(),
        cluster=int(det['cluster']),
        last_box=tuple(det['box']),
        state_t=float(t),
        last_seen_t=float(t),
    )
    tr.obs.append({
        'fi': fi, 't': float(t), 'pix': np.array([px, py], float),
        'box': tuple(det['box']), 'conf': float(det.get('conf', 0.0)),
        'cluster': int(det['cluster']),
    })
    return tr


def build_tracks_pixel(frames, selected, max_age=2.0):
    """Persistent image-space tracker independent of ground truth.

    V4 associated in world coordinates, so calibration error itself broke
    identities. V5 deliberately tracks in raw pixels with a Kalman filter,
    appearance, size and cluster consistency. World conversion happens only
    after identities are established.
    """
    tracks = []
    next_id = 1

    for fi, f in enumerate(frames):
        t = float(f['t'])
        dets = [d for d in f['all_persons'] if d['cluster'] in selected]

        # Keep predictions alive through brief detector misses.
        active = [tr for tr in tracks if t - tr.last_seen_t <= max_age]
        for tr in active:
            dt = max(0.0, t - tr.state_t)
            if dt > 0:
                tr.state, tr.cov = kf_predict(tr.state, tr.cov, dt)
                tr.state_t = t

        matched_dets = set()
        matched_tracks = set()

        if active and dets:
            C = np.full((len(active), len(dets)), 1e6, float)
            for i, tr in enumerate(active):
                pred = tr.state[:2]
                age = max(0.0, t - tr.last_seen_t)
                ph = box_height(tr.last_box)
                for j, d in enumerate(dets):
                    z = np.asarray(d['foot'], float)
                    dh = box_height(d['box'])
                    spatial = float(np.linalg.norm(z - pred))
                    scale = max(18.0, .5 * (ph + dh))
                    # Expand the gate while a track is temporarily invisible.
                    gate = max(70.0, 2.8 * scale) + 105.0 * min(age, 1.75)
                    app = cosine_distance(tr.feat, d['feat'])
                    size_pen = abs(math.log(max(1e-3, dh / ph)))
                    cluster_pen = 0.0 if int(d['cluster']) == tr.cluster else 0.65
                    if spatial > gate or app > 0.78 or size_pen > 1.35:
                        continue
                    C[i, j] = 2.15 * (spatial / gate) + 1.65 * app + .35 * size_pen + cluster_pen

            ri, ci = linear_sum_assignment(C)
            for i, j in zip(ri, ci):
                if C[i, j] > 2.65:
                    continue
                tr = active[int(i)]
                d = dets[int(j)]
                z = np.asarray(d['foot'], float)
                h = box_height(d['box'])
                sigma = max(4.0, min(13.0, .13 * h))
                tr.state, tr.cov = kf_update(tr.state, tr.cov, z, sigma)
                tr.last_seen_t = t
                tr.last_box = tuple(d['box'])
                tr.hits += 1
                tr.misses = 0
                # Slow EMA avoids one bad crop instantly changing identity.
                tr.feat = .90 * tr.feat + .10 * np.asarray(d['feat'], float)
                if int(d['cluster']) == tr.cluster:
                    pass
                tr.obs.append({
                    'fi': fi, 't': t, 'pix': z.copy(), 'box': tuple(d['box']),
                    'conf': float(d.get('conf', 0.0)), 'cluster': int(d['cluster']),
                })
                matched_dets.add(int(j))
                matched_tracks.add(tr.tid)

        for tr in active:
            if tr.tid not in matched_tracks:
                tr.misses += 1

        for j, d in enumerate(dets):
            if j in matched_dets:
                continue
            # Suppress extremely weak one-frame clutter while retaining small players.
            if float(d.get('conf', 0.0)) < 0.085:
                continue
            tracks.append(make_track(next_id, fi, t, d))
            next_id += 1

    return tracks


def fragment_link_cost(a, b):
    gap = b.start_t - a.end_t
    if gap <= 0 or gap > 2.25:
        return None
    if a.cluster != b.cluster:
        return None
    app = cosine_distance(a.feat, b.feat)
    if app > 0.52:
        return None
    a_last = np.asarray(a.obs[-1]['pix'], float)
    b_first = np.asarray(b.obs[0]['pix'], float)
    # Estimate velocity from last two observations if possible.
    vel = np.zeros(2, float)
    if len(a.obs) >= 2:
        oa, ob = a.obs[-2], a.obs[-1]
        dt = max(.05, ob['t'] - oa['t'])
        vel = (np.asarray(ob['pix'], float) - np.asarray(oa['pix'], float)) / dt
        vmag = np.linalg.norm(vel)
        if vmag > 450:
            vel *= 450 / vmag
    pred = a_last + vel * gap
    dist = float(np.linalg.norm(b_first - pred))
    h = .5 * (box_height(a.obs[-1]['box']) + box_height(b.obs[0]['box']))
    gate = max(95.0, 3.2 * h) + 125.0 * gap
    if dist > gate:
        return None
    return 2.0 * dist / gate + 1.8 * app + .12 * gap


def relink_tracklets(tracks):
    """Greedily merge short-gap fragments using vision only."""
    alive = list(tracks)
    changed = True
    while changed:
        changed = False
        candidates = []
        for i, a in enumerate(alive):
            if len(a.obs) < 2:
                continue
            for j, b in enumerate(alive):
                if i == j or b.start_t <= a.end_t:
                    continue
                c = fragment_link_cost(a, b)
                if c is not None:
                    candidates.append((c, i, j))
        if not candidates:
            break
        candidates.sort()
        used = set()
        merges = []
        for c, i, j in candidates:
            if i in used or j in used or c > 2.55:
                continue
            used.add(i); used.add(j); merges.append((i, j))
        if not merges:
            break
        remove = set()
        for i, j in merges:
            a, b = alive[i], alive[j]
            a.obs = sorted(a.obs + b.obs, key=lambda o: o['t'])
            a.hits += b.hits
            a.last_seen_t = max(a.last_seen_t, b.last_seen_t)
            a.feat = .65 * a.feat + .35 * b.feat
            remove.add(j)
            changed = True
        alive = [tr for idx, tr in enumerate(alive) if idx not in remove]
    return alive


def attach_world(tracks, coef):
    for tr in tracks:
        if not tr.obs:
            continue
        pix = np.asarray([o['pix'] for o in tr.obs], float)
        world = project_geometry(pix, coef)
        for o, xy in zip(tr.obs, world):
            o['xy'] = np.asarray(xy, float)


def map_tracks_to_truth(tracks, frames, calibration_seconds, max_median=4.0):
    # Only tracks that actually bridge calibration -> holdout can be validated
    # without leaking identity labels into holdout.
    cal_tracks = [
        tr for tr in tracks
        if sum(o['t'] <= calibration_seconds for o in tr.obs) >= 3
        and any(o['t'] > calibration_seconds for o in tr.obs)
    ]
    gt_ids = sorted({g['id'] for f in frames if f['t'] <= calibration_seconds for g in f['gt']})
    if not cal_tracks or not gt_ids:
        return {}, []
    C = np.full((len(cal_tracks), len(gt_ids)), 1e5, float)
    detail = {}
    for i, tr in enumerate(cal_tracks):
        for j, gid in enumerate(gt_ids):
            ds = []
            for o in tr.obs:
                if o['t'] > calibration_seconds:
                    continue
                gt = {g['id']: g for g in frames[o['fi']]['gt']}
                if gid in gt:
                    ds.append(float(np.linalg.norm(o['xy'] - np.array([gt[gid]['x'], gt[gid]['y']], float))))
            if len(ds) >= 3:
                med = float(np.median(ds))
                p90 = float(np.percentile(ds, 90))
                score = med + .22 * p90 + .6 / len(ds)
                C[i, j] = score
                detail[(i, j)] = med, p90, len(ds), score
    ri, ci = linear_sum_assignment(C)
    mapping, rows = {}, []
    for i, j in zip(ri, ci):
        info = detail.get((int(i), int(j)))
        if info is None:
            continue
        med, p90, n, score = info
        if med > max_median:
            continue
        tr, gid = cal_tracks[int(i)], gt_ids[int(j)]
        mapping[tr.tid] = gid
        rows.append({
            'track_id': tr.tid, 'gt_id': gid,
            'calibration_median_m': med, 'calibration_p90_m': p90,
            'calibration_samples': n, 'assignment_score': score,
            'track_total_samples': len(tr.obs),
            'track_holdout_samples': sum(o['t'] > calibration_seconds for o in tr.obs),
        })
    return mapping, rows


def evaluate(tracks, mapping, frames, calibration_seconds, out):
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
            f = frames[o['fi']]
            gt = {g['id']: g for g in f['gt']}
            if gid not in gt:
                continue
            g = gt[gid]
            err = float(np.linalg.norm(o['xy'] - np.array([g['x'], g['y']], float)))
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
    pd.DataFrame(rows).to_csv(out / 'matched_observations.csv', index=False)
    metrics = summarize(rows, total_gt, total_det)
    crossing = [tr for tr in tracks if tr.start_t <= calibration_seconds < tr.end_t]
    metrics.update({
        'identity_frozen_holdout': True,
        'mapped_tracks': len(mapping),
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
                cv2.circle(img, (x, y), 11, (0, 255, 0), 3)
                cv2.putText(img, f'T{tr.tid}->GT{gid}', (x + 6, y - 7), 0, .55, (0, 255, 0), 2)
        cv2.imwrite(str(out / 'annotated_eval_frame.jpg'), img)
    return metrics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--video', required=True)
    ap.add_argument('--truth', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--sample-fps', type=float, default=6.0)
    ap.add_argument('--calibration-seconds', type=float, default=3.0)
    ap.add_argument('--model', default='yolo11n.pt')
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    from ultralytics import YOLO
    model = YOLO(args.model)
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
        persons = [d for d in detect_tiled(model, frame) if d['cls'] == 'person']
        for d in persons:
            d['feat'] = appearance_feature(frame, d['box'])
        frames.append({
            't': float(t), 'frame': frame,
            'all_persons': persons, 'gt': truth_at(truth_by, float(t)),
        })
        print(f't={t:.2f}s people={len(persons)}', flush=True)
    cap.release()

    k = 4
    cluster_appearance(frames, args.calibration_seconds, k)
    selected, tuning = choose_cluster_subset(frames, args.calibration_seconds, k)
    (out / 'cluster_tuning.json').write_text(json.dumps(tuning, indent=2), encoding='utf-8')
    print('selected_clusters=', sorted(selected), flush=True)

    coef, calhist = iterative_calibration(frames, args.calibration_seconds, selected)
    np.save(out / 'pixel_to_world_poly2.npy', coef)
    (out / 'calibration_history.json').write_text(json.dumps(calhist, indent=2), encoding='utf-8')

    raw_tracks = build_tracks_pixel(frames, selected)
    tracks = relink_tracklets(raw_tracks)
    attach_world(tracks, coef)
    mapping, maprows = map_tracks_to_truth(tracks, frames, args.calibration_seconds)
    (out / 'track_identity_mapping.json').write_text(json.dumps(maprows, indent=2), encoding='utf-8')
    print(f'raw_tracks={len(raw_tracks)} relinked_tracks={len(tracks)} mapping={maprows}', flush=True)

    metrics = evaluate(tracks, mapping, frames, args.calibration_seconds, out)
    metrics.update({
        'version': 'v5-kalman-pixel-relink',
        'video_duration_s': dur,
        'sample_fps': args.sample_fps,
        'calibration_seconds': args.calibration_seconds,
        'model': args.model,
        'selected_clusters': sorted(selected),
        'raw_tracklets': len(raw_tracks),
        'relinked_tracklets': len(tracks),
        'calibration_history': calhist,
    })
    (out / 'metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    print(json.dumps(metrics, indent=2), flush=True)


if __name__ == '__main__':
    main()
