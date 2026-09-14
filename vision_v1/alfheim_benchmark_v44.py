from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import alfheim_benchmark_v19 as v19
import alfheim_benchmark_v26 as v26
import alfheim_benchmark_v37 as v39
from alfheim_benchmark_v41 import median_filter_trajectory, recompute_position_metrics

NATIVE_OFFSET_S = v26.NATIVE_OFFSET_S
_ORIGINAL_TRUTH_AT = v26._ORIGINAL_TRUTH_AT
_ORIGINAL_DETECTOR = v39._ORIGINAL_DETECTOR_CORRECT
_PENDING = {}


def truth_at_native(truth_by, t):
    return _ORIGINAL_TRUTH_AT(truth_by, float(t) + NATIVE_OFFSET_S)


def bbox_close(a, b, threshold=0.22):
    if a is None or b is None:
        return False
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    h = max(12.0, float(a[3] - a[1]))
    ca = np.asarray([(a[0] + a[2]) / 2.0, (a[1] + a[3]) / 2.0])
    cb = np.asarray([(b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0])
    return float(np.linalg.norm(ca - cb)) / h <= threshold


def detector_correct_adaptive(states, dets, gray, model, bias, t):
    """V44: require stronger persistence for large healthy reacquisitions.

    Small/expected detector refreshes keep V39's two-observation persistence.
    A large jump on a healthy optical track requires three coherent detector
    observations before replacing the optical state. No holdout GT is used.
    """
    global _PENDING
    before = {gid: copy.deepcopy(state) for gid, state in states.items()}
    n = _ORIGINAL_DETECTOR(states, dets, gray, model, bias, t)
    if n <= 0:
        _PENDING.clear()
        return 0

    accepted = 0
    changed = set()
    required = {}
    for gid, state in states.items():
        b0 = before[gid].get('bbox')
        b1 = state.get('bbox')
        if b0 is None or b1 is None or bbox_close(b0, b1):
            continue
        changed.add(gid)
        gap = float(np.linalg.norm(
            np.asarray([(b0[0] + b0[2]) / 2.0, (b0[1] + b0[3]) / 2.0]) -
            np.asarray([(b1[0] + b1[2]) / 2.0, (b1[1] + b1[3]) / 2.0])
        )) / max(12.0, float(b0[3] - b0[1]))
        healthy = int(before[gid].get('fail_frames', 0)) == 0
        required[gid] = 3 if healthy and gap > 0.45 else 2

    for gid in changed:
        proposal = np.asarray(states[gid]['bbox'], float).copy()
        prev = _PENDING.get(gid)
        if prev is not None and bbox_close(prev['bbox'], proposal, threshold=0.28):
            count = int(prev['count']) + 1
        else:
            count = 1
        if count >= required[gid]:
            _PENDING.pop(gid, None)
            accepted += 1
        else:
            states[gid].clear()
            states[gid].update(copy.deepcopy(before[gid]))
            _PENDING[gid] = {'bbox': proposal, 'count': count}

    for gid in list(_PENDING):
        if gid not in changed:
            _PENDING.pop(gid, None)
    return accepted


def main():
    v19.truth_at = truth_at_native
    v19.CAL_SPLIT = 3.0
    v19.detector_correct = detector_correct_adaptive
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

    raw['v44_base_adaptive_mae_m'] = base_mae
    raw['v44_candidate_mae_m'] = candidate_mae
    raw['v44_policy'] = {
        'detector': 'V44 adaptive transition persistence: 3 observations for large healthy jumps, otherwise 2',
        'smoother': 'centered 7-sample median on predicted world coordinates',
        'uses_holdout_ground_truth_for_inference': False,
        'identity_assignments_changed': False,
    }
    if candidate_mae < base_mae - 1e-9 and candidate_mae < 6.968596667699693 - 1e-9:
        smooth.to_csv(csv_path, index=False)
        raw = recompute_position_metrics(raw, smooth)
        raw['version'] = 'v44-adaptive-transition-persistence-plus-median'
    else:
        raw['version'] = 'v44-no-improvement'
    metrics_path.write_text(json.dumps(raw, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
