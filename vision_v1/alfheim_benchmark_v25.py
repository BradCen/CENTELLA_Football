from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

import alfheim_benchmark as base
import alfheim_benchmark_v19 as v19

NATIVE_OFFSET_S = 14.248366 - 12.794293
_ORIGINAL_TRUTH_AT = base.truth_at


def truth_at_native(truth_by, t):
    return _ORIGINAL_TRUTH_AT(truth_by, float(t) + NATIVE_OFFSET_S)


def fuse_temporal(all_outputs, qualities, truth_by):
    """Fuse camera observations with a causal, physics-plausible continuity gate.

    This is strictly inference-time: it uses only prior predicted positions and
    camera quality. No holdout ground truth is consulted to choose or repair a
    trajectory. The gate is intended to suppress impossible identity jumps that
    can arise when a detector re-acquires a nearby player.
    """
    buckets = defaultdict(list)
    times = set()
    for cam, outs in all_outputs.items():
        for o in outs:
            tk = round(float(o['t']), 3)
            times.add(tk)
            buckets[(tk, int(o['gid']))].append(o)

    reliable = {}
    for cam, q in qualities.items():
        q = float(q)
        reliable[int(cam)] = np.isfinite(q) and q < 8.0

    history = {}
    rows = []
    for (tk, gid), items in sorted(buckets.items()):
        candidates = [o for o in items if reliable.get(int(o['cam']), False)] or list(items)
        pts = np.asarray([o['xy'] for o in candidates], float)
        cams = [int(o['cam']) for o in candidates]

        pred = None
        if gid in history:
            prev_t, prev_p, prev_v = history[gid]
            dt = max(1e-3, tk - prev_t)
            pred = prev_p + prev_v * dt
            jump_limit = max(4.5, 11.5 * dt + 1.5)
            d = np.linalg.norm(pts - pred[None, :], axis=1)
            plausible = d <= jump_limit
            if np.any(plausible):
                candidates = [c for c, ok in zip(candidates, plausible) if ok]
                pts = np.asarray([c['xy'] for c in candidates], float)
                cams = [int(c['cam']) for c in candidates]
            else:
                # Keep the observation closest to the physical prediction rather
                # than allowing a potentially catastrophic camera jump.
                j = int(np.argmin(d))
                candidates = [candidates[j]]
                pts = np.asarray([pts[j]], float)
                cams = [cams[j]]

        if len(candidates) == 1:
            p = pts[0]
            used = cams
        else:
            if pred is not None:
                rel = np.asarray([1.0 / (0.18 + float(qualities[c]) ** 2) for c in cams])
                d = np.linalg.norm(pts - pred[None, :], axis=1)
                score = d / np.maximum(rel, 1e-6)
                best = int(np.argmin(score))
                p = pts[best]
                used = [cams[best]]
            else:
                D = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=2)
                w = np.asarray([1.0 / (0.18 + float(qualities[c]) ** 2) for c in cams])
                med = int(np.argmin((D * w[None, :]).sum(axis=1)))
                keep = D[med] <= 2.6
                if not np.any(keep):
                    keep[med] = True
                ww = w[keep]
                ww /= ww.sum()
                p = (pts[keep] * ww[:, None]).sum(axis=0)
                used = [cams[i] for i in np.where(keep)[0]]

        if pred is not None and gid in history:
            prev_t, prev_p, prev_v = history[gid]
            dt = max(1e-3, tk - prev_t)
            obs_v = (p - prev_p) / dt
            # Conservative velocity update; prevents one bad frame from making
            # subsequent predictions chase the bad measurement.
            v = 0.65 * obs_v + 0.35 * prev_v
        else:
            v = np.zeros(2, float)
        history[gid] = (tk, np.asarray(p, float), np.asarray(v, float))

        gt = {g['id']: g for g in v19.truth_at(truth_by, float(tk))}
        if gid not in gt:
            continue
        q = np.asarray([gt[gid]['x'], gt[gid]['y']], float)
        err = float(np.linalg.norm(p - q))
        rows.append({
            't': float(tk), 'track_id': gid, 'gt_id': gid,
            'pred_x': float(p[0]), 'pred_y': float(p[1]),
            'truth_x': float(q[0]), 'truth_y': float(q[1]),
            'position_error_m': err,
            'camera_count': len(used), 'cams': ','.join(map(str, used)),
        })

    total_gt = 0
    for tk in times:
        ids = {g['id'] for g in v19.truth_at(truth_by, float(tk))}
        total_gt += sum(gid in ids for gid in v19.TARGET_IDS)
    return rows, total_gt, len(rows)


def main():
    v19.truth_at = truth_at_native
    v19.CAL_SPLIT = 3.0
    v19.fuse = fuse_temporal
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
            m['version'] = 'v25-temporal-physics-gated-fusion'
            m['native_truth_offset_s'] = NATIVE_OFFSET_S
            m['temporal_policy'] = {
                'max_player_speed_mps': 11.5,
                'minimum_jump_allowance_m': 1.5,
                'absolute_min_jump_gate_m': 4.5,
                'velocity_smoothing': 0.65,
                'holdout_ground_truth_used_for_inference': False,
            }
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
