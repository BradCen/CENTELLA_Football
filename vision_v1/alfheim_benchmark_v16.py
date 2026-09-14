from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

import alfheim_benchmark_v9 as v9
import alfheim_benchmark_v15 as v15


BASE_CHOOSE = v15.choose_measurement


def calibration_identity_observations(cam, frames, clf, model):
    """Initialize identity pixels from geometry+GT during calibration.

    Team appearance is deliberately not a hard gate here: calibration truth is
    allowed, and repeated sub-2.2m geometric matches give us a much stronger
    identity anchor than the noisy jersey classifier.
    """
    obs = {gid: [] for gid in v15.TARGET_IDS}
    residuals = []
    for f in frames:
        if f['t'] > v15.CAL_END:
            continue
        ds = f['det']
        if not ds:
            continue
        pix = np.asarray([d['foot'] for d in ds], float)
        xy = model.project(pix)
        pairs = v9.hungarian_pairs(xy, f['gt'], 2.6)
        for i, j, c in pairs:
            if c > 2.2:
                continue
            gid = int(f['gt'][j]['id'])
            d = ds[i]
            gtxy = np.asarray([f['gt'][j]['x'], f['gt'][j]['y']], float)
            residuals.append(gtxy - xy[i])
            obs[gid].append({
                't': float(f['t']),
                'pix': np.asarray(d['foot'], float),
                'box_h': float(d['box'][3] - d['box'][1]),
                'feat': np.asarray(d['feat'], float),
                'world_error': float(c),
                'team_margin': float(clf.raw_score(d) - clf.threshold),
            })
    bias = np.median(np.asarray(residuals, float), axis=0) if residuals else np.zeros(2, float)
    return obs, np.asarray(bias, float)


def assign_camera(cam, t, frame, clf, model, bias, pix_states, world_states):
    """Use all pitch detections for an already pixel-locked ID.

    Jersey confidence becomes a soft cost. New/reacquired identities still
    require a positive team margin and unique world ownership.
    """
    ds = frame['det']
    if not ds:
        return {}
    pix = np.asarray([d['foot'] for d in ds], float)
    xy = model.project(pix) + bias[None, :]
    ids = sorted(world_states)
    C = np.full((len(ids), len(ds)), 1e6, float)
    meta = {}
    world_pred = {gid: world_states[gid].predict(t) for gid in ids}

    for j, (d, q) in enumerate(zip(ds, xy)):
        score = float(clf.raw_score(d))
        margin = score - float(clf.threshold)
        world_dists = {gid: float(np.linalg.norm(q - world_pred[gid])) for gid in ids}
        ordered = sorted(world_dists.items(), key=lambda x: x[1])
        nearest_gid = ordered[0][0]
        second_gap = ordered[1][1] - ordered[0][1] if len(ordered) > 1 else 99.0

        for i, gid in enumerate(ids):
            pst = pix_states.get(gid)
            dw = world_dists[gid]
            if pst is not None and pst.gap(t) <= 1.25:
                pp = pst.predict(t)
                dp = float(np.linalg.norm(d['foot'] - pp))
                scale = max(18.0, 0.95 * pst.box_h + 50.0 * pst.gap(t))
                pn = dp / scale
                if pn > 2.15 or dw > 4.4:
                    continue
                # A very negative team score is suspicious, but excellent
                # pixel continuity may still be the same player after a turn.
                if margin < -2.4 and pn > 0.45:
                    continue
                app = v15.cosine_distance(pst.feat, d['feat'])
                other = min((v for k, v in world_dists.items() if k != gid), default=99.0)
                if other + 0.65 < dw and pn > 0.58:
                    continue
                ownership_pen = max(0.0, dw - other - 0.10)
                team_pen = 0.62 * max(0.0, -margin)
                cost = (
                    1.55 * pn + 0.28 * dw + 0.08 * max(0.0, app)
                    + 0.62 * ownership_pen + team_pen
                    - 0.025 * max(0.0, margin)
                )
                C[i, j] = cost
                meta[(i, j)] = {
                    'gid': gid, 'xy': q, 'pix': np.asarray(d['foot'], float),
                    'box_h': float(d['box'][3] - d['box'][1]),
                    'feat': np.asarray(d['feat'], float),
                    'pixel_norm': pn, 'world_innovation': dw,
                    'cost': float(cost), 'team_margin': margin,
                    'fallback': False,
                }
            else:
                # Reacquisition stays strict: correct team + uniquely closest
                # predicted identity + tight world-space gate.
                if margin < 0.0:
                    continue
                if gid != nearest_gid or dw > 2.20 or second_gap < 0.60:
                    continue
                cost = 1.70 + 0.68 * dw - 0.035 * margin
                C[i, j] = cost
                meta[(i, j)] = {
                    'gid': gid, 'xy': q, 'pix': np.asarray(d['foot'], float),
                    'box_h': float(d['box'][3] - d['box'][1]),
                    'feat': np.asarray(d['feat'], float),
                    'pixel_norm': None, 'world_innovation': dw,
                    'cost': float(cost), 'team_margin': margin,
                    'fallback': True,
                }

    ri, ci = linear_sum_assignment(C)
    out = {}
    for i, j in zip(ri, ci):
        if C[i, j] >= 1e5 or (i, j) not in meta:
            continue
        m = dict(meta[(i, j)])
        m['cam'] = cam
        out[m['gid']] = m
    return out


def choose_measurement(gid, proposals, world_states, camera_quality, t):
    normal = BASE_CHOOSE(gid, proposals, world_states, camera_quality, t)
    if normal is not None:
        return normal

    # Recovery path: trust a very strong pixel lock through a moderate change
    # of direction. It still cannot be a fallback/reacquisition observation.
    locked = [
        p for p in proposals
        if not p['fallback'] and p['pixel_norm'] is not None
        and p['pixel_norm'] <= 0.62 and p['world_innovation'] <= 2.85
    ]
    if not locked:
        return None
    locked.sort(key=lambda p: (p['pixel_norm'], p['cost']))
    p = locked[0]
    z = np.asarray(p['xy'], float)
    pred = world_states[gid].predict(t)
    innovation = float(np.linalg.norm(z - pred))
    other = min(
        (float(np.linalg.norm(z - s.predict(t))) for k, s in world_states.items() if k != gid),
        default=99.0,
    )
    if other + 0.80 < innovation and p['pixel_norm'] > 0.28:
        return None
    return {
        'xy': z, 'confirmed': False, 'innovation': innovation,
        'used': [p], 'pixel_override': True,
    }


def main():
    v15.calibration_identity_observations = calibration_identity_observations
    v15.assign_camera = assign_camera
    v15.choose_measurement = choose_measurement
    v15.main()

    # V15's main owns argument parsing/output; relabel the artifact afterwards.
    out = None
    for i, arg in enumerate(sys.argv[:-1]):
        if arg == '--out':
            out = Path(sys.argv[i + 1])
            break
    if out is not None:
        p = out / 'metrics.json'
        if p.exists():
            m = json.loads(p.read_text(encoding='utf-8'))
            m['version'] = 'v16-soft-team-pixel-lock'
            m['tracking_method'] = (
                'calibration GT initializes pixel identities; locked IDs use all pitch detections '
                'with soft team penalty; reacquisition remains team+world gated'
            )
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
