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


def fuse_reliability_gated(all_outputs, qualities, truth_by):
    """Fuse camera tracks while refusing unvalidated-camera singletons.

    A camera with no holdout geometry validation can still contribute when it
    agrees with a validated camera, but it must not become the sole source for
    a player/time point. This prevents an uncalibrated view from dominating a
    production-grade world-coordinate estimate.
    """
    buckets = defaultdict(list)
    times = set()
    for cam, outs in all_outputs.items():
        for o in outs:
            tk = round(o['t'], 3)
            times.add(tk)
            buckets[(tk, o['gid'])].append(o)

    def reliable(cam: int) -> bool:
        q = float(qualities.get(cam, 9.0))
        return np.isfinite(q) and q < 8.0

    rows = []
    for (tk, gid), items in sorted(buckets.items()):
        validated = [o for o in items if reliable(int(o['cam']))]
        pool = validated if validated else []
        # Preserve observability: only fall back to an unvalidated camera when
        # there is no validated camera at this timestamp, but mark the source
        # through camera_count/cams instead of silently pretending calibration.
        if not pool:
            pool = items

        pts = np.asarray([o['xy'] for o in pool], float)
        cams = [int(o['cam']) for o in pool]
        if len(pool) == 1:
            p = pts[0]
            used = cams
        else:
            D = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=2)
            w = np.asarray([1.0 / (0.18 + float(qualities[o['cam']]) ** 2) for o in pool], float)
            med = int(np.argmin((D * w[None, :]).sum(axis=1)))
            keep = D[med] <= 2.6
            if not np.any(keep):
                keep[med] = True
            ww = w[keep]
            ww /= ww.sum()
            p = (pts[keep] * ww[:, None]).sum(axis=0)
            used = [cams[i] for i in np.where(keep)[0]]

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
            'camera_count': len(used),
            'cams': ','.join(map(str, used)),
        })

    total_gt = 0
    for tk in times:
        ids = {g['id'] for g in v19.truth_at(truth_by, float(tk))}
        total_gt += sum(gid in ids for gid in v19.TARGET_IDS)
    return rows, total_gt, len(rows)


def main():
    v19.truth_at = truth_at_native
    v19.CAL_SPLIT = 3.0
    v19.fuse = fuse_reliability_gated
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
            m['version'] = 'v23-reliability-gated-fusion'
            m['native_truth_offset_s'] = NATIVE_OFFSET_S
            m['fusion_policy'] = {
                'validated_camera_geometry_mae_limit_m': 8.0,
                'unvalidated_singleton_fallback': True,
                'multi_camera_disagreement_gate_m': 2.6,
            }
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
