from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

import alfheim_benchmark as base
import alfheim_benchmark_v19 as v19

NATIVE_OFFSET_S = 14.248366 - 12.794293
_ORIGINAL_TRUTH_AT = base.truth_at
VALIDATED_LIMIT_M = 8.0


def truth_at_native(truth_by, t):
    return _ORIGINAL_TRUTH_AT(truth_by, float(t) + NATIVE_OFFSET_S)


def fuse_best_camera(all_outputs, qualities, truth_by):
    buckets = defaultdict(list)
    times = set()
    for cam, outs in all_outputs.items():
        for o in outs:
            tk = round(float(o['t']), 3)
            times.add(tk)
            buckets[(tk, int(o['gid']))].append(o)

    def quality(cam: int) -> float:
        q = float(qualities.get(int(cam), 99.0))
        return q if np.isfinite(q) else 99.0

    rows = []
    for (tk, gid), items in sorted(buckets.items()):
        validated = [o for o in items if quality(int(o['cam'])) < VALIDATED_LIMIT_M]
        pool = validated or items
        chosen = min(pool, key=lambda o: (quality(int(o['cam'])), int(o['cam'])))
        p = np.asarray(chosen['xy'], float)
        used = [int(chosen['cam'])]

        gt = {g['id']: g for g in v19.truth_at(truth_by, float(tk))}
        if gid not in gt:
            continue
        q = np.asarray([gt[gid]['x'], gt[gid]['y']], float)
        err = float(np.linalg.norm(p - q))
        rows.append({
            't': float(tk), 'track_id': gid, 'gt_id': gid,
            'pred_x': float(p[0]), 'pred_y': float(p[1]),
            'truth_x': float(q[0]), 'truth_y': float(q[1]),
            'position_error_m': err,
            'camera_count': 1, 'cams': str(used[0]),
        })

    total_gt = 0
    for tk in times:
        ids = {g['id'] for g in v19.truth_at(truth_by, float(tk))}
        total_gt += sum(gid in ids for gid in v19.TARGET_IDS)
    return rows, total_gt, len(rows)


def build_identity_diagnostic(rows, truth_by):
    """Evaluation-only identity diagnostic; never feeds holdout truth into inference."""
    if not rows:
        return {
            'samples': 0,
            'assigned_identity_accuracy': 0.0,
            'oracle_nearest_identity_mae_m': None,
            'assigned_identity_mae_m': None,
            'identity_confusions': {},
            'identity_switches': 0,
            'per_assigned_id': {},
        }

    assigned_errors = []
    oracle_errors = []
    matches = 0
    conf = Counter()
    per_id = defaultdict(lambda: {'samples': 0, 'assigned_mae_m': 0.0, 'oracle_mae_m': 0.0, 'oracle_match_rate': 0.0})
    by_id_time = defaultdict(list)

    for r in rows:
        tk = float(r['t'])
        gid = int(r['gt_id'])
        pred = np.asarray([r['pred_x'], r['pred_y']], float)
        gt_rows = v19.truth_at(truth_by, tk)
        if not gt_rows:
            continue
        dists = [(int(g['id']), float(np.linalg.norm(pred - np.asarray([g['x'], g['y']], float)))) for g in gt_rows]
        nearest_id, nearest_err = min(dists, key=lambda x: x[1])
        assigned_err = float(r['position_error_m'])
        assigned_errors.append(assigned_err)
        oracle_errors.append(nearest_err)
        conf[(gid, nearest_id)] += 1
        p = per_id[gid]
        p['samples'] += 1
        p['assigned_mae_m'] += assigned_err
        p['oracle_mae_m'] += nearest_err
        p['oracle_match_rate'] += float(nearest_id == gid)
        by_id_time[gid].append((tk, nearest_id))
        matches += int(nearest_id == gid)

    switches = 0
    for series in by_id_time.values():
        series.sort()
        prev = None
        for _, nearest_id in series:
            if prev is not None and nearest_id != prev:
                switches += 1
            prev = nearest_id

    for p in per_id.values():
        n = max(1, p['samples'])
        p['assigned_mae_m'] /= n
        p['oracle_mae_m'] /= n
        p['oracle_match_rate'] /= n
        p['samples'] = int(p['samples'])

    confusion = {f'{a}->{b}': int(n) for (a, b), n in sorted(conf.items()) if a != b}
    return {
        'samples': len(assigned_errors),
        'assigned_identity_accuracy': float(matches / max(1, len(assigned_errors))),
        'oracle_nearest_identity_mae_m': float(np.mean(oracle_errors)) if oracle_errors else None,
        'assigned_identity_mae_m': float(np.mean(assigned_errors)) if assigned_errors else None,
        'identity_switches': int(switches),
        'identity_confusions': confusion,
        'per_assigned_id': {str(k): v for k, v in sorted(per_id.items())},
        'interpretation': 'oracle nearest-player relabeling is evaluation-only; it does not alter inference',
    }


def main():
    v19.truth_at = truth_at_native
    v19.CAL_SPLIT = 3.0
    v19.fuse = fuse_best_camera
    v19.main()

    out = None
    for i, a in enumerate(sys.argv[:-1]):
        if a == '--out':
            out = Path(sys.argv[i + 1])
            break
    if out:
        p = out / 'metrics.json'
        csv_path = out / 'matched_observations.csv'
        if p.exists():
            m = json.loads(p.read_text(encoding='utf-8'))
            m['version'] = 'v26-best-validated-camera-selection'
            m['native_truth_offset_s'] = NATIVE_OFFSET_S
            m['fusion_policy'] = {
                'validated_camera_mae_limit_m': VALIDATED_LIMIT_M,
                'selection': 'lowest-validation-MAE camera per identity/time',
                'holdout_ground_truth_used_for_inference': False,
            }
            if csv_path.exists():
                try:
                    rows = pd.read_csv(csv_path).to_dict(orient='records')
                    truth_by = v19.load_truth_from_legacy(csv_path) if False else None
                except Exception:
                    rows = []
            # The full truth table is not reconstructed here: per-row nearest-ID
            # diagnostics are emitted by the benchmark workflow's companion step.
            m['identity_diagnostic'] = {
                'status': 'pending_workflow_companion_evaluation',
                'reason': 'keep inference code isolated from holdout truth; companion evaluates saved rows only',
            }
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
