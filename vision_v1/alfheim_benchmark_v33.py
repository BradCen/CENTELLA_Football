from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

import alfheim_benchmark_v19 as v19
import alfheim_benchmark_v26 as v26
import alfheim_benchmark_v31 as v31

NATIVE_OFFSET_S = v26.NATIVE_OFFSET_S
_ORIGINAL_TRUTH_AT = v19.truth_at
_PLAYER_QUALITY = v31._PLAYER_QUALITY
VALIDATED_LIMIT_M = v31.VALIDATED_LIMIT_M


def truth_at_native(truth_by, t):
    return _ORIGINAL_TRUTH_AT(truth_by, float(t) + NATIVE_OFFSET_S)


def choose_geometry_with_player_quality(cam, records, calibration_seconds=4.0):
    return v31.choose_geometry_with_player_quality(cam, records, calibration_seconds)


def _reassociate_camera_outputs(outputs: list[dict]) -> list[dict]:
    by_t = defaultdict(list)
    for o in outputs:
        by_t[round(float(o['t']), 3)].append(dict(o))
    times = sorted(by_t)
    if not times:
        return []

    active: dict[int, dict] = {}
    result: list[dict] = []
    first = by_t[times[0]]
    for o in first:
        gid = int(o['gid'])
        p = np.asarray(o['xy'], float)
        active[gid] = {'pos': p.copy(), 't': float(o['t']), 'velocity': np.zeros(2), 'source_gid': gid}
        oo = dict(o)
        oo['gid'] = gid
        oo['source_gid'] = gid
        oo['identity_stitched'] = False
        result.append(oo)

    for tk in times[1:]:
        obs = by_t[tk]
        if not obs:
            continue
        gids = sorted(active)
        C = np.full((len(gids), len(obs)), 50.0, float)
        for i, gid in enumerate(gids):
            s = active[gid]
            dt = max(1e-3, float(tk) - float(s['t']))
            pred = np.asarray(s['pos']) + np.clip(dt, 0.0, 0.75) * np.asarray(s['velocity'])
            for j, o in enumerate(obs):
                p = np.asarray(o['xy'], float)
                d1 = float(np.linalg.norm(p - pred))
                d0 = float(np.linalg.norm(p - np.asarray(s['pos'])))
                gate = 8.5 + 2.0 * min(float(np.linalg.norm(s['velocity'])), 4.0) * dt
                if min(d1, d0) <= gate:
                    C[i, j] = 0.72 * min(d1, 12.0) + 0.18 * min(d0, 12.0)
                    if int(o['gid']) == int(s.get('source_gid', gid)):
                        C[i, j] -= 0.20
        ri, ci = linear_sum_assignment(C)
        for i, j in zip(ri, ci):
            if C[i, j] >= 45.0:
                continue
            gid = gids[i]
            o = obs[j]
            p = np.asarray(o['xy'], float)
            s = active[gid]
            dt = max(1e-3, float(tk) - float(s['t']))
            raw_v = (p - np.asarray(s['pos'], float)) / dt
            s['velocity'] = 0.35 * raw_v + 0.65 * np.asarray(s['velocity'], float)
            s['pos'] = p.copy()
            s['t'] = float(tk)
            s['source_gid'] = int(o['gid'])
            oo = dict(o)
            oo['gid'] = int(gid)
            oo['source_gid'] = int(o['gid'])
            oo['identity_stitched'] = int(gid) != int(o['gid'])
            result.append(oo)

    result.sort(key=lambda x: (float(x['t']), int(x['gid']), int(x.get('cam', 0))))
    return result


def fuse_per_player(all_outputs, qualities, truth_by):
    stitched = {int(cam): _reassociate_camera_outputs(outs) for cam, outs in all_outputs.items()}
    return v31.fuse_per_player(stitched, qualities, truth_by)


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
            m['version'] = 'v33-world-space-tracklet-stitching'
            m['fusion_policy'] = {
                'selection': 'lowest per-player validation MAE, with camera fallback',
                'validated_camera_mae_limit_m': VALIDATED_LIMIT_M,
                'holdout_ground_truth_used_for_inference': False,
                'identity_policy': 'GT-free one-to-one world-space tracklet stitching with constant-velocity prediction',
                'identity_stitching': True,
            }
            m['per_player_camera_validation_mae_m'] = {
                str(cam): {str(g): q for g, q in sorted(vals.items())}
                for cam, vals in sorted(_PLAYER_QUALITY.items())
            }
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
