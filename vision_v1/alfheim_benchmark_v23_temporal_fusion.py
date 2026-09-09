from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

import alfheim_benchmark_v19 as v19

CAL_SPLIT_S = 7.0


def robust_temporal_fuse(all_outputs, qualities, truth_by):
    """Fuse per-camera, already identity-locked observations with temporal gating.

    The previous V21/V22 path averaged camera observations independently at each
    timestamp. That is dangerous: a single camera can drift or jump to a nearby
    player and the average then moves the identity with it. V23 treats each
    player's holdout trajectory as a causal state: predict from its own recent
    world velocity, reject implausible jumps, then robustly combine only camera
    observations that agree with the prediction. Ground truth is used only to
    score the final result, never to select a holdout observation.
    """
    buckets = defaultdict(list)
    times = set()
    for cam, outs in all_outputs.items():
        for o in outs:
            tk = round(float(o['t']), 3)
            buckets[(tk, int(o['gid']))].append(o)
            times.add(tk)

    state = {}
    rows = []
    for tk, gid in sorted(buckets):
        items = buckets[(tk, gid)]
        qvals = np.asarray([float(qualities.get(o['cam'], 9.0)) for o in items], float)
        # Calibration-derived camera quality: lower is better. Do not allow a
        # failed camera calibration to dominate a healthy camera.
        base_w = 1.0 / (0.35 + np.square(np.maximum(qvals, 0.5)))
        pts = np.asarray([o['xy'] for o in items], float)

        st = state.get(gid)
        chosen = None
        pred = None
        if st is not None:
            dt = max(0.04, tk - st['t'])
            pred = st['xy'] + st['vel'] * min(dt, 0.75)
            # Football sprint speeds can be high, but a 7.5-8 Hz tracker should
            # not accept an instantaneous identity teleport.
            gate = min(5.0, max(2.2, 1.5 + 11.0 * dt))
            dist = np.linalg.norm(pts - pred[None, :], axis=1)
            valid = dist <= gate
            if valid.any():
                # Robust local consensus around the best temporal candidate.
                score = dist + 0.28 * qvals
                score[~valid] = 1e9
                j = int(np.argmin(score))
                local = np.linalg.norm(pts - pts[j][None, :], axis=1) <= 2.25
                local &= valid
                if local.any():
                    ww = base_w.copy()
                    ww[~local] = 0.0
                    ww /= max(1e-9, ww.sum())
                    chosen = np.sum(pts * ww[:, None], axis=0)
                else:
                    chosen = pts[j]
            else:
                # No plausible measurement: keep a short extrapolation instead
                # of switching to a distant player. This is a missing observation,
                # not a permission to break identity.
                chosen = pred.copy()
        else:
            # Cold entry: choose the best calibrated camera, with consensus if
            # multiple cameras agree. This does not use holdout ground truth.
            med = np.median(pts, axis=0)
            local = np.linalg.norm(pts - med[None, :], axis=1) <= 2.25
            if local.any():
                ww = base_w.copy(); ww[~local] = 0.0; ww /= max(1e-9, ww.sum())
                chosen = np.sum(pts * ww[:, None], axis=0)
            else:
                chosen = pts[int(np.argmin(qvals))]

        if st is not None:
            dt = max(0.04, tk - st['t'])
            raw_v = (chosen - st['xy']) / dt
            # Smooth velocity to suppress optical-flow jitter while preserving
            # genuine direction changes.
            speed = float(np.linalg.norm(raw_v))
            if speed > 11.0:
                raw_v *= 11.0 / speed
            vel = 0.65 * st['vel'] + 0.35 * raw_v
        else:
            vel = np.zeros(2, float)
        state[gid] = {'t': tk, 'xy': np.asarray(chosen, float), 'vel': vel}

        gt = {g['id']: g for g in truth_at(truth_by, float(tk))}
        if gid not in gt:
            continue
        g = gt[gid]
        q = np.asarray([g['x'], g['y']], float)
        err = float(np.linalg.norm(chosen - q))
        rows.append({
            't': float(tk), 'track_id': gid, 'gt_id': gid,
            'pred_x': float(chosen[0]), 'pred_y': float(chosen[1]),
            'truth_x': float(q[0]), 'truth_y': float(q[1]),
            'position_error_m': err,
            'camera_count': len(items),
            'cams': ','.join(map(str, [o['cam'] for o in items])),
        })

    total_gt = 0
    for tk in times:
        ids = {g['id'] for g in truth_at(truth_by, float(tk))}
        total_gt += sum(gid in ids for gid in v19.TARGET_IDS)
    return rows, total_gt, len(rows)


def main():
    v19.CAL_SPLIT = CAL_SPLIT_S
    v19.fuse = robust_temporal_fuse
    v19.main()

    out = None
    for i, a in enumerate(sys.argv[:-1]):
        if a == '--out':
            out = Path(sys.argv[i + 1])
            break
    if out:
        p = out / 'metrics.json'
        if p.exists():
            m = json.loads(p.read_text(encoding='utf-8'))
            m['version'] = 'v23-robust-temporal-fusion'
            m['calibration_seconds'] = 10.0
            m['geometry_train_split_seconds'] = CAL_SPLIT_S
            m['tracking_method'] += '; causal temporal fusion with camera-quality weighting, consensus rejection and bounded velocity'
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
