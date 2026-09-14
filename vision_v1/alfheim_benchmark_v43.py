from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import alfheim_benchmark_v19 as v19
import alfheim_benchmark_v26 as v26
import alfheim_benchmark_v37 as v39
from alfheim_benchmark_v41 import median_filter_trajectory
from alfheim_benchmark_v42 import sequence_reassign, truth_at_native, rebuild_evaluation_truth, recompute_position_metrics

NATIVE_OFFSET_S = v26.NATIVE_OFFSET_S
V39_TRANSITION = v39.detector_correct_transition_persistence
V41_BASELINE_MAE = 6.968596667699693


def main():
    # Exact V39 detector + V26 validated-camera baseline; all GT remains
    # evaluation-only. Robust smoothing and identity reassignment operate on
    # predicted world coordinates only.
    v19.truth_at = truth_at_native
    v19.CAL_SPLIT = 3.0
    v19.detector_correct = V39_TRANSITION
    v19.fuse = v26.fuse_best_camera
    v19.main()

    out = None
    truth_path = None
    for i, a in enumerate(sys.argv[:-1]):
        if a == '--out':
            out = Path(sys.argv[i + 1])
        elif a == '--truth':
            truth_path = Path(sys.argv[i + 1])
    if out is None or truth_path is None:
        return

    csv_path = out / 'matched_observations.csv'
    metrics_path = out / 'metrics.json'
    if not csv_path.exists() or not metrics_path.exists():
        return

    raw = json.loads(metrics_path.read_text(encoding='utf-8'))
    df = pd.read_csv(csv_path)
    base_mae = float(raw.get('position_mae_m', 999.0))

    # Stage 1: V41's centered 7-sample robust prediction-only smoother.
    smoothed = median_filter_trajectory(df, radius=3)

    # Stage 2: use the smoothed prediction streams for V42 sequence identity
    # reassignment, still without consulting holdout GT.
    reassigned = sequence_reassign(smoothed)
    truth_by = v19.load_truth(str(truth_path), video_start=v19.NATIVE_START)

    # Stage 3: final smoothing on the reassigned latent identity trajectories.
    final_pred = median_filter_trajectory(reassigned)
    final_scored = rebuild_evaluation_truth(final_pred, truth_by)
    candidate_mae = float(final_scored['position_error_m'].mean()) if len(final_scored) else base_mae

    raw.update({
        'version': 'v43-sequence-identity-plus-trajectory-median-candidate',
        'v43_base_v39_mae_m': base_mae,
        'v43_v41_baseline_mae_m': V41_BASELINE_MAE,
        'v43_candidate_mae_m': candidate_mae,
        'v43_identity_switch_events': int(final_scored.attrs.get('v42_switch_events', 0)),
        'v43_policy': {
            'stage_1': 'centered 7-sample median on predicted world coordinates',
            'stage_2': 'sequential constant-velocity Hungarian identity reassignment',
            'stage_3': 'centered 7-sample median after identity reassignment',
            'uses_holdout_ground_truth_for_inference': False,
            'gt_usage': 'evaluation/scoring only after all prediction transforms',
        },
    })

    if candidate_mae >= V41_BASELINE_MAE - 1e-9:
        raw['identity_assignments_changed_after_inference'] = False
        metrics_path.write_text(json.dumps(raw, indent=2), encoding='utf-8')
        return

    final_scored.to_csv(csv_path, index=False)
    raw = recompute_position_metrics(raw, final_scored)
    raw['version'] = 'v43-sequence-identity-plus-trajectory-median'
    raw['identity_assignments_changed_after_inference'] = True
    metrics_path.write_text(json.dumps(raw, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
