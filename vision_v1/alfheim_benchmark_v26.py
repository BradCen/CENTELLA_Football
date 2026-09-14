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
VALIDATED_LIMIT_M = 8.0


def truth_at_native(truth_by, t):
    return _ORIGINAL_TRUTH_AT(truth_by, float(t) + NATIVE_OFFSET_S)


def fuse_best_camera(all_outputs, qualities, truth_by):
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
    for (tk, gid), items in sorted(buckets.items()):
        validated = [o for o in items if quality(int(o['cam'])) < VALIDATED_LIMIT_M]
        pool = validated or items
        chosen = min(pool, key=lambda o: (quality(int(o['cam'])), int(o['cam'])))
        p = np.asarray(chosen['xy'], float)
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
    v19.fuse = fuse_best_camera
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
            m['version'] = 'v26-best-validated-camera-selection'
            m['native_truth_offset_s'] = NATIVE_OFFSET_S
            m['fusion_policy'] = {
                'validated_camera_mae_limit_m': VALIDATED_LIMIT_M,
                'selection': 'lowest-validation-MAE camera per identity/time',
                'holdout_ground_truth_used_for_inference': False,
            }
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
