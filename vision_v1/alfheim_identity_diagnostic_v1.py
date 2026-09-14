from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

import alfheim_benchmark as base
import alfheim_benchmark_v19 as v19

NATIVE_OFFSET_S = 14.248366 - 12.794293
_ORIGINAL_TRUTH_AT = base.truth_at


def truth_at_with_offset(truth_by, t: float, offset_s: float) -> list[dict]:
    return _ORIGINAL_TRUTH_AT(truth_by, float(t) + float(offset_s))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--rows', required=True)
    ap.add_argument('--truth', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--truth-offset-s', type=float, default=NATIVE_OFFSET_S,
                    help='Seconds to add to row-relative time before truth lookup.')
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    truth_by = v19.load_truth(args.truth, video_start=v19.NATIVE_START)
    df = pd.read_csv(args.rows)

    required = {'t', 'track_id', 'gt_id', 'pred_x', 'pred_y', 'truth_x', 'truth_y', 'position_error_m'}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f'missing columns: {sorted(missing)}')

    assigned = []
    oracle = []
    conf = Counter()
    per_id = defaultdict(lambda: {'samples': 0, 'assigned_error_sum_m': 0.0, 'oracle_error_sum_m': 0.0, 'oracle_match_sum': 0})
    series = defaultdict(list)

    for row in df.itertuples(index=False):
        t = float(row.t)
        gid = int(row.gt_id)
        pred = np.asarray([float(row.pred_x), float(row.pred_y)], float)
        gt_rows = truth_at_with_offset(truth_by, t, args.truth_offset_s)
        if not gt_rows:
            continue
        candidates = []
        for g in gt_rows:
            gxy = np.asarray([float(g['x']), float(g['y'])], float)
            candidates.append((int(g['id']), float(np.linalg.norm(pred - gxy))))
        nearest_id, nearest_err = min(candidates, key=lambda x: x[1])
        assigned_err = float(row.position_error_m)
        assigned.append(assigned_err)
        oracle.append(nearest_err)
        conf[(gid, nearest_id)] += 1
        p = per_id[gid]
        p['samples'] += 1
        p['assigned_error_sum_m'] += assigned_err
        p['oracle_error_sum_m'] += nearest_err
        p['oracle_match_sum'] += int(nearest_id == gid)
        series[gid].append((t, nearest_id))

    switches = 0
    for entries in series.values():
        entries.sort()
        prev = None
        for _, nid in entries:
            if prev is not None and nid != prev:
                switches += 1
            prev = nid

    per_player = {}
    for gid, p in sorted(per_id.items()):
        n = max(1, p['samples'])
        per_player[str(gid)] = {
            'samples': int(p['samples']),
            'assigned_mae_m': p['assigned_error_sum_m'] / n,
            'oracle_nearest_identity_mae_m': p['oracle_error_sum_m'] / n,
            'oracle_identity_match_rate': p['oracle_match_sum'] / n,
        }

    total = len(assigned)
    assigned_mean = float(np.mean(assigned)) if assigned else None
    oracle_mean = float(np.mean(oracle)) if oracle else None
    result = {
        'version': 'v2-identity-diagnostic-offset-aware',
        'samples': total,
        'truth_offset_s': float(args.truth_offset_s),
        'assigned_identity_accuracy': float(sum(n for (a, b), n in conf.items() if a == b) / max(1, total)),
        'assigned_mae_m': assigned_mean,
        'oracle_nearest_identity_mae_m': oracle_mean,
        'error_reduction_if_relabelled_pct': float((1.0 - oracle_mean / assigned_mean) * 100.0) if assigned_mean and assigned_mean > 0 else None,
        'identity_switches': int(switches),
        'identity_confusions': {f'{a}->{b}': int(n) for (a, b), n in sorted(conf.items()) if a != b},
        'per_player': per_player,
        'holdout_truth_used_only_for_evaluation': True,
    }
    (out / 'identity_diagnostic.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
