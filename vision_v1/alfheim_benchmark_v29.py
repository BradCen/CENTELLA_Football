from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

import alfheim_benchmark_v19 as v19
import alfheim_benchmark_v26 as v26

NATIVE_OFFSET_S = v26.NATIVE_OFFSET_S


def _cosdist(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    na = np.linalg.norm(a); nb = np.linalg.norm(b)
    if na < 1e-8 or nb < 1e-8:
        return 1.0
    return float(1.0 - np.dot(a, b) / (na * nb))


def exclusive_detector_correct(states, dets, gray, model, bias, t):
    """V19 detector correction plus world-space identity ownership.

    Each detection is first compared against the current optical-flow world
    position of every active identity. A candidate that is materially closer
    to another active identity is rejected unless its fixed calibration
    appearance is substantially stronger. This prevents Hungarian assignment
    from legally swapping two players at a crossing. Holdout truth is never
    consulted.
    """
    gids = [g for g, s in states.items() if s.get('bbox') is not None and s.get('fail_frames', 0) <= 12]
    if not gids or not dets:
        return 0

    flow_world = {}
    for gid in gids:
        b = np.asarray(states[gid]['bbox'], float)
        flow_world[gid] = model.project(np.asarray([v19.foot_of(b)], float))[0] + bias

    det_world = [model.project(np.asarray([d['foot']], float))[0] + bias for d in dets]
    # Ownership matrix: how strongly each detection belongs to each flow track
    # in world space. It is a separate guard, not a replacement for appearance.
    world_dist = np.zeros((len(gids), len(dets)), float)
    for i, gid in enumerate(gids):
        for j, dw in enumerate(det_world):
            world_dist[i, j] = float(np.linalg.norm(dw - flow_world[gid]))

    C = np.full_like(world_dist, 1e6)
    margins = np.zeros(len(gids), float)
    for ii, gid in enumerate(gids):
        s = states[gid]
        b = np.asarray(s['bbox'], float)
        h = max(12.0, b[3] - b[1])
        center = np.asarray([(b[0] + b[2]) * 0.5, (b[1] + b[3]) * 0.5])
        proto = np.median(np.asarray(s.get('cal_feats', []), float), axis=0) if s.get('cal_feats') else None
        vals = []
        for j, d in enumerate(dets):
            db = np.asarray(d['box'], float)
            dc = np.asarray([(db[0] + db[2]) * 0.5, (db[1] + db[3]) * 0.5])
            dn = float(np.linalg.norm(dc - center) / h)
            iou = v19.box_iou(b, db)
            app = _cosdist(proto, d['feat']) if proto is not None else 0.0
            gap = world_dist[ii, j]
            others = [world_dist[k, j] for k in range(len(gids)) if k != ii]
            other_gap = min(others) if others else 99.0

            # Identity ownership: do not steal another track's detection merely
            # because Hungarian cost is slightly lower. At near-ties, appearance
            # can override ownership when it is clearly stronger.
            owner_margin = gap - other_gap
            if owner_margin > 1.15 and not (app < 0.25 and dn < 0.30):
                continue
            if dn > 1.35 and iou < 0.015:
                continue
            if app > 0.50 and dn > 0.36:
                continue
            if gap > 4.0 and dn > 0.45:
                continue
            cost = 1.28 * dn + 0.50 * (1.0 - iou) + 0.68 * max(0.0, app) + 0.13 * gap
            # Add a soft collision penalty even when the ownership gate passes.
            cost += 0.55 * max(0.0, owner_margin)
            C[ii, j] = cost
            vals.append(cost)
        if len(vals) >= 2:
            q = np.sort(np.asarray(vals, float)); margins[ii] = float(q[1] - q[0])
        else:
            margins[ii] = 99.0

    ri, ci = linear_sum_assignment(C)
    corrections = 0
    for ii, j in zip(ri, ci):
        if C[ii, j] >= 1e5 or C[ii, j] > 2.75:
            continue
        gid = gids[ii]
        s = states[gid]
        # Preserve an already healthy optical identity when the best detector
        # candidate is ambiguous and does not have strong appearance support.
        if margins[ii] < 0.10 and s.get('fail_frames', 0) == 0:
            continue
        d = dets[j]
        proto = np.median(np.asarray(s.get('cal_feats', []), float), axis=0) if s.get('cal_feats') else None
        app = _cosdist(proto, d['feat']) if proto is not None else 0.0
        gap = world_dist[ii, j]
        other_gap = min((world_dist[k, j] for k in range(len(gids)) if k != ii), default=99.0)
        if gap - other_gap > 1.45 and app > 0.28:
            continue
        old = np.asarray(s['bbox'], float)
        new = np.asarray(d['box'], float)
        blend = 0.78 if s.get('fail_frames', 0) > 0 else 0.62
        dd = dict(d); dd['box'] = blend * new + (1.0 - blend) * old
        v19.reset_state(s, gray, dd, t, calibration=False)
        corrections += 1
    return corrections


def main():
    v19.detector_correct = exclusive_detector_correct
    v19.truth_at = lambda by, t: v19.__dict__['truth_at_original'](by, float(t) + NATIVE_OFFSET_S) if 'truth_at_original' in v19.__dict__ else by
    # Keep the original truth function object without modifying calibration logic.
    if 'truth_at_original' not in v19.__dict__:
        import alfheim_benchmark as base
        v19.truth_at_original = base.truth_at
        v19.truth_at = lambda by, t: v19.truth_at_original(by, float(t) + NATIVE_OFFSET_S)
    v19.CAL_SPLIT = 3.0
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
            m['version'] = 'v29-world-space-identity-exclusivity'
            m['identity_correction'] = {
                'policy': 'world-space detection ownership + appearance-gated Hungarian reassociation',
                'holdout_ground_truth_used_for_inference': False,
                'ownership_margin_m': 1.15,
            }
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
