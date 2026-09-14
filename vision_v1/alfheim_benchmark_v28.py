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
CONSENSUS_OUTLIER_M = 6.0


def truth_at_native(truth_by, t):
    return _ORIGINAL_TRUTH_AT(truth_by, float(t) + NATIVE_OFFSET_S)


def robust_cross_camera_fuse(all_outputs, qualities, truth_by):
    """Choose a camera observation using cross-camera world-space consensus.

    Holdout truth is not used here. Validation MAE only determines whether a
    camera has trustworthy geometry; the selected point is determined solely by
    agreement among independent camera tracks for the same identity/time.
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
    for (tk, gid), items in sorted(buckets.items()):
        validated = [o for o in items if quality(int(o['cam'])) < VALIDATED_LIMIT_M]
        pool = validated or items
        pts = [np.asarray(o['xy'], float) for o in pool]

        if len(pool) == 1:
            chosen = pool[0]
            selection = 'single_camera'
            consensus_gap = 0.0
        else:
            # Geometric medoid: choose the observation with the smallest total
            # world-space distance to the other cameras. This is robust to one
            # identity-switched/outlier camera and avoids averaging identities.
            D = np.zeros((len(pool), len(pool)), float)
            for i in range(len(pool)):
                for j in range(i + 1, len(pool)):
                    D[i, j] = D[j, i] = float(np.linalg.norm(pts[i] - pts[j]))
            totals = D.sum(axis=1)
            best_total = float(np.min(totals))
            best_idx = min(
                (i for i, v in enumerate(totals) if abs(float(v) - best_total) < 1e-9),
                key=lambda i: (quality(int(pool[i]['cam'])), int(pool[i]['cam']))
            )
            chosen = pool[best_idx]
            nearest_other = sorted(D[best_idx].tolist())[1] if len(pool) > 1 else 0.0
            consensus_gap = float(best_total / max(1, len(pool) - 1))
            # If cameras strongly disagree, validation quality breaks the tie;
            # never let consensus select an unvalidated or wildly inconsistent view.
            if consensus_gap > CONSENSUS_OUTLIER_M:
                chosen = min(pool, key=lambda o: (quality(int(o['cam'])), int(o['cam'])))
                selection = 'best_validation_on_disagreement'
            else:
                selection = 'cross_camera_medoid'

        p = np.asarray(chosen['xy'], float)
        gt = {g['id']: g for g in v19.truth_at(truth_by, float(tk))}
        if gid not in gt:
            continue
        q = np.asarray([gt[gid]['x'], gt[gid]['y']], float)
        err = float(np.linalg.norm(p - q))
        rows.append({
            't': float(tk),
            'track_id': gid,
            'gt_id': gid,
            'pred_x': float(p[0]),
            'pred_y': float(p[1]),
            'truth_x': float(q[0]),
            'truth_y': float(q[1]),
            'position_error_m': err,
            'camera_count': len(pool),
            'cams': ','.join(str(int(o['cam'])) for o in pool),
            'selected_camera': int(chosen['cam']),
            'fusion_selection': selection,
            'consensus_gap_m': consensus_gap,
        })

    total_gt = 0
    for tk in times:
        ids = {g['id'] for g in v19.truth_at(truth_by, float(tk))}
        total_gt += sum(gid in ids for gid in v19.TARGET_IDS)
    return rows, total_gt, len(rows)


def main():
    v19.truth_at = truth_at_native
    v19.CAL_SPLIT = 3.0
    v19.fuse = robust_cross_camera_fuse
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
            m['version'] = 'v28-robust-cross-camera-consensus'
            m['fusion_policy'] = {
                'validated_camera_mae_limit_m': VALIDATED_LIMIT_M,
                'consensus_outlier_m': CONSENSUS_OUTLIER_M,
                'selection': 'cross-camera world-space geometric medoid; validation-quality fallback on disagreement',
                'holdout_ground_truth_used_for_inference': False,
            }
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
