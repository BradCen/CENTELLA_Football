from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

import alfheim_benchmark_v19 as v19
import alfheim_benchmark_v26 as v26

NATIVE_OFFSET_S = v26.NATIVE_OFFSET_S
_ORIGINAL_TRUTH_AT = v19.truth_at
_ORIGINAL_CHOOSE_GEOMETRY = v19.choose_geometry
_PLAYER_QUALITY: dict[int, dict[int, float]] = defaultdict(dict)
VALIDATED_LIMIT_M = 8.0


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
    _PLAYER_QUALITY[int(cam)] = {
        gid: float(np.mean(es)) for gid, es in per.items() if es
    }
    diag['per_player_validation_mae_m'] = {str(g): q for g, q in sorted(_PLAYER_QUALITY[int(cam)].items())}
    return model, bias, diag


def fuse_per_player(all_outputs, qualities, truth_by):
    buckets = defaultdict(list)
    times = set()
    for cam, outs in all_outputs.items():
        for o in outs:
            tk = round(float(o['t']), 3)
            times.add(tk)
            buckets[(tk, int(o['gid']))].append(o)

    def cam_quality(o):
        cam = int(o['cam']); gid = int(o['gid'])
        # Prefer player-specific validation; fall back to camera validation.
        pq = float(_PLAYER_QUALITY.get(cam, {}).get(gid, 99.0))
        cq = float(qualities.get(cam, 99.0))
        if np.isfinite(pq) and pq < VALIDATED_LIMIT_M:
            return (0, pq, cq, cam)
        return (1, cq, pq, cam)

    rows = []
    for (tk, gid), items in sorted(buckets.items()):
        chosen = min(items, key=cam_quality)
        p = np.asarray(chosen['xy'], float)
        cams = sorted({int(o['cam']) for o in items})
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
            'camera_count': len(items),
            'cams': ','.join(map(str, cams)),
            'selected_camera': int(chosen['cam']),
            'player_validation_mae_m': float(_PLAYER_QUALITY.get(int(chosen['cam']), {}).get(gid, 99.0)),
        })

    total_gt = 0
    for tk in times:
        ids = {g['id'] for g in v19.truth_at(truth_by, float(tk))}
        total_gt += sum(gid in ids for gid in v19.TARGET_IDS)
    return rows, total_gt, len(rows)


def main():
    _PLAYER_QUALITY.clear()
    v19.truth_at = truth_at_native
    v19.CAL_SPLIT = 3.0
    v19.choose_geometry = choose_geometry_with_player_quality
    v19.fuse = fuse_per_player
    v19.main()

    out = None
    for i, a in enumerate(sys.argv[:-1]):
        if a == '--out':
            out = Path(sys.argv[i + 1]); break
    if out:
        p = out / 'metrics.json'
        if p.exists():
            m = json.loads(p.read_text(encoding='utf-8'))
            m['version'] = 'v31-per-player-camera-validation'
            m['fusion_policy'] = {
                'selection': 'lowest per-player validation MAE, with camera fallback',
                'validated_camera_mae_limit_m': VALIDATED_LIMIT_M,
                'holdout_ground_truth_used_for_inference': False,
            }
            m['per_player_camera_validation_mae_m'] = {
                str(cam): {str(g): q for g, q in sorted(vals.items())}
                for cam, vals in sorted(_PLAYER_QUALITY.items())
            }
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
