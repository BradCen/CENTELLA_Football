from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

import alfheim_benchmark_v19 as v19
import alfheim_benchmark_v31 as v31

NATIVE_OFFSET_S = v31.NATIVE_OFFSET_S
_ORIGINAL_TRUTH_AT = v31._ORIGINAL_TRUTH_AT
_ORIGINAL_CHOOSE_GEOMETRY = v31._ORIGINAL_CHOOSE_GEOMETRY
_PLAYER_QUALITY = v31._PLAYER_QUALITY
VALIDATED_LIMIT_M = v31.VALIDATED_LIMIT_M
SHRINKAGE_K = 20.0
_PLAYER_COUNTS: dict[int, dict[int, int]] = defaultdict(dict)


def truth_at_native(truth_by, t):
    return _ORIGINAL_TRUTH_AT(truth_by, float(t) + NATIVE_OFFSET_S)


def choose_geometry_with_player_quality(cam, records, calibration_seconds=4.0):
    model, bias, diag = _ORIGINAL_CHOOSE_GEOMETRY(cam, records, calibration_seconds)
    per = defaultdict(list)
    for r in records:
        if not (3.0 < float(r['t']) <= calibration_seconds):
            continue
        gid = int(r['gid'])
        pred = model.project(np.asarray([r['pix']], float))[0]
        e = float(np.linalg.norm(pred - np.asarray(r['world'], float)))
        per[gid].append(e)
    _PLAYER_QUALITY[int(cam)] = {gid: float(np.mean(es)) for gid, es in per.items() if es}
    _PLAYER_COUNTS[int(cam)] = {gid: int(len(es)) for gid, es in per.items() if es}
    diag['per_player_validation_mae_m'] = {str(g): q for g, q in sorted(_PLAYER_QUALITY[int(cam)].items())}
    diag['per_player_validation_n'] = {str(g): n for g, n in sorted(_PLAYER_COUNTS[int(cam)].items())}
    return model, bias, diag


def _shrunk_quality(cam: int, gid: int, camera_quality: dict[int, float]) -> tuple[float, int, float]:
    pq = float(_PLAYER_QUALITY.get(cam, {}).get(gid, np.nan))
    n = int(_PLAYER_COUNTS.get(cam, {}).get(gid, 0))
    cq = float(camera_quality.get(cam, 99.0))
    if not np.isfinite(pq):
        return cq, 0, cq
    # Empirical-Bayes style shrinkage: sparse per-player validation is pulled
    # toward the more stable whole-camera validation estimate. This prevents a
    # small calibration sample from overriding strong global camera evidence.
    w = n / (n + SHRINKAGE_K)
    score = w * pq + (1.0 - w) * cq
    return float(score), n, float(pq)


def fuse_shrunk_player_quality(all_outputs, qualities, truth_by):
    buckets = defaultdict(list)
    times = set()
    for cam, outs in all_outputs.items():
        for o in outs:
            tk = round(float(o['t']), 3)
            times.add(tk)
            buckets[(tk, int(o['gid']))].append(o)

    rows = []
    selection_counts = defaultdict(int)
    for (tk, gid), items in sorted(buckets.items()):
        def key(o):
            cam = int(o['cam'])
            score, n, raw_pq = _shrunk_quality(cam, gid, qualities)
            # Prefer validated cameras, then shrunk quality, then raw player MAE,
            # then higher sample count and stable camera id for deterministic ties.
            validated = np.isfinite(_PLAYER_QUALITY.get(cam, {}).get(gid, np.nan)) and raw_pq < VALIDATED_LIMIT_M
            return (0 if validated else 1, score, raw_pq, -n, cam)

        chosen = min(items, key=key)
        p = np.asarray(chosen['xy'], float)
        cams = sorted({int(o['cam']) for o in items})
        gt = {g['id']: g for g in v19.truth_at(truth_by, float(tk))}
        if gid not in gt:
            continue
        q = np.asarray([gt[gid]['x'], gt[gid]['y']], float)
        err = float(np.linalg.norm(p - q))
        cam = int(chosen['cam'])
        score, n, raw_pq = _shrunk_quality(cam, gid, qualities)
        selection_counts[f'{gid}:{cam}'] += 1
        rows.append({
            't': float(tk), 'track_id': gid, 'gt_id': gid,
            'pred_x': float(p[0]), 'pred_y': float(p[1]),
            'truth_x': float(q[0]), 'truth_y': float(q[1]),
            'position_error_m': err,
            'camera_count': len(items),
            'cams': ','.join(map(str, cams)),
            'selected_camera': cam,
            'player_validation_mae_m': raw_pq,
            'player_validation_n': n,
            'shrunk_camera_score_m': score,
        })

    total_gt = 0
    for tk in times:
        ids = {g['id'] for g in v19.truth_at(truth_by, float(tk))}
        total_gt += sum(gid in ids for gid in v19.TARGET_IDS)
    return rows, total_gt, len(rows), dict(selection_counts)


def main():
    _PLAYER_QUALITY.clear()
    _PLAYER_COUNTS.clear()
    v19.truth_at = truth_at_native
    v19.CAL_SPLIT = 3.0
    v19.choose_geometry = choose_geometry_with_player_quality

    original_fuse = v19.fuse

    def fuse_adapter(all_outputs, qualities, truth_by):
        rows, total_gt, total_det, counts = fuse_shrunk_player_quality(all_outputs, qualities, truth_by)
        fuse_adapter.selection_counts = counts
        return rows, total_gt, total_det

    fuse_adapter.selection_counts = {}
    v19.fuse = fuse_adapter
    v19.main()

    out = None
    for i, a in enumerate(sys.argv[:-1]):
        if a == '--out':
            out = Path(sys.argv[i + 1])
            break
    if out:
        p = out / 'metrics.json'
        if p.exists():
            m = json.loads(p.read_text(encoding='utf-8'))
            m['version'] = 'v35-shrunk-per-player-camera-quality'
            m['fusion_policy'] = {
                'selection': 'per-player validation quality shrunk toward whole-camera validation quality',
                'validated_camera_mae_limit_m': VALIDATED_LIMIT_M,
                'shrinkage_k_samples': SHRINKAGE_K,
                'holdout_ground_truth_used_for_inference': False,
                'reason': 'avoid sparse player calibration from overriding stronger camera-wide evidence',
            }
            m['per_player_camera_validation_mae_m'] = {
                str(cam): {str(g): q for g, q in sorted(vals.items())}
                for cam, vals in sorted(_PLAYER_QUALITY.items())
            }
            m['per_player_camera_validation_n'] = {
                str(cam): {str(g): n for g, n in sorted(vals.items())}
                for cam, vals in sorted(_PLAYER_COUNTS.items())
            }
            m['selected_camera_observations'] = dict(getattr(fuse_adapter, 'selection_counts', {}))
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
