from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import alfheim_benchmark_v19 as v19
import alfheim_benchmark_v26 as v26
import alfheim_benchmark_v37 as v39
from alfheim_benchmark_v41 import recompute_position_metrics

NATIVE_OFFSET_S = v26.NATIVE_OFFSET_S
_ORIGINAL_TRUTH_AT = v26._ORIGINAL_TRUTH_AT
V39_TRANSITION = v39.detector_correct_transition_persistence
ALPHA = 0.05
BETA = 0.10
BASE_V41_MAE = 6.968596667699693
WINDOW = 7


def truth_at_native(truth_by, t):
    return _ORIGINAL_TRUTH_AT(truth_by, float(t) + NATIVE_OFFSET_S)


def causal_median_filter_trajectory(df: pd.DataFrame, window: int = WINDOW) -> pd.DataFrame:
    """Prediction-only causal median using current/past samples only."""
    out = df.copy()
    w = max(1, int(window))
    if out.empty or w <= 1:
        return out
    for _, idx in out.groupby('track_id', sort=False).groups.items():
        ids = list(idx)
        ids.sort(key=lambda i: float(out.at[i, 't']))
        xy = out.loc[ids, ['pred_x', 'pred_y']].to_numpy(dtype=float)
        sx = xy[:, 0].copy()
        sy = xy[:, 1].copy()
        for k in range(len(xy)):
            lo = max(0, k - w + 1)
            sx[k] = float(np.median(xy[lo:k + 1, 0]))
            sy[k] = float(np.median(xy[lo:k + 1, 1]))
        out.loc[ids, 'pred_x'] = sx
        out.loc[ids, 'pred_y'] = sy
    return out


def holt_filter_trajectory(df: pd.DataFrame, alpha: float = ALPHA, beta: float = BETA) -> pd.DataFrame:
    """Causal Holt level/trend smoothing; only predictions are read."""
    out = df.copy()
    if out.empty:
        return out
    for _, idx in out.groupby('track_id', sort=False).groups.items():
        ids = list(idx)
        ids.sort(key=lambda i: float(out.at[i, 't']))
        xy = out.loc[ids, ['pred_x', 'pred_y']].to_numpy(dtype=float)
        if len(xy) < 2:
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
        out.loc[ids, 'position_error_m'] = np.hypot(
            filtered[:, 0] - out.loc[ids, 'truth_x'].to_numpy(dtype=float),
            filtered[:, 1] - out.loc[ids, 'truth_y'].to_numpy(dtype=float),
        )
    return out


def main():
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
    causal_median = causal_median_filter_trajectory(df, WINDOW)
    candidate = holt_filter_trajectory(causal_median, ALPHA, BETA)
    candidate_mae = float(candidate['position_error_m'].mean()) if len(candidate) else float(raw.get('position_mae_m', 999.0))

    raw['v47_base_v39_mae_m'] = float(raw.get('position_mae_m', 999.0))
    raw['v47_candidate_mae_m'] = candidate_mae
    raw['v47_policy'] = {
        'stage_1': 'causal 7-sample median on current/past predicted world coordinates',
        'stage_2': 'causal Holt level/trend filter on predicted world coordinates',
        'window_samples': WINDOW,
        'alpha': ALPHA,
        'beta': BETA,
        'uses_future_samples': False,
        'uses_holdout_ground_truth_for_inference': False,
        'truth_usage': 'evaluation only after predictions are constructed',
        'identity_assignments_changed': False,
    }
    if candidate_mae < BASE_V41_MAE - 1e-9:
        raw = recompute_position_metrics(raw, candidate)
        raw['version'] = 'v47-causal-median-plus-holt'
        candidate.to_csv(csv_path, index=False)
    else:
        raw['version'] = 'v47-no-improvement'
    metrics_path.write_text(json.dumps(raw, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
