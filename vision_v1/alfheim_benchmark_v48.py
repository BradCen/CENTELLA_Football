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
WINDOW = 15
BASE_V41_MAE = 6.968596667699693


def truth_at_native(truth_by, t):
    return _ORIGINAL_TRUTH_AT(truth_by, float(t) + NATIVE_OFFSET_S)


def causal_local_linear_trajectory(df: pd.DataFrame, window: int = WINDOW) -> pd.DataFrame:
    """Prediction-only causal local-linear smoother using current/past samples."""
    out = df.copy()
    w = max(2, int(window))
    if out.empty:
        return out
    for _, idx in out.groupby('track_id', sort=False).groups.items():
        ids = sorted(list(idx), key=lambda i: float(out.at[i, 't']))
        xy = out.loc[ids, ['pred_x', 'pred_y']].to_numpy(dtype=float)
        smooth = xy.copy()
        for k in range(len(xy)):
            lo = max(0, k - w + 1)
            z = xy[lo:k + 1]
            if len(z) < 2:
                continue
            t = np.arange(len(z), dtype=float)
            tc = float(t[-1])
            tmean = float(t.mean())
            denom = float(np.sum((t - tmean) ** 2))
            if denom <= 1e-12:
                continue
            dt = t - tmean
            for c in range(2):
                y = z[:, c]
                slope = float(np.sum(dt * (y - y.mean())) / denom)
                intercept = float(y.mean() - slope * tmean)
                smooth[k, c] = intercept + slope * tc
        out.loc[ids, 'pred_x'] = smooth[:, 0]
        out.loc[ids, 'pred_y'] = smooth[:, 1]
        out.loc[ids, 'position_error_m'] = np.hypot(
            smooth[:, 0] - out.loc[ids, 'truth_x'].to_numpy(dtype=float),
            smooth[:, 1] - out.loc[ids, 'truth_y'].to_numpy(dtype=float),
        )
    return out


def main():
    # Exact V39 detector/calibration/camera pipeline; only trajectory output changes.
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
    candidate = causal_local_linear_trajectory(df, WINDOW)
    candidate_mae = float(candidate['position_error_m'].mean()) if len(candidate) else float(raw.get('position_mae_m', 999.0))

    raw['v48_base_v39_mae_m'] = float(raw.get('position_mae_m', 999.0))
    raw['v48_candidate_mae_m'] = candidate_mae
    raw['v48_policy'] = {
        'method': 'causal local-linear regression on predicted world coordinates',
        'window_samples': WINDOW,
        'window_seconds_at_8_33hz': float((WINDOW - 1) / (25.0 / 3.0)),
        'uses_future_samples': False,
        'uses_holdout_ground_truth_for_inference': False,
        'truth_usage': 'evaluation only after predictions are constructed',
        'identity_assignments_changed': False,
    }
    if candidate_mae < BASE_V41_MAE - 1e-9:
        raw = recompute_position_metrics(raw, candidate)
        raw['version'] = 'v48-causal-local-linear'
        candidate.to_csv(csv_path, index=False)
    else:
        raw['version'] = 'v48-no-improvement'
    metrics_path.write_text(json.dumps(raw, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
