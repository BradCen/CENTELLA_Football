from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

import alfheim_benchmark_v19 as v19
import alfheim_benchmark_v31 as v31

NATIVE_OFFSET_S = v31.NATIVE_OFFSET_S
_ORIGINAL_TRUTH_AT = v31._ORIGINAL_TRUTH_AT
_ORIGINAL_CHOOSE_GEOMETRY = v31._ORIGINAL_CHOOSE_GEOMETRY
_PLAYER_QUALITY = v31._PLAYER_QUALITY
VALIDATED_LIMIT_M = v31.VALIDATED_LIMIT_M


def truth_at_native(truth_by, t):
    return _ORIGINAL_TRUTH_AT(truth_by, float(t) + NATIVE_OFFSET_S)


def choose_geometry_with_player_quality(cam, records, calibration_seconds=4.0):
    return v31.choose_geometry_with_player_quality(cam, records, calibration_seconds)


def _center(box):
    b = np.asarray(box, float)
    return np.asarray([(b[0] + b[2]) * 0.5, (b[1] + b[3]) * 0.5], float)


def _height(box):
    b = np.asarray(box, float)
    return max(12.0, float(b[3] - b[1]))


def _cosdist(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    na = np.linalg.norm(a); nb = np.linalg.norm(b)
    if na < 1e-8 or nb < 1e-8:
        return 1.0
    return float(1.0 - np.dot(a, b) / (na * nb))


def reset_state_identity(state, gray, d, t, calibration=True):
    old_box = state.get('bbox')
    old_t = state.get('detector_t')
    if old_box is not None and old_t is not None:
        dt = float(t) - float(old_t)
        if 0.03 <= dt <= 2.0:
            c_old = _center(old_box)
            c_new = _center(d['box'])
            raw = (c_new - c_old) / dt
            prev = np.asarray(state.get('image_velocity_px_s', raw), float)
            state['image_velocity_px_s'] = 0.35 * raw + 0.65 * prev

    state['bbox'] = np.asarray(d['box'], float)
    state['pts'] = v19.seed_points(gray, state['bbox'])
    state['fail_frames'] = 0
    state['last_detector_t'] = float(t)
    state['last_t'] = float(t)
    state['detector_center'] = _center(state['bbox'])
    if calibration:
        state['cal_feats'].append(np.asarray(d['feat'], float))
        if len(state['cal_feats']) > 30:
            state['cal_feats'] = state['cal_feats'][-30:]
        state['appearance_proto'] = np.asarray(d['feat'], float).copy()
    elif 'appearance_proto' not in state:
        state['appearance_proto'] = np.asarray(d['feat'], float).copy()
    return state


def detector_correct_identity(states, dets, gray, model, bias, t):
    gids = [g for g, s in states.items() if s.get('bbox') is not None and s.get('fail_frames', 0) <= 12]
    if not gids or not dets:
        return 0

    C = np.full((len(gids), len(dets)), 1e6, float)
    raw_features = {}
    diagnostics = []

    for ii, gid in enumerate(gids):
        s = states[gid]
        b = np.asarray(s['bbox'], float)
        h = _height(b)
        c0 = _center(b)
        prev_c = np.asarray(s.get('detector_center', c0), float)
        dt = max(0.0, float(t) - float(s.get('detector_t', t)))
        vel_px = np.asarray(s.get('image_velocity_px_s', np.zeros(2)), float)
        predicted_c = prev_c + np.clip(dt, 0.0, 1.2) * vel_px
        proto_cal = np.median(np.asarray(s['cal_feats'], float), axis=0) if s.get('cal_feats') else None
        proto_adapt = s.get('appearance_proto', proto_cal)

        last_world = s.get('last_world_pos')
        world_vel = np.asarray(s.get('world_velocity_mps', np.zeros(2)), float)
        predicted_world = None
        if last_world is not None:
            predicted_world = np.asarray(last_world, float) + np.clip(dt, 0.0, 1.2) * world_vel
        current_opt_world = model.project(np.asarray([v19.foot_of(b)], float))[0] + bias

        vals = []
        for j, d in enumerate(dets):
            db = np.asarray(d['box'], float)
            dc = _center(db)
            motion_h = float(np.linalg.norm(dc - predicted_c) / h)
            instant_h = float(np.linalg.norm(dc - c0) / h)
            iou = v19.box_iou(b, db)
            app_cal = _cosdist(proto_cal, d['feat']) if proto_cal is not None else 0.5
            app_adapt = _cosdist(proto_adapt, d['feat']) if proto_adapt is not None else app_cal
            app = min(app_cal, app_adapt)
            dw = model.project(np.asarray([d['foot']], float))[0] + bias
            world_gap = float(np.linalg.norm(dw - current_opt_world))
            pred_world_gap = float(np.linalg.norm(dw - predicted_world)) if predicted_world is not None else world_gap

            # Basic geometry rejection remains deliberately permissive; identity
            # is resolved with the full temporal cost instead of hard per-frame gates.
            if motion_h > 2.2 and instant_h > 2.5 and iou < 0.005:
                continue
            if world_gap > 7.0 and motion_h > 1.2:
                continue

            # Appearance is stable but not absolute. Temporal/world continuity
            # dominate at crossings, while appearance breaks ties after long gaps.
            cost = (
                0.90 * min(motion_h, 3.0)
                + 0.26 * min(instant_h, 3.0)
                + 0.40 * (1.0 - iou)
                + 1.15 * min(app, 1.0)
                + 0.10 * min(world_gap, 8.0)
                + 0.34 * min(pred_world_gap, 8.0)
            )

            # Healthy tracks get strong hysteresis against implausible identity
            # jumps. A detector can still take over after optical failure.
            healthy = int(s.get('fail_frames', 0)) == 0
            if healthy and motion_h > 0.95 and app > 0.32:
                cost += 0.34
            if healthy and predicted_world is not None and pred_world_gap > 4.0 and app > 0.30:
                cost += 0.28

            C[ii, j] = cost
            vals.append((cost, j, motion_h, instant_h, app, pred_world_gap))

        vals.sort(key=lambda x: x[0])
        raw_features[gid] = vals

    ri, ci = linear_sum_assignment(C)
    n = 0
    for ii, j in zip(ri, ci):
        if C[ii, j] >= 1e5:
            continue
        gid = gids[ii]
        s = states[gid]
        vals = raw_features.get(gid, [])
        selected = next((x for x in vals if x[1] == j), None)
        if selected is None:
            continue
        cost, _, motion_h, instant_h, app, pred_world_gap = selected

        # Identity-preserving hysteresis: when two detections are nearly tied,
        # leave a healthy track untouched rather than gambling on a switch.
        alternative = [x for x in vals if x[1] != j]
        margin = (alternative[0][0] - cost) if alternative else 99.0
        healthy = int(s.get('fail_frames', 0)) == 0
        if healthy and margin < 0.16 and motion_h > 0.55:
            continue
        if healthy and motion_h > 1.25 and app > 0.35 and instant_h > 1.0:
            continue
        if cost > 4.25:
            continue

        d = dets[j]
        old_box = np.asarray(s['bbox'], float)
        new_box = np.asarray(d['box'], float)
        blend = 0.84 if s.get('fail_frames', 0) > 0 else 0.68
        dd = dict(d)
        dd['box'] = blend * new_box + (1.0 - blend) * old_box
        reset_state_identity(s, gray, dd, t, calibration=False)

        # Update the long-term appearance prototype only for a confident match.
        feat = np.asarray(d['feat'], float)
        if s.get('appearance_proto') is None:
            s['appearance_proto'] = feat.copy()
        else:
            alpha = 0.08 if healthy else 0.16
            s['appearance_proto'] = (1.0 - alpha) * np.asarray(s['appearance_proto'], float) + alpha * feat

        world = model.project(np.asarray([v19.foot_of(dd['box'])], float))[0] + bias
        prev_world = s.get('last_world_pos')
        prev_world_t = s.get('last_world_t')
        if prev_world is not None and prev_world_t is not None:
            dtw = float(t) - float(prev_world_t)
            if 0.03 <= dtw <= 2.0:
                raw_v = (world - np.asarray(prev_world, float)) / dtw
                old_v = np.asarray(s.get('world_velocity_mps', raw_v), float)
                s['world_velocity_mps'] = 0.28 * raw_v + 0.72 * old_v
        s['last_world_pos'] = np.asarray(world, float)
        s['last_world_t'] = float(t)
        s['detector_t'] = float(t)
        diagnostics.append({
            'gid': int(gid),
            'cost': float(cost),
            'margin': float(margin),
            'motion_h': float(motion_h),
            'appearance': float(app),
            'pred_world_gap_m': float(pred_world_gap),
        })
        n += 1

    # Keep a compact, non-GT diagnostic on the states for debugging artifacts.
    for gid, s in states.items():
        s['last_reassociation'] = diagnostics[-1] if diagnostics and diagnostics[-1]['gid'] == int(gid) else s.get('last_reassociation')
    return n


def fuse_per_player(all_outputs, qualities, truth_by):
    return v31.fuse_per_player(all_outputs, qualities, truth_by)


def main():
    _PLAYER_QUALITY.clear()
    v19.truth_at = truth_at_native
    v19.CAL_SPLIT = 3.0
    v19.choose_geometry = choose_geometry_with_player_quality
    v19.reset_state = reset_state_identity
    v19.detector_correct = detector_correct_identity
    v19.fuse = fuse_per_player
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
            m['version'] = 'v32-temporal-identity-preserving-reassociation'
            m['fusion_policy'] = {
                'selection': 'lowest per-player validation MAE, with camera fallback',
                'validated_camera_mae_limit_m': VALIDATED_LIMIT_M,
                'holdout_ground_truth_used_for_inference': False,
                'identity_policy': 'one-to-one temporal re-association using image motion, world prediction and long-term appearance',
                'identity_hysteresis': True,
            }
            m['per_player_camera_validation_mae_m'] = {
                str(cam): {str(g): q for g, q in sorted(vals.items())}
                for cam, vals in sorted(_PLAYER_QUALITY.items())
            }
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
