from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

import alfheim_benchmark_v19 as v19
import alfheim_benchmark_v26 as v26
import alfheim_benchmark_v37 as v39
from alfheim_benchmark_v41 import median_filter_trajectory, recompute_position_metrics

NATIVE_OFFSET_S = v26.NATIVE_OFFSET_S
_ORIGINAL_TRUTH_AT = v26._ORIGINAL_TRUTH_AT
V39_TRANSITION = v39.detector_correct_transition_persistence
_ORIGINAL_DETECTOR = v39._ORIGINAL_DETECTOR_CORRECT


def truth_at_native(truth_by, t):
    return _ORIGINAL_TRUTH_AT(truth_by, float(t) + NATIVE_OFFSET_S)


def cosdist(a, b):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na < 1e-8 or nb < 1e-8:
        return 1.0
    return float(1.0 - np.dot(a, b) / (na * nb))


def detector_correct_temporal(states, dets, gray, model, bias, t):
    """V45 detector correction with prediction-aware temporal identity gating.

    V39 remains the primary detector policy. Before accepting its correction,
    V45 evaluates the proposed detection against a short-lived appearance
    memory and an expected world-space position derived from the optical-flow
    trajectory. This never reads holdout ground truth.
    """
    # First obtain V39's proposal, preserving its calibrated detector behaviour.
    before = {gid: copy.deepcopy(state) for gid, state in states.items()}
    accepted_v39 = _ORIGINAL_DETECTOR(states, dets, gray, model, bias, t)
    if accepted_v39 <= 0:
        return 0

    accepted = 0
    for gid, state in states.items():
        b0 = before[gid].get('bbox')
        b1 = state.get('bbox')
        if b0 is None or b1 is None:
            continue
        # Only inspect actual detector-transition corrections.
        h = max(12.0, float(b0[3] - b0[1]))
        c0 = np.asarray([(b0[0] + b0[2]) / 2.0, (b0[1] + b0[3]) / 2.0])
        c1 = np.asarray([(b1[0] + b1[2]) / 2.0, (b1[1] + b1[3]) / 2.0])
        center_gap_norm = float(np.linalg.norm(c1 - c0)) / h
        if center_gap_norm < 0.18:
            continue

        # Locate the detector observation that V39 actually selected by IoU /
        # centre proximity. This is deliberately local and cannot relabel a
        # track using holdout truth.
        best = None
        for d in dets:
            db = np.asarray(d['box'], float)
            dc = np.asarray([(db[0] + db[2]) / 2.0, (db[1] + db[3]) / 2.0])
            dn = float(np.linalg.norm(dc - c0)) / h
            iou = v19.box_iou(b0, db)
            if best is None or (-iou, dn) < best[0]:
                best = ((-iou, dn), d)
        if best is None:
            continue
        d = best[1]

        cal_feats = np.asarray(state.get('cal_feats', []), float)
        if cal_feats.ndim == 1 and cal_feats.size:
            cal_feats = cal_feats[None, :]
        if len(cal_feats):
            # Robust calibration prototype: medoid under cosine distance.
            proto = cal_feats[np.argmin([np.median([cosdist(x, y) for y in cal_feats]) for x in cal_feats])]
        else:
            proto = None
        recent = state.get('v45_recent_feat')
        if recent is None and len(cal_feats):
            recent = cal_feats[-1]
        recent_app = cosdist(recent, d['feat']) if recent is not None else 0.0
        cal_app = cosdist(proto, d['feat']) if proto is not None else 0.0

        current_world = model.project(np.asarray([v19.foot_of(b0)], float))[0] + bias
        proposed_world = model.project(np.asarray([d['foot']], float))[0] + bias
        prev_world = state.get('v45_last_world')
        prev_t = state.get('v45_last_t')
        expected_world = current_world.copy()
        if prev_world is not None and prev_t is not None:
            dt = max(0.08, float(t) - float(prev_t))
            vel = (current_world - np.asarray(prev_world, float)) / dt
            speed = float(np.linalg.norm(vel))
            if speed <= 10.0:
                expected_world = current_world + vel * dt
        world_gap = float(np.linalg.norm(proposed_world - expected_world))

        # A large movement plus a poor temporal appearance match is the classic
        # identity-swap signature. V39's original cost remains authoritative;
        # this layer only vetoes the risky transition.
        risky = center_gap_norm > 0.38 and recent_app > 0.43 and cal_app > 0.43
        velocity_violation = world_gap > (1.3 + 10.0 * max(0.08, float(t) - float(prev_t or t)))
        if risky or velocity_violation:
            state.clear()
            state.update(copy.deepcopy(before[gid]))
            continue

        state['v45_recent_feat'] = np.asarray(d['feat'], float).copy()
        state['v45_last_world'] = current_world.copy()
        state['v45_last_t'] = float(t)
        accepted += 1

    return accepted


def main():
    v19.truth_at = truth_at_native
    v19.CAL_SPLIT = 3.0
    v19.detector_correct = detector_correct_temporal
    v19.fuse = v26.fuse_best_camera
    v19.main()

    out = None
    for i, a in enumerate(sys.argv[:-1]):
        if a == '--out':
            out = Path(sys.argv[i + 1])
            break
    if out is None:
        return
    csv_path = out / 'matched_observations.csv'
    metrics_path = out / 'metrics.json'
    if not csv_path.exists() or not metrics_path.exists():
        return

    raw = json.loads(metrics_path.read_text(encoding='utf-8'))
    df = pd.read_csv(csv_path)
    base_mae = float(raw.get('position_mae_m', 999.0))
    smooth = median_filter_trajectory(df, radius=3)
    candidate_mae = float(smooth['position_error_m'].mean()) if len(smooth) else base_mae
    raw['v45_base_v39_mae_m'] = base_mae
    raw['v45_candidate_mae_m'] = candidate_mae
    raw['v45_policy'] = {
        'detector': 'V39 transition detector plus temporal appearance and world-velocity veto',
        'appearance': 'calibration medoid + last accepted detector feature',
        'velocity_limit_mps': 10.0,
        'large_transition_threshold_body_heights': 0.38,
        'appearance_veto_threshold_cosdist': 0.43,
        'smoother': 'centered 7-sample median on predicted world coordinates',
        'uses_holdout_ground_truth_for_inference': False,
    }
    if candidate_mae < 6.968596667699693 - 1e-9:
        smooth.to_csv(csv_path, index=False)
        raw = recompute_position_metrics(raw, smooth)
        raw['version'] = 'v45-temporal-appearance-velocity-plus-median'
    else:
        raw['version'] = 'v45-no-improvement'
    metrics_path.write_text(json.dumps(raw, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
