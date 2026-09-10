from __future__ import annotations

import copy
import json
from pathlib import Path
from collections import defaultdict

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

import alfheim_benchmark_v19 as v19
import alfheim_benchmark_v26 as v26
import alfheim_benchmark_v9 as v9
import alfheim_benchmark_v10 as v10
from alfheim_benchmark import load_truth, truth_at

NATIVE_START = v19.NATIVE_START
TARGET_IDS = v19.TARGET_IDS
CAL_SPLIT = 3.0


def _cosdist(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    na = np.linalg.norm(a); nb = np.linalg.norm(b)
    if na < 1e-8 or nb < 1e-8:
        return 1.0
    return float(1.0 - np.dot(a, b) / (na * nb))


def _hard_lock_detector_correct(states, dets, gray, model, bias, t):
    """Identity-preserving detector re-association.

    This remains holdout-truth-free. The correction uses only each player's
    frozen calibration appearance prototype, current flow position, projected
    world motion and detector geometry. A two-stage assignment protects strong
    identity locks before resolving weaker candidates.
    """
    gids = [g for g, s in states.items() if s.get('bbox') is not None and s.get('fail_frames', 0) <= 12]
    if not gids or not dets:
        return 0

    rows = []
    for gid in gids:
        s = states[gid]
        b = np.asarray(s['bbox'], float)
        h = max(12.0, b[3] - b[1])
        center = np.asarray([(b[0] + b[2]) * 0.5, (b[1] + b[3]) * 0.5])
        flow_xy = model.project(np.asarray([v19.foot_of(b)], float))[0] + bias
        proto = np.median(np.asarray(s.get('cal_feats', []), float), axis=0) if s.get('cal_feats') else None
        vals = []
        for j, d in enumerate(dets):
            db = np.asarray(d['box'], float)
            dc = np.asarray([(db[0] + db[2]) * 0.5, (db[1] + db[3]) * 0.5])
            dn = float(np.linalg.norm(dc - center) / h)
            iou = v19.box_iou(b, db)
            app = _cosdist(proto, d['feat']) if proto is not None else 0.0
            det_xy = model.project(np.asarray([d['foot']], float))[0] + bias
            world_gap = float(np.linalg.norm(det_xy - flow_xy))
            if dn > 1.10 and iou < 0.01 and world_gap > 3.4:
                continue
            if app > 0.56 and dn > 0.28:
                continue
            if world_gap > 3.0 and dn > 0.32:
                continue
            # Appearance is deliberately stronger than in V19 to protect identity,
            # while motion and IoU keep corrections available when appearance is weak.
            cost = 1.20 * dn + 0.42 * (1.0 - iou) + 0.95 * app + 0.18 * world_gap
            vals.append((j, cost, app, dn, iou, world_gap))
        vals.sort(key=lambda x: x[1])
        best = vals[0] if vals else None
        second = vals[1] if len(vals) > 1 else None
        margin = (second[1] - best[1]) if best and second else 99.0
        rows.append((gid, best, margin))

    # Stage 1: only unmistakable identity locks are allowed to move the bbox.
    locked = []
    for gid, best, margin in rows:
        if best is None:
            continue
        j, cost, app, dn, iou, world_gap = best
        healthy = states[gid].get('fail_frames', 0) == 0
        hard = (margin >= 0.22 and cost <= 2.30 and app <= 0.40 and world_gap <= 2.25)
        recover = (not healthy and margin >= 0.28 and cost <= 2.45 and app <= 0.46 and world_gap <= 2.60)
        if hard or recover:
            locked.append((gid, j, cost, margin))
    locked.sort(key=lambda x: (x[2], -x[3]))
    used_gids, used_dets = set(), set()
    corrections = 0
    for gid, j, cost, margin in locked:
        if gid in used_gids or j in used_dets:
            continue
        s = states[gid]
        old = np.asarray(s['bbox'], float)
        new = np.asarray(dets[j]['box'], float)
        blend = 0.72 if s.get('fail_frames', 0) > 0 else 0.55
        dd = dict(dets[j]); dd['box'] = blend * new + (1.0 - blend) * old
        v19.reset_state(s, gray, dd, t, calibration=False)
        used_gids.add(gid); used_dets.add(j); corrections += 1

    # Stage 2: reconcile only tracks/detections not consumed by a hard lock.
    rem_gids = [gid for gid in gids if gid not in used_gids]
    rem_dets = [j for j in range(len(dets)) if j not in used_dets]
    if not rem_gids or not rem_dets:
        return corrections
    C = np.full((len(rem_gids), len(rem_dets)), 1e6, float)
    details = {}
    for ii, gid in enumerate(rem_gids):
        s = states[gid]
        b = np.asarray(s['bbox'], float)
        h = max(12.0, b[3] - b[1])
        center = np.asarray([(b[0] + b[2]) * 0.5, (b[1] + b[3]) * 0.5])
        flow_xy = model.project(np.asarray([v19.foot_of(b)], float))[0] + bias
        proto = np.median(np.asarray(s.get('cal_feats', []), float), axis=0) if s.get('cal_feats') else None
        for jj, j in enumerate(rem_dets):
            d = dets[j]; db = np.asarray(d['box'], float)
            dc = np.asarray([(db[0] + db[2]) * 0.5, (db[1] + db[3]) * 0.5])
            dn = float(np.linalg.norm(dc - center) / h)
            iou = v19.box_iou(b, db)
            app = _cosdist(proto, d['feat']) if proto is not None else 0.0
            det_xy = model.project(np.asarray([d['foot']], float))[0] + bias
            world_gap = float(np.linalg.norm(det_xy - flow_xy))
            if dn > 1.30 and iou < 0.01:
                continue
            if app > 0.62 and dn > 0.35:
                continue
            if world_gap > 4.0 and dn > 0.50:
                continue
            cost = 1.15 * dn + 0.42 * (1.0 - iou) + 0.82 * app + 0.14 * world_gap
            C[ii, jj] = cost
            details[(ii, jj)] = (app, dn, iou, world_gap)
    ri, ci = linear_sum_assignment(C)
    for ii, jj in zip(ri, ci):
        if C[ii, jj] >= 1e5 or C[ii, jj] > 2.55:
            continue
        gid = rem_gids[ii]; j = rem_dets[jj]
        app, dn, iou, world_gap = details[(ii, jj)]
        if app > 0.50 and dn > 0.26:
            continue
        s = states[gid]
        old = np.asarray(s['bbox'], float); new = np.asarray(dets[j]['box'], float)
        blend = 0.78 if s.get('fail_frames', 0) > 0 else 0.62
        dd = dict(dets[j]); dd['box'] = blend * new + (1.0 - blend) * old
        v19.reset_state(s, gray, dd, t, calibration=False)
        corrections += 1
    return corrections


def main():
    # Patch only the holdout correction policy. Calibration, geometry selection,
    # and fusion remain identical to V26 so the experiment isolates identity lock.
    v19.detector_correct = _hard_lock_detector_correct
    v19.truth_at = lambda by, t: truth_at(by, float(t) + v26.NATIVE_OFFSET_S)
    v19.CAL_SPLIT = CAL_SPLIT
    v19.fuse = v26.fuse_best_camera
    v19.main()

    out = None
    import sys
    for i, a in enumerate(sys.argv[:-1]):
        if a == '--out':
            out = Path(sys.argv[i + 1]); break
    if out:
        p = out / 'metrics.json'
        if p.exists():
            m = json.loads(p.read_text(encoding='utf-8'))
            m['version'] = 'v27-identity-lock-reassociation'
            m['identity_correction'] = {
                'policy': 'two-stage appearance+motion+geometry identity lock',
                'holdout_ground_truth_used_for_inference': False,
                'calibration_seconds': CAL_SPLIT,
            }
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
