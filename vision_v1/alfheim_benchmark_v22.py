from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

import alfheim_benchmark as base
import alfheim_benchmark_v19 as v19

# Reuse the validated native-camera time alignment from V21.1.
NATIVE_OFFSET_S = 14.248366 - 12.794293
_ORIGINAL_TRUTH_AT = base.truth_at


def truth_at_native(truth_by, t):
    return _ORIGINAL_TRUTH_AT(truth_by, float(t) + NATIVE_OFFSET_S)


def conservative_detector_correct(states, dets, gray, model, bias, t):
    """Measurement update that cannot easily teleport an optical identity.

    V19 allowed a holdout detector correction with a 4 m projected-world gate and
    a relatively strong bbox blend. V22 keeps the detector as a recovery aid but
    requires tighter spatial/appearance agreement and uses weaker correction when
    the optical track is healthy.
    """
    gids = [g for g, s in states.items()
            if s.get('bbox') is not None and s.get('fail_frames', 0) <= 12]
    if not gids or not dets:
        return 0

    C = np.full((len(gids), len(dets)), 1e6, float)
    margins = np.zeros(len(gids), float)
    for ii, gid in enumerate(gids):
        s = states[gid]
        b = np.asarray(s['bbox'], float)
        h = max(12.0, b[3] - b[1])
        c0 = np.asarray([(b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0])
        proto = np.median(np.asarray(s['cal_feats'], float), axis=0) if s.get('cal_feats') else None
        vals = []
        flow_world = model.project(np.asarray([v19.foot_of(b)], float))[0] + bias

        for j, d in enumerate(dets):
            db = np.asarray(d['box'], float)
            c1 = np.asarray([(db[0] + db[2]) / 2.0, (db[1] + db[3]) / 2.0])
            dn = float(np.linalg.norm(c1 - c0) / h)
            iou = v19.box_iou(b, db)
            app = v19.cosdist(proto, d['feat']) if proto is not None else 0.0
            dw = model.project(np.asarray([d['foot']], float))[0] + bias
            world_gap = float(np.linalg.norm(dw - flow_world))

            # Hard gates: a healthy track must not be reassigned merely because a
            # nearby detector box is cheaper in the global Hungarian assignment.
            if dn > 1.05 and iou < 0.02:
                continue
            if app > 0.42 and dn > 0.30:
                continue
            if world_gap > 2.35 and dn > 0.35:
                continue

            cost = 1.55 * dn + 0.65 * (1.0 - iou) + 0.75 * max(0.0, app) + 0.16 * world_gap
            C[ii, j] = cost
            vals.append(cost)

        if len(vals) >= 2:
            ordered = np.sort(np.asarray(vals, float))
            margins[ii] = float(ordered[1] - ordered[0])
        else:
            margins[ii] = 99.0

    ri, ci = linear_sum_assignment(C)
    corrections = 0
    for ii, j in zip(ri, ci):
        if C[ii, j] >= 1e5:
            continue
        gid = gids[ii]
        s = states[gid]
        if margins[ii] < 0.16 and s.get('fail_frames', 0) == 0:
            continue
        if C[ii, j] > 2.30:
            continue

        old = np.asarray(s['bbox'], float)
        new = np.asarray(dets[j]['box'], float)
        # Healthy optical tracks retain more inertia; failed tracks may recover
        # more aggressively because there is no reliable optical state to trust.
        blend = 0.55 if s.get('fail_frames', 0) > 0 else 0.35
        dd = dict(dets[j])
        dd['box'] = blend * new + (1.0 - blend) * old
        v19.reset_state(s, gray, dd, t, calibration=False)
        corrections += 1
    return corrections


def main():
    v19.truth_at = truth_at_native
    v19.CAL_SPLIT = 3.0
    v19.detector_correct = conservative_detector_correct
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
            m['version'] = 'v22-conservative-detector-correction'
            m['native_truth_offset_s'] = NATIVE_OFFSET_S
            m['tracking_method'] = ('per-player Lucas-Kanade optical flow with conservative '
                                    'geometry+appearance-gated detector measurement updates')
            m['detector_correction_policy'] = {
                'healthy_blend': 0.35,
                'recovery_blend': 0.55,
                'max_projected_world_gap_m': 2.35,
                'max_assignment_cost': 2.30,
                'minimum_crossing_margin': 0.16,
            }
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
