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

# Force-run after native downloader correction: this commit intentionally
# retriggers the OOS workflow with the canonical 0059-0061 URLs.
SEGMENT_VIDEO_START_S = 23.251115 - 12.794293
V39_TRANSITION = v39.detector_correct_transition_persistence
ALPHA = 0.05
BETA = 0.10
WINDOW = 7
BASE_V41_MAE = 6.968596667699693


def truth_at_segment(truth_by, t):
    return v26._ORIGINAL_TRUTH_AT(truth_by, float(t) + SEGMENT_VIDEO_START_S)


def causal_median_filter_trajectory(df: pd.DataFrame, window: int = WINDOW) -> pd.DataFrame:
    out = df.copy()
    w = max(1, int(window))
    if out.empty or w <= 1:
        return out
    for _, idx in out.groupby('track_id', sort=False).groups.items():
        ids = sorted(list(idx), key=lambda i: float(out.at[i, 't']))
        xy = out.loc[ids, ['pred_x', 'pred_y']].to_numpy(dtype=float)
        sx, sy = xy[:, 0].copy(), xy[:, 1].copy()
        for k in range(len(xy)):
            lo = max(0, k - w + 1)
            sx[k] = float(np.median(xy[lo:k + 1, 0]))
            sy[k] = float(np.median(xy[lo:k + 1, 1]))
        out.loc[ids, 'pred_x'] = sx
        out.loc[ids, 'pred_y'] = sy
    return out


def holt_filter_trajectory(df: pd.DataFrame, alpha: float = ALPHA, beta: float = BETA) -> pd.DataFrame:
    out = df.copy()
    if out.empty:
        return out
    for _, idx in out.groupby('track_id', sort=False).groups.items():
        ids = sorted(list(idx), key=lambda i: float(out.at[i, 't']))
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
    v19.truth_at = truth_at_segment
    v19.CAL_SPLIT = 3.0
    v19.detector_correct = V39_TRANSITION
    v19.fuse = v26.fuse_best_camera
    v19.main()

    out = None
    for i, a in enumerate(sys.argv[:-1]):
        if a == '--out':
            out = Path(sys.argv[i + 1]); break
    if out is None:
        return
    csv_path = out / 'matched_observations.csv'
    metrics_path = out / 'metrics.json'
    if not csv_path.exists() or not metrics_path.exists():
        return

    raw = json.loads(metrics_path.read_text(encoding='utf-8'))
    df = pd.read_csv(csv_path)
    candidate = holt_filter_trajectory(causal_median_filter_trajectory(df, WINDOW), ALPHA, BETA)
    candidate_mae = float(candidate['position_error_m'].mean()) if len(candidate) else 999.0
    raw['v49_oos_candidate_mae_m'] = candidate_mae
    raw['v49_oos_segment'] = '0059-0061'
    raw['v49_oos_segment_start_s_from_video_start'] = SEGMENT_VIDEO_START_S
    raw['v49_policy'] = {
        'base': 'V39 detector transition persistence + V26 validated-camera fusion',
        'stage_1': 'V47 causal 7-sample median',
        'stage_2': 'V47 causal Holt alpha=0.05 beta=0.10',
        'parameters_changed_for_oos': False,
        'uses_future_samples': False,
        'uses_holdout_ground_truth_for_inference': False,
        'truth_usage': 'evaluation only after predictions are constructed',
    }
    raw['version'] = 'v49-oos-0059-0061-causal-v47'
    raw = recompute_position_metrics(raw, candidate)
    candidate.to_csv(csv_path, index=False)
    metrics_path.write_text(json.dumps(raw, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
