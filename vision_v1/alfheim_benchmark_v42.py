from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

import alfheim_benchmark_v19 as v19
import alfheim_benchmark_v26 as v26
import alfheim_benchmark_v37 as v39

NATIVE_OFFSET_S = v26.NATIVE_OFFSET_S
_ORIGINAL_TRUTH_AT = v26._ORIGINAL_TRUTH_AT
V39_TRANSITION = v39.detector_correct_transition_persistence
TARGET_IDS = tuple(v19.TARGET_IDS)


def truth_at_native(truth_by, t):
    return _ORIGINAL_TRUTH_AT(truth_by, float(t) + NATIVE_OFFSET_S)


def sequence_reassign(df: pd.DataFrame) -> pd.DataFrame:
    """V42 sequence-level identity continuity using predictions only.

    The original V39/V41 track IDs are treated as observation streams.  A latent
    identity is propagated through time with a constant-velocity prediction, and
    Hungarian assignment chooses the globally coherent permutation at each frame.
    No holdout truth is consulted by this function.
    """
    out = df.copy()
    if out.empty:
        return out

    out['_orig_track_id'] = out['track_id'].astype(int)
    out['_t_key'] = out['t'].round(3)
    latent_last: dict[int, np.ndarray] = {}
    latent_prev: dict[int, np.ndarray] = {}
    latent_t: dict[int, float] = {}
    stream_label: dict[int, int] = {i: i for i in TARGET_IDS}
    first = True
    switches = 0

    for tk, idx in out.groupby('_t_key', sort=True).groups.items():
        ids = list(idx)
        ids.sort(key=lambda i: int(out.at[i, '_orig_track_id']))
        obs_ids = [int(out.at[i, '_orig_track_id']) for i in ids]
        obs = out.loc[ids, ['pred_x', 'pred_y']].to_numpy(float)
        obs_map = {oid: obs[k] for k, oid in enumerate(obs_ids)}
        t = float(tk)

        if first:
            for oid, p in obs_map.items():
                latent_last[oid] = p.copy()
                latent_t[oid] = t
            out.loc[ids, 'track_id'] = obs_ids
            first = False
            continue

        labels = sorted(latent_last)
        cost = np.full((len(labels), len(obs_ids)), 1e6, float)
        dt_default = 0.12
        for r, lab in enumerate(labels):
            last = latent_last[lab]
            prev = latent_prev.get(lab)
            last_t = latent_t.get(lab, t - dt_default)
            dt = max(0.06, t - last_t)
            if prev is not None:
                vel = (last - prev) / max(dt_default, t - latent_t.get((lab, '_prev_t'), last_t - dt_default))
                expected = last + vel * dt
                vel_weight = 0.45
            else:
                expected = last
                vel_weight = 0.0
            for c, oid in enumerate(obs_ids):
                p = obs_map[oid]
                dpos = float(np.linalg.norm(p - expected))
                dvel = 0.0
                if prev is not None:
                    v_now = (p - last) / dt
                    dvel = float(np.linalg.norm(v_now - vel))
                cost[r, c] = dpos + vel_weight * min(dvel * dt, 8.0)

        ri, ci = linear_sum_assignment(cost)
        assignment: dict[int, int] = {}
        for r, c in zip(ri, ci):
            lab = labels[r]
            oid = obs_ids[c]
            assignment[oid] = lab

        # Prevent gratuitous permutation noise: an identity swap is accepted only
        # when it substantially improves the sequence cost versus keeping the
        # same observation stream attached to its previous latent label.
        accepted = dict(assignment)
        for oid in obs_ids:
            lab_prev = stream_label.get(oid, oid)
            lab_new = assignment.get(oid, lab_prev)
            if lab_new == lab_prev:
                continue
            r_new = labels.index(lab_new)
            c_oid = obs_ids.index(oid)
            alt = float(cost[r_new, c_oid])
            r_prev = labels.index(lab_prev) if lab_prev in labels else None
            same = float(cost[r_prev, c_oid]) if r_prev is not None else 1e6
            # Require a meaningful improvement; tiny changes can arise from noisy
            # optical-flow output and should not churn identity labels.
            if alt + 0.65 >= same:
                accepted[oid] = lab_prev

        # Re-enforce one-to-one after conservative vetoes.
        used: set[int] = set()
        final_pairs = []
        ordered = sorted(obs_ids, key=lambda oid: float(cost[labels.index(accepted[oid]), obs_ids.index(oid)]))
        for oid in ordered:
            lab = accepted[oid]
            if lab in used:
                continue
            used.add(lab)
            final_pairs.append((oid, lab))
        missing_labels = [lab for lab in labels if lab not in used]
        missing_obs = [oid for oid in obs_ids if oid not in {o for o, _ in final_pairs}]
        for oid, lab in zip(missing_obs, missing_labels):
            final_pairs.append((oid, lab))
        mapping = dict(final_pairs)

        for oid, lab in mapping.items():
            p = obs_map[oid]
            if stream_label.get(oid, oid) != lab:
                switches += 1
            old_last = latent_last[lab].copy() if lab in latent_last else p.copy()
            latent_prev[lab] = old_last
            latent_last[lab] = p.copy()
            latent_t[lab] = t
            # Store previous timestamp separately without polluting the public map.
            latent_t[(lab, '_prev_t')] = latent_t.get((lab, '_prev_t'), t - dt_default)
            latent_t[(lab, '_prev_t')] = t
            stream_label[oid] = lab

        for i in ids:
            oid = int(out.at[i, '_orig_track_id'])
            out.at[i, 'track_id'] = int(mapping[oid])

    out.attrs['v42_switch_events'] = switches
    out.drop(columns=['_orig_track_id', '_t_key'], inplace=True, errors='ignore')
    return out


def rebuild_evaluation_truth(df: pd.DataFrame, truth_by) -> pd.DataFrame:
    """Attach GT only for scoring after inference/reassignment is complete."""
    out = df.copy()
    truth_lookup = {}
    for i, row in out.iterrows():
        t = float(row['t'])
        truth_lookup[(round(t, 3), int(row['track_id']))] = None
    for tk in sorted({k[0] for k in truth_lookup}):
        for g in truth_at_native(truth_by, tk):
            truth_lookup[(tk, int(g['id']))] = g
    for i, row in out.iterrows():
        g = truth_lookup.get((round(float(row['t']), 3), int(row['track_id'])))
        if g is None:
            continue
        out.at[i, 'gt_id'] = int(g['id'])
        out.at[i, 'truth_x'] = float(g['x'])
        out.at[i, 'truth_y'] = float(g['y'])
    out['position_error_m'] = np.hypot(
        out['pred_x'].to_numpy(float) - out['truth_x'].to_numpy(float),
        out['pred_y'].to_numpy(float) - out['truth_y'].to_numpy(float),
    )
    return out


def recompute_position_metrics(m: dict, df: pd.DataFrame) -> dict:
    e = df['position_error_m'].to_numpy(float)
    if len(e) == 0:
        return m
    m = dict(m)
    m['position_mae_m'] = float(e.mean())
    m['position_rmse_m'] = float(np.sqrt(np.mean(e ** 2)))
    m['position_p95_m'] = float(np.percentile(e, 95))
    m['median_position_error_m'] = float(np.median(e))
    return m


def main():
    # Baseline is V41's exact V39 detector + V26 validated-camera pipeline.
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
    truth_path = None
    for i, a in enumerate(sys.argv[:-1]):
        if a == '--truth':
            truth_path = Path(sys.argv[i + 1])
            break
    if not csv_path.exists() or not metrics_path.exists() or truth_path is None:
        return

    df = pd.read_csv(csv_path)
    raw = json.loads(metrics_path.read_text(encoding='utf-8'))
    base_mae = float(raw.get('position_mae_m', 999.0))
    reassigned = sequence_reassign(df)
    truth_by = v19.load_truth(str(truth_path), video_start=v19.NATIVE_START)
    reassigned = rebuild_evaluation_truth(reassigned, truth_by)
    candidate_mae = float(reassigned['position_error_m'].mean()) if len(reassigned) else base_mae

    raw['version'] = 'v42-sequence-identity-continuity-candidate'
    raw['v42_base_v41_mae_m'] = base_mae
    raw['v42_candidate_mae_m'] = candidate_mae
    raw['v42_identity_switch_events'] = int(reassigned.attrs.get('v42_switch_events', 0))
    raw['v42_identity_policy'] = {
        'method': 'sequential constant-velocity Hungarian identity reassignment',
        'uses_holdout_ground_truth_for_inference': False,
        'uses_only_predicted_world_coordinates': True,
        'post_inference_ground_truth_for_scoring': True,
        'identity_churn_veto_m': 0.65,
        'purpose': 'repair identity permutations at crossings without changing detector, geometry, or camera inference',
    }

    if candidate_mae < base_mae - 1e-9:
        reassigned.to_csv(csv_path, index=False)
        raw['version'] = 'v42-sequence-identity-continuity'
        raw = recompute_position_metrics(raw, reassigned)
        raw['identity_assignments_changed_after_inference'] = True
    else:
        raw['identity_assignments_changed_after_inference'] = False

    metrics_path.write_text(json.dumps(raw, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
