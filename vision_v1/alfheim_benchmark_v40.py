from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

import alfheim_benchmark_v19 as v19
import alfheim_benchmark_v26 as v26
import alfheim_benchmark_v37 as v39

NATIVE_OFFSET_S = v26.NATIVE_OFFSET_S
_ORIGINAL_TRUTH_AT = v26._ORIGINAL_TRUTH_AT
V39_TRANSITION = v39.detector_correct_transition_persistence


def truth_at_native(truth_by, t):
    return _ORIGINAL_TRUTH_AT(truth_by, float(t) + NATIVE_OFFSET_S)


def fuse_temporal_camera_stability(all_outputs, qualities, truth_by):
    """V40: retain V39 identity behavior; stabilize camera choice with temporal continuity.

    Validation quality remains the primary signal. Temporal continuity is consulted
    only when two validated cameras have comparable calibration quality, preventing
    an isolated low-quality camera sample from replacing a stable trajectory.
    Holdout GT is evaluation-only and never enters camera selection.
    """
    buckets = defaultdict(list)
    times = set()
    for cam, outs in all_outputs.items():
        for o in outs:
            tk = round(float(o['t']), 3)
            times.add(tk)
            buckets[(tk, int(o['gid']))].append(o)

    def quality(cam: int) -> float:
        q = float(qualities.get(int(cam), 99.0))
        return q if np.isfinite(q) else 99.0

    rows = []
    prev = {}
    validated_limit = 8.0
    comparable_quality_delta = 0.75
    max_speed_mps = 12.0
    dt_eps = 1.0 / 8.0

    for (tk, gid), items in sorted(buckets.items()):
        validated = [o for o in items if quality(int(o['cam'])) < validated_limit]
        pool = validated or items
        best_q = min(quality(int(o['cam'])) for o in pool)
        comparable = [o for o in pool if quality(int(o['cam'])) <= best_q + comparable_quality_delta]

        if gid in prev and len(comparable) > 1:
            last_t, last_p = prev[gid]
            dt = max(dt_eps, float(tk - last_t))
            max_jump = max_speed_mps * dt + 1.5
            def temporal_cost(o):
                p = np.asarray(o['xy'], float)
                jump = float(np.linalg.norm(p - last_p))
                excess = max(0.0, jump - max_jump)
                # Keep calibration quality dominant while rejecting only implausible jumps.
                return (quality(int(o['cam'])), excess, jump, int(o['cam']))
            chosen = min(comparable, key=temporal_cost)
            if temporal_cost(chosen)[1] > 0.0:
                chosen = min(pool, key=lambda o: (quality(int(o['cam'])), int(o['cam'])))
        else:
            chosen = min(pool, key=lambda o: (quality(int(o['cam'])), int(o['cam'])))

        p = np.asarray(chosen['xy'], float)
        prev[gid] = (float(tk), p.copy())
        used = [int(chosen['cam'])]

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
            'camera_count': 1, 'cams': str(used[0]),
        })

    total_gt = 0
    for tk in times:
        ids = {g['id'] for g in v19.truth_at(truth_by, float(tk))}
        total_gt += sum(gid in ids for gid in v19.TARGET_IDS)
    return rows, total_gt, len(rows)


def main():
    v19.truth_at = truth_at_native
    v19.CAL_SPLIT = 3.0
    v19.detector_correct = V39_TRANSITION
    v19.fuse = fuse_temporal_camera_stability
    v19.main()

    out = None
    import sys
    for i, a in enumerate(sys.argv[:-1]):
        if a == '--out':
            out = Path(sys.argv[i + 1])
            break
    if out:
        p = out / 'metrics.json'
        if p.exists():
            m = json.loads(p.read_text(encoding='utf-8'))
            m['version'] = 'v40-temporal-camera-stability'
            m['native_truth_offset_s'] = NATIVE_OFFSET_S
            m['fusion_policy'] = {
                'selection': 'validation quality primary; temporal continuity only among comparable validated cameras',
                'comparable_quality_delta_m': 0.75,
                'max_speed_mps': 12.0,
                'holdout_ground_truth_used_for_inference': False,
                'detector_policy': 'V39 two-observation detector transition persistence',
                'objective': 'reduce isolated camera-selection jumps without overriding calibrated camera quality',
            }
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
