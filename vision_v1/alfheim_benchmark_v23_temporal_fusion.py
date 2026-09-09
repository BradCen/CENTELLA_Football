from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

import alfheim_benchmark_v22_conservative as v22
v19 = v22.v19

CAL_SPLIT_S = 7.0


def robust_temporal_fuse(all_outputs, qualities, truth_by):
    """Causal multi-camera fusion with jump rejection and camera weighting."""
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
        weights = 1.0 / (0.35 + np.square(np.maximum(qvals, 0.5)))
        pts = np.asarray([o['xy'] for o in items], float)
        st = state.get(gid)

        if st is not None:
            dt = max(0.04, tk - st['t'])
            pred = st['xy'] + st['vel'] * min(dt, 0.75)
            gate = min(5.0, max(2.2, 1.5 + 11.0 * dt))
            dist = np.linalg.norm(pts - pred[None, :], axis=1)
            valid = dist <= gate
            if valid.any():
                score = dist + 0.28 * qvals
                score[~valid] = 1e9
                j = int(np.argmin(score))
                local = (np.linalg.norm(pts - pts[j][None, :], axis=1) <= 2.25) & valid
                if local.any():
                    ww = weights.copy(); ww[~local] = 0.0; ww /= max(1e-9, ww.sum())
                    chosen = np.sum(pts * ww[:, None], axis=0)
                else:
                    chosen = pts[j]
            else:
                chosen = pred.copy()
        else:
            med = np.median(pts, axis=0)
            local = np.linalg.norm(pts - med[None, :], axis=1) <= 2.25
            if local.any():
                ww = weights.copy(); ww[~local] = 0.0; ww /= max(1e-9, ww.sum())
                chosen = np.sum(pts * ww[:, None], axis=0)
            else:
                chosen = pts[int(np.argmin(qvals))]

        if st is not None:
            dt = max(0.04, tk - st['t'])
            raw_v = (chosen - st['xy']) / dt
            speed = float(np.linalg.norm(raw_v))
            if speed > 11.0:
                raw_v *= 11.0 / speed
            vel = 0.65 * st['vel'] + 0.35 * raw_v
        else:
            vel = np.zeros(2, float)
        state[gid] = {'t': tk, 'xy': np.asarray(chosen, float), 'vel': vel}

        # Truth is used here only for benchmark scoring, never for selection.
        gt = {g['id']: g for g in v19.truth_at(truth_by, float(tk))}
        if gid not in gt:
            continue
        g = gt[gid]
        q = np.asarray([g['x'], g['y']], float)
        rows.append({'t': float(tk), 'track_id': gid, 'gt_id': gid,
                     'pred_x': float(chosen[0]), 'pred_y': float(chosen[1]),
                     'truth_x': float(q[0]), 'truth_y': float(q[1]),
                     'position_error_m': float(np.linalg.norm(chosen - q)),
                     'camera_count': len(items),
                     'cams': ','.join(map(str, [o['cam'] for o in items]))})

    total_gt = 0
    for tk in times:
        ids = {g['id'] for g in v19.truth_at(truth_by, float(tk))}
        total_gt += sum(gid in ids for gid in v19.TARGET_IDS)
    return rows, total_gt, len(rows)


def main():
    v22.v19.CAL_SPLIT = CAL_SPLIT_S
    v22.v19.fuse = robust_temporal_fuse
    v22.main()
    out = None
    for i, a in enumerate(sys.argv[:-1]):
        if a == '--out':
            out = Path(sys.argv[i + 1]); break
    if out:
        p = out / 'metrics.json'
        if p.exists():
            m = json.loads(p.read_text(encoding='utf-8'))
            m['version'] = 'v23-robust-temporal-fusion'
            m['calibration_seconds'] = 10.0
            m['geometry_train_split_seconds'] = CAL_SPLIT_S
            m['tracking_method'] = m.get('tracking_method','') + '; causal temporal fusion with camera-quality weighting and bounded-velocity jump rejection'
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
