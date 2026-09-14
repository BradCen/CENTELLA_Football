from __future__ import annotations

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
V39_TRANSITION = v39.detector_correct_transition_persistence
ALPHA = 0.05
BETA = 0.10
BASE_V41_MAE = 6.968596667699693


def truth_at_native(truth_by, t):
    return _ORIGINAL_TRUTH_AT(truth_by, float(t) + NATIVE_OFFSET_S)


def holt_filter_trajectory(df: pd.DataFrame, alpha: float = ALPHA, beta: float = BETA) -> pd.DataFrame:
    """Prediction-only level/trend smoothing applied per fixed track.

    The filter never reads truth columns while constructing predictions.  It is
    deliberately causal: each point uses only the current observation and the
    previous filtered level/trend state.
    """
    out = df.copy()
    if out.empty:
        return out

    for gid, idx in out.groupby('track_id', sort=False).groups.items():
        ids = list(idx)
        ids.sort(key=lambda i: float(out.at[i, 't']))
        xy = out.loc[ids, ['pred_x', 'pred_y']].to_numpy(dtype=float)
        n = len(xy)
        if n < 2:
            continue
        level = xy[0].copy()
        trend = xy[1] - xy[0]
        filtered = [level.copy()]
        for z in xy[1:]:
            previous_level = level.copy()
            level = alpha * z + (1.0 - alpha) * (level + trend)
            trend = beta * (level - previous_level) + (1.0 - beta) * trend
            filtered.append(level.copy())
        filtered = np.asarray(filtered, dtype=float)
        out.loc[ids, 'pred_x'] = filtered[:, 0]
        out.loc[ids, 'pred_y'] = filtered[:, 1]
        # Recompute only after prediction construction; truth is evaluation data.
        out.loc[ids, 'position_error_m'] = np.hypot(
            filtered[:, 0] - out.loc[ids, 'truth_x'].to_numpy(dtype=float),
            filtered[:, 1] - out.loc[ids, 'truth_y'].to_numpy(dtype=float),
        )
    return out


def main():
    # Reproduce exact V41 baseline first: V39 detector + V26 camera selection,
    # then V41's 7-sample median.
    v19.truth_at = truth_at_native
    v19.CAL_SPLIT = 3.0
    v19.detector_correct = V39_TRANSITION
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
    # V41 stage: robust median, prediction-only.
    median = median_filter_trajectory(df, radius=3)
    base_mae = float(median['position_error_m'].mean()) if len(median) else BASE_V41_MAE
    # V46 stage: causal level/trend filter, prediction-only.
    candidate = holt_filter_trajectory(median, ALPHA, BETA)
    candidate_mae = float(candidate['position_error_m'].mean()) if len(candidate) else base_mae

    raw['v46_base_v41_mae_m'] = base_mae
    raw['v46_candidate_mae_m'] = candidate_mae
    raw['v46_policy'] = {
        'stage_1': 'centered 7-sample median on predicted world coordinates',
        'stage_2': 'causal Holt level/trend filter on predicted world coordinates',
        'alpha': ALPHA,
        'beta': BETA,
        'uses_holdout_ground_truth_for_inference': False,
        'truth_usage': 'evaluation only after predictions are constructed',
        'identity_assignments_changed': False,
    }
    if candidate_mae < BASE_V41_MAE - 1e-9:
        candidate.to_csv(csv_path, index=False)
        raw = recompute_position_metrics(raw, candidate)
        raw['version'] = 'v46-holt-trend-plus-median'
    else:
        raw['version'] = 'v46-no-improvement'
    metrics_path.write_text(json.dumps(raw, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
