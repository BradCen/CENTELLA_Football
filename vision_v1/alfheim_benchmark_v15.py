from __future__ import annotations

import argparse
import copy
import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

import alfheim_benchmark_v9 as v9
import alfheim_benchmark_v10 as v10
import alfheim_benchmark_v11 as v11
import alfheim_benchmark_v12 as v12
from alfheim_benchmark import load_truth, truth_at

NATIVE_START = v9.NATIVE_START
TARGET_IDS = v9.TARGET_IDS
CAL_END = 4.0


def cosine_distance(a, b):
    if a is None or b is None:
        return 0.0
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    den = float(np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9
    return 1.0 - float(np.dot(a, b) / den)


def cap_vec(v, limit):
    v = np.asarray(v, float)
    n = float(np.linalg.norm(v))
    return v if n <= limit else v * (limit / max(n, 1e-9))


@dataclass
class PixelState:
    gid: int
    pix: np.ndarray
    vel: np.ndarray
    t: float
    box_h: float
    feat: np.ndarray | None = None
    accepted: int = 0

    def predict(self, t):
        return self.pix + self.vel * max(0.0, float(t) - self.t)

    def gap(self, t):
        return max(0.0, float(t) - self.t)

    def update(self, t, pix, box_h, feat):
        t = float(t)
        pix = np.asarray(pix, float)
        dt = max(0.04, t - self.t)
        inst = cap_vec((pix - self.pix) / dt, 900.0)
        self.vel = 0.72 * self.vel + 0.28 * inst
        self.pix = pix
        self.t = t
        self.box_h = 0.75 * self.box_h + 0.25 * float(box_h)
        if feat is not None:
            f = np.asarray(feat, float)
            self.feat = f if self.feat is None else 0.92 * self.feat + 0.08 * f
        self.accepted += 1


@dataclass
class WorldState:
    gid: int
    pos: np.ndarray
    vel: np.ndarray
    t: float
    accepted: int = 0

    def predict(self, t):
        return self.pos + self.vel * max(0.0, float(t) - self.t)

    def gap(self, t):
        return max(0.0, float(t) - self.t)

    def update(self, t, z, confirmed):
        t = float(t)
        z = np.asarray(z, float)
        dt = max(0.04, t - self.t)
        pred = self.predict(t)
        r = z - pred
        alpha = 0.66 if confirmed else 0.46
        beta = 0.055 if confirmed else 0.025
        self.pos = pred + alpha * r
        self.vel = cap_vec(self.vel + beta * r / dt, 10.5)
        self.t = t
        self.accepted += 1
        return self.pos.copy()


def fit_world_states(truth_by, times):
    cal = [float(t) for t in times if t <= CAL_END]
    t0 = cal[-1]
    states = {}
    diag = {}
    for gid in TARGET_IDS:
        samples = []
        for t in cal:
            if t < t0 - 0.85:
                continue
            g = {x['id']: x for x in truth_at(truth_by, t)}
            if gid in g:
                samples.append((t, g[gid]['x'], g[gid]['y']))
        g0 = {x['id']: x for x in truth_at(truth_by, t0)}
        if gid not in g0:
            continue
        p0 = np.asarray([g0[gid]['x'], g0[gid]['y']], float)
        vel = np.zeros(2, float)
        if len(samples) >= 4:
            a = np.asarray(samples, float)
            tt = a[:, 0] - t0
            X = np.c_[tt, np.ones(len(tt))]
            vx = np.linalg.lstsq(X, a[:, 1], rcond=None)[0][0]
            vy = np.linalg.lstsq(X, a[:, 2], rcond=None)[0][0]
            vel = cap_vec([vx, vy], 10.5)
        states[gid] = WorldState(gid, p0, vel, t0)
        diag[str(gid)] = {'pos': p0.tolist(), 'vel': vel.tolist(), 'fit_samples': len(samples)}
    return states, {'t0': t0, 'ids': sorted(states), 'states': diag}


def select_team_frames(cams):
    pooled, train_diag = v12.fit_pooled_classifier(cams)
    classifiers = {}
    team_diag = {}
    for cam in range(3):
        clf = copy.deepcopy(pooled)
        th, val = v12.tune_camera_threshold(cam, cams[cam], clf)
        clf.threshold = th
        clf.annotate(cams[cam])
        classifiers[cam] = clf
        team_diag[str(cam)] = val
    return classifiers, train_diag, team_diag


def fit_camera_models(cams, classifiers, team_diag):
    models = {}
    geom_diag = {}
    enabled = []
    for cam in range(3):
        val = team_diag[str(cam)]
        # Cam0 narrowly missed V12's 0.50 team-precision gate but its geometry
        # is useful. Cam2 has zero temporal geometry support and stays out.
        usable_team = (
            int(val.get('matches', 0)) >= 8
            and float(val.get('precision', 0.0)) >= 0.40
            and float(val.get('avg_per_frame', 99.0)) <= 9.5
        )
        if not usable_team:
            geom_diag[str(cam)] = {'enabled': False, 'reason': 'team_temporal_health'}
            continue
        try:
            model, hist = v12.stable_calibrate(cam, cams[cam], classifiers[cam])
            q = v10.geom_quality(cams[cam], classifiers[cam], model, 3.0, 4.0, 4.0)
        except Exception as exc:
            geom_diag[str(cam)] = {'enabled': False, 'reason': f'geometry:{exc}'}
            continue
        usable_geom = int(q.get('matched', 0)) >= 8 and float(q.get('mae_m', 99.0)) <= 2.5
        geom_diag[str(cam)] = {
            'enabled': bool(usable_geom), 'validation': q,
            'selection': hist,
        }
        if usable_geom:
            models[cam] = model
            enabled.append(cam)
    return models, enabled, geom_diag


def calibration_identity_observations(cam, frames, clf, model):
    obs = {gid: [] for gid in TARGET_IDS}
    residuals = []
    for f in frames:
        if f['t'] > CAL_END:
            continue
        ds = v12.frame_selection(f, clf, clf.threshold)
        if not ds:
            continue
        pix = np.asarray([d['foot'] for d in ds], float)
        xy = model.project(pix)
        pairs = v9.hungarian_pairs(xy, f['gt'], 3.6)
        for i, j, c in pairs:
            if c > 3.25:
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
            })
    bias = np.median(np.asarray(residuals, float), axis=0) if residuals else np.zeros(2, float)
    return obs, np.asarray(bias, float)


def make_pixel_states(obs):
    states = {}
    diag = {}
    for gid, arr in obs.items():
        arr = sorted(arr, key=lambda x: x['t'])
        if len(arr) < 2:
            continue
        last = arr[-1]
        velocities = []
        for a, b in zip(arr[-7:-1], arr[-6:]):
            dt = b['t'] - a['t']
            if 0.04 <= dt <= 0.32:
                velocities.append((b['pix'] - a['pix']) / dt)
        vel = np.median(np.asarray(velocities, float), axis=0) if velocities else np.zeros(2, float)
        vel = cap_vec(vel, 900.0)
        feat = np.median(np.asarray([x['feat'] for x in arr[-10:]], float), axis=0)
        states[gid] = PixelState(
            gid, last['pix'].copy(), vel, float(last['t']),
            float(last['box_h']), feat,
        )
        diag[str(gid)] = {
            'samples': len(arr), 'last_t': float(last['t']),
            'pix': last['pix'].tolist(), 'vel': vel.tolist(),
            'median_world_error_m': float(np.median([x['world_error'] for x in arr])),
        }
    return states, diag


def prepare_pixel_states(cams, classifiers, models, enabled):
    pixel_states = {}
    camera_bias = {}
    diag = {}
    for cam in enabled:
        obs, bias = calibration_identity_observations(cam, cams[cam], classifiers[cam], models[cam])
        st, d = make_pixel_states(obs)
        pixel_states[cam] = st
        camera_bias[cam] = bias
        diag[str(cam)] = {'ids': sorted(st), 'states': d, 'global_bias_m': bias.tolist()}
    return pixel_states, camera_bias, diag


def candidate_team_detections(frame, clf):
    return v12.frame_selection(frame, clf, clf.threshold)


def assign_camera(cam, t, frame, clf, model, bias, pix_states, world_states):
    ds = candidate_team_detections(frame, clf)
    if not ds:
        return {}
    pix = np.asarray([d['foot'] for d in ds], float)
    xy = model.project(pix) + bias[None, :]
    ids = sorted(world_states)
    C = np.full((len(ids), len(ds)), 1e6, float)
    meta = {}

    world_pred = {gid: world_states[gid].predict(t) for gid in ids}
    for j, (d, q) in enumerate(zip(ds, xy)):
        world_dists = {gid: float(np.linalg.norm(q - world_pred[gid])) for gid in ids}
        ordered = sorted(world_dists.items(), key=lambda x: x[1])
        nearest_gid = ordered[0][0]
        second_gap = ordered[1][1] - ordered[0][1] if len(ordered) > 1 else 99.0

        for i, gid in enumerate(ids):
            pst = pix_states.get(gid)
            dw = world_dists[gid]
            score = float(clf.raw_score(d))
            margin = score - float(clf.threshold)
            if pst is not None and pst.gap(t) <= 1.15:
                pp = pst.predict(t)
                dp = float(np.linalg.norm(d['foot'] - pp))
                scale = max(18.0, 0.90 * pst.box_h + 45.0 * pst.gap(t))
                pn = dp / scale
                if pn > 2.05 or dw > 4.2:
                    continue
                app = cosine_distance(pst.feat, d['feat'])
                # A detection strongly owned by another world state is not
                # allowed to steal this identity unless pixel continuity is excellent.
                other = min((v for k, v in world_dists.items() if k != gid), default=99.0)
                if other + 0.55 < dw and pn > 0.72:
                    continue
                ownership_pen = max(0.0, dw - other - 0.10)
                cost = 1.45 * pn + 0.34 * dw + 0.10 * max(0.0, app) + 0.55 * ownership_pen - 0.035 * margin
                C[i, j] = cost
                meta[(i, j)] = {
                    'gid': gid, 'xy': q, 'pix': np.asarray(d['foot'], float),
                    'box_h': float(d['box'][3] - d['box'][1]), 'feat': np.asarray(d['feat'], float),
                    'pixel_norm': pn, 'world_innovation': dw, 'cost': float(cost),
                    'team_margin': margin, 'fallback': False,
                }
            else:
                # Reacquisition is intentionally conservative. It must be the
                # unique nearest predicted identity in world space.
                if gid != nearest_gid or dw > 2.15 or second_gap < 0.55:
                    continue
                cost = 1.65 + 0.70 * dw - 0.035 * margin
                C[i, j] = cost
                meta[(i, j)] = {
                    'gid': gid, 'xy': q, 'pix': np.asarray(d['foot'], float),
                    'box_h': float(d['box'][3] - d['box'][1]), 'feat': np.asarray(d['feat'], float),
                    'pixel_norm': None, 'world_innovation': dw, 'cost': float(cost),
                    'team_margin': margin, 'fallback': True,
                }

    if not np.isfinite(C).any():
        return {}
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
    if not proposals:
        return None
    pred = world_states[gid].predict(t)
    props = sorted(proposals, key=lambda p: p['cost'] / max(0.05, camera_quality[p['cam']]))

    confirmed = False
    used = []
    if len(props) >= 2:
        best_pair = None
        for i in range(len(props)):
            for j in range(i + 1, len(props)):
                sep = float(np.linalg.norm(props[i]['xy'] - props[j]['xy']))
                if sep <= 2.0:
                    pair_cost = props[i]['cost'] + props[j]['cost'] + 0.2 * sep
                    if best_pair is None or pair_cost < best_pair[0]:
                        best_pair = (pair_cost, props[i], props[j])
        if best_pair is not None:
            _, a, b = best_pair
            used = [a, b]
            w = np.asarray([
                camera_quality[a['cam']] / max(0.25, a['cost']),
                camera_quality[b['cam']] / max(0.25, b['cost']),
            ], float)
            w /= w.sum()
            z = w[0] * a['xy'] + w[1] * b['xy']
            confirmed = True
        else:
            used = [props[0]]
            z = props[0]['xy']
    else:
        used = [props[0]]
        z = props[0]['xy']

    innovation = float(np.linalg.norm(z - pred))
    other = min(
        (float(np.linalg.norm(z - s.predict(t))) for k, s in world_states.items() if k != gid),
        default=99.0,
    )
    if other + 0.45 < innovation and not confirmed:
        return None

    if confirmed:
        if innovation > 3.0:
            return None
    else:
        p = used[0]
        pn = p['pixel_norm']
        if p['fallback']:
            if innovation > 1.25:
                return None
        elif innovation > 1.80 or pn is None or pn > 1.35:
            return None

    return {
        'xy': np.asarray(z, float), 'confirmed': confirmed,
        'innovation': innovation, 'used': used,
    }


def run_tracker(times, cams, classifiers, models, enabled, pixel_states, camera_bias, world_states, camera_quality):
    outputs = []
    audit = []
    for idx, t0 in enumerate(times):
        t = float(t0)
        if t <= CAL_END:
            continue
        proposals_by_gid = {gid: [] for gid in world_states}
        for cam in enabled:
            if idx >= len(cams[cam]):
                continue
            amap = assign_camera(
                cam, t, cams[cam][idx], classifiers[cam], models[cam],
                camera_bias[cam], pixel_states[cam], world_states,
            )
            for gid, p in amap.items():
                proposals_by_gid[gid].append(p)

        accepted_ids = set()
        for gid, st in world_states.items():
            chosen = choose_measurement(gid, proposals_by_gid[gid], world_states, camera_quality, t)
            if chosen is None:
                if st.gap(t) <= 0.45:
                    outputs.append({
                        't': t, 'gt_id': gid, 'xy': st.predict(t), 'observed': False,
                        'confirmed': False, 'cams': [], 'camera_count': 0,
                    })
                continue

            pos = st.update(t, chosen['xy'], chosen['confirmed'])
            accepted_ids.add(gid)
            used_cams = []
            for p in chosen['used']:
                cam = p['cam']
                pst = pixel_states[cam].get(gid)
                if pst is None:
                    pixel_states[cam][gid] = PixelState(
                        gid, p['pix'].copy(), np.zeros(2, float), t,
                        p['box_h'], p['feat'].copy(), 1,
                    )
                else:
                    pst.update(t, p['pix'], p['box_h'], p['feat'])
                used_cams.append(cam)
            outputs.append({
                't': t, 'gt_id': gid, 'xy': pos, 'observed': True,
                'confirmed': bool(chosen['confirmed']), 'cams': sorted(used_cams),
                'camera_count': len(used_cams),
            })
            audit.append({
                't': t, 'gid': gid, 'confirmed': bool(chosen['confirmed']),
                'innovation_m': float(chosen['innovation']), 'cams': sorted(used_cams),
                'proposal_costs': [float(p['cost']) for p in chosen['used']],
                'pixel_norms': [None if p['pixel_norm'] is None else float(p['pixel_norm']) for p in chosen['used']],
            })
    return outputs, audit


def evaluate(outputs, truth_by, times):
    rows = []
    total_gt = sum(len(truth_at(truth_by, float(t))) for t in times if t > CAL_END)
    for o in outputs:
        gt = {g['id']: g for g in truth_at(truth_by, o['t'])}
        gid = o['gt_id']
        if gid not in gt:
            continue
        g = gt[gid]
        q = np.asarray([g['x'], g['y']], float)
        err = float(np.linalg.norm(o['xy'] - q))
        rows.append({
            't': o['t'], 'track_id': gid, 'gt_id': gid,
            'pred_x': float(o['xy'][0]), 'pred_y': float(o['xy'][1]),
            'truth_x': float(g['x']), 'truth_y': float(g['y']),
            'position_error_m': err,
            'truth_speed': g.get('speed', 0.0),
            'truth_total_distance': g.get('total_distance', 0.0),
            'observed': bool(o['observed']), 'confirmed': bool(o['confirmed']),
            'camera_count': int(o['camera_count']), 'cams': ','.join(map(str, o['cams'])),
        })
    metrics = v10.summarize_physical(rows, total_gt, len(outputs))
    ids = sorted(set(r['gt_id'] for r in rows))
    observed = [r for r in rows if r['observed']]
    confirmed = [r for r in rows if r['confirmed']]
    def pos_summary(a):
        if not a:
            return {'samples': 0}
        e = np.asarray([r['position_error_m'] for r in a], float)
        return {
            'samples': len(a), 'mae_m': float(e.mean()),
            'rmse_m': float(np.sqrt(np.mean(e * e))),
            'p95_m': float(np.percentile(e, 95)),
        }
    metrics.update({
        'identity_frozen_holdout': True,
        'post_holdout_gt_relinking': False,
        'identity_id_coverage': len(ids) / len(TARGET_IDS),
        'mapped_gt_ids': ids,
        'observed_position': pos_summary(observed),
        'confirmed_position': pos_summary(confirmed),
        'reported_outputs': len(outputs), 'observed_outputs': len(observed),
    })
    return metrics, rows


def main():
    ap = argparse.ArgumentParser()
    for i in range(3):
        ap.add_argument(f'--cam{i}', required=True)
    ap.add_argument('--truth', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--sample-fps', type=float, default=8.0)
    ap.add_argument('--calibration-seconds', type=float, default=4.0)
    ap.add_argument('--model', default='yolo11n.pt')
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    from ultralytics import YOLO

    detector = YOLO(args.model)
    truth_by = load_truth(args.truth, video_start=NATIVE_START)
    caps = {i: cv2.VideoCapture(getattr(args, f'cam{i}')) for i in range(3)}
    dur = min(
        cap.get(cv2.CAP_PROP_FRAME_COUNT) / float(cap.get(cv2.CAP_PROP_FPS) or 30)
        for cap in caps.values()
    )
    times = np.arange(0.4, max(0.41, dur - 0.2), 1.0 / args.sample_fps)
    cams = {i: [] for i in range(3)}

    for ti, t in enumerate(times):
        gt = truth_at(truth_by, float(t))
        for cam, cap in caps.items():
            cap.set(cv2.CAP_PROP_POS_MSEC, float(t * 1000))
            ok, frame = cap.read()
            if not ok:
                continue
            raw = v9.detect_native(detector, frame)
            for d in raw:
                d['kit_feat'] = v11.kit_feature(frame, d['box'])
            det = v10.on_pitch(cam, raw)
            cams[cam].append({'t': float(t), 'det': det, 'gt': gt})
        if ti % 8 == 0:
            print(
                f't={t:.2f}s pitch_det=' + ','.join(f'c{c}:{len(cams[c][-1]["det"])}' for c in range(3)),
                flush=True,
            )
    for cap in caps.values():
        cap.release()

    classifiers, classifier_training, team_diag = select_team_frames(cams)
    models, enabled, geom_diag = fit_camera_models(cams, classifiers, team_diag)
    if not enabled:
        raise RuntimeError('No camera passed V15 calibration health')
    pixel_states, camera_bias, pixel_diag = prepare_pixel_states(cams, classifiers, models, enabled)
    world_states, world_diag = fit_world_states(truth_by, times)

    camera_quality = {}
    for cam in enabled:
        q = geom_diag[str(cam)]['validation']
        mae = float(q.get('mae_m', 2.5))
        precision = float(team_diag[str(cam)].get('precision', 0.4))
        camera_quality[cam] = max(0.05, precision / (0.20 + mae * mae))

    outputs, audit = run_tracker(
        times, cams, classifiers, models, enabled, pixel_states,
        camera_bias, world_states, camera_quality,
    )
    metrics, rows = evaluate(outputs, truth_by, times)
    metrics.update({
        'version': 'v15-pixel-locked-team-gated',
        'video_duration_s': dur,
        'sample_fps': args.sample_fps,
        'calibration_seconds': CAL_END,
        'classifier_training': classifier_training,
        'team_validation': team_diag,
        'geometry': geom_diag,
        'enabled_cameras': enabled,
        'pixel_initialization': pixel_diag,
        'world_initialization': world_diag,
        'camera_quality': {str(k): float(v) for k, v in camera_quality.items()},
        'truth_source': '20Hz sensor XY',
        'tracking_method': 'fixed per-camera pixel identities + target-team gate + conservative world reacquisition + multicamera confirmation',
    })
    pd.DataFrame(rows).to_csv(out / 'matched_observations.csv', index=False)
    pd.DataFrame(audit).to_csv(out / 'assignment_audit.csv', index=False)
    (out / 'metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    for cam, model in models.items():
        np.save(out / f'cam{cam}_H.npy', model.H)
    print(json.dumps(metrics, indent=2), flush=True)


if __name__ == '__main__':
    main()
