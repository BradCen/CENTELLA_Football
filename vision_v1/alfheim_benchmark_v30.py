from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

import alfheim_benchmark as base
import alfheim_benchmark_v19 as v19
import alfheim_benchmark_v26 as v26

NATIVE_OFFSET_S = v26.NATIVE_OFFSET_S
_ORIGINAL_TRUTH_AT = base.truth_at
_CAL_MEMORY = defaultdict(dict)


def _cosdist(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    na = np.linalg.norm(a); nb = np.linalg.norm(b)
    if na < 1e-8 or nb < 1e-8:
        return 1.0
    return float(1.0 - np.dot(a, b) / (na * nb))


def temporal_confident_pairs(cam, dets, gt, seed):
    """GT-assisted calibration association with temporal identity continuity.

    GT remains available because this function is used only inside the
    calibration interval. Once holdout starts, v19 no longer calls it.
    Previous calibration detections provide a visual continuity prior so two
    nearby players cannot repeatedly exchange identity slots merely because the
    static homography is imperfect.
    """
    if not dets or not gt:
        return []
    pred = seed.project(np.asarray([d['foot'] for d in dets], float))
    G = np.asarray([[g['x'], g['y']] for g in gt], float)
    geom = np.linalg.norm(pred[:, None, :] - G[None, :, :], axis=2)
    C = np.full_like(geom, 1e6)
    memory = _CAL_MEMORY[int(cam)]

    for i, d in enumerate(dets):
        db = np.asarray(d['box'], float)
        dc = np.asarray([(db[0] + db[2]) * .5, (db[1] + db[3]) * .5])
        dh = max(12.0, db[3] - db[1])
        for j, g in enumerate(gt):
            gid = int(g['id'])
            if geom[i, j] > 4.6:
                continue
            cost = float(geom[i, j])
            if gid in memory:
                prev = memory[gid]
                pb = np.asarray(prev['box'], float)
                pc = np.asarray([(pb[0] + pb[2]) * .5, (pb[1] + pb[3]) * .5])
                pdh = max(12.0, pb[3] - pb[1])
                dn = float(np.linalg.norm(dc - pc) / max(dh, pdh))
                app = _cosdist(prev['feat'], d['feat'])
                # Geometry dominates; continuity resolves close geometric ties.
                if dn > 1.75 and geom[i, j] > 3.0:
                    continue
                if app > .62 and dn > .55:
                    continue
                cost += 1.05 * dn + .75 * app
            C[i, j] = cost

    ri, ci = linear_sum_assignment(C)
    out = []
    used_dets = set(); used_gt = set()
    for i, j in zip(ri, ci):
        if C[i, j] >= 1e5:
            continue
        # Exclude weakly separated assignments. The first term below is the
        # full temporal+geometry score, not raw homography error.
        row = np.sort(C[i])
        col = np.sort(C[:, j])
        rm = float(row[1] - row[0]) if len(row) > 1 else 99.0
        cm = float(col[1] - col[0]) if len(col) > 1 else 99.0
        raw = float(geom[i, j])
        good = (raw <= 2.9 and rm >= .10 and cm >= .10) or (raw <= 4.6 and rm >= .40 and cm >= .40)
        if not good or i in used_dets or j in used_gt:
            continue
        gid = int(gt[j]['id'])
        memory[gid] = {'box': np.asarray(dets[i]['box'], float).copy(), 'feat': np.asarray(dets[i]['feat'], float).copy()}
        out.append((int(i), int(j), raw, rm, cm))
        used_dets.add(i); used_gt.add(j)
    return out


def main():
    _CAL_MEMORY.clear()
    v19.confident_pairs = temporal_confident_pairs
    v19.truth_at = lambda by, t: _ORIGINAL_TRUTH_AT(by, float(t) + NATIVE_OFFSET_S)
    v19.CAL_SPLIT = 3.0
    # Keep the best validated-camera selection from V26. This experiment isolates
    # the calibration identity association change.
    v19.fuse = v26.fuse_best_camera
    v19.main()

    out = None
    for i, a in enumerate(sys.argv[:-1]):
        if a == '--out':
            out = Path(sys.argv[i + 1]); break
    if out:
        p = out / 'metrics.json'
        if p.exists():
            m = json.loads(p.read_text(encoding='utf-8'))
            m['version'] = 'v30-temporally-consistent-calibration-association'
            m['calibration_identity_policy'] = {
                'policy': 'GT-assisted geometry + previous calibration appearance/image continuity',
                'holdout_ground_truth_used_for_inference': False,
                'calibration_split_seconds': v19.CAL_SPLIT,
            }
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
