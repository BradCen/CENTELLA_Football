from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import alfheim_benchmark_v19 as v19
import alfheim_benchmark_v26 as v26

CAL_SPLIT = 3.0
NATIVE_OFFSET_S = v26.NATIVE_OFFSET_S
_ORIGINAL_TRUTH_AT = v26._ORIGINAL_TRUTH_AT
_ORIGINAL_RESET_STATE = v19.reset_state
_ORIGINAL_DETECTOR_CORRECT = v19.detector_correct


def truth_at_native(truth_by, t):
    return _ORIGINAL_TRUTH_AT(truth_by, float(t) + NATIVE_OFFSET_S)


def _cosdist(a, b):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na < 1e-8 or nb < 1e-8:
        return 1.0
    return float(1.0 - np.dot(a, b) / (na * nb))


def _center(box):
    b = np.asarray(box, float)
    return np.asarray([(b[0] + b[2]) * 0.5, (b[1] + b[3]) * 0.5], float)


def _iou(a, b):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    x1 = max(a[0], b[0]); y1 = max(a[1], b[1])
    x2 = min(a[2], b[2]); y2 = min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    aa = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    bb = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return inter / max(1e-6, aa + bb - inter)


def reset_state_temporal_identity_gate(state, gray, d, t, calibration=True):
    """Keep calibration identities attached to temporally plausible tracks.

    V19 re-seeds a GT-associated identity whenever confident_pairs returns a
    detection. During the four-second calibration window, a single ambiguous
    detector/GT association can therefore move an identity to another nearby
    player and poison every later frozen holdout label. This gate only affects
    calibration and rejects implausible jumps using camera-space continuity,
    box scale, and accumulated appearance. It never reads holdout GT.
    """
    if calibration and float(t) <= CAL_SPLIT + 1e-6 and state.get('bbox') is not None:
        old = np.asarray(state['bbox'], float)
        new = np.asarray(d['box'], float)
        old_h = max(12.0, old[3] - old[1])
        old_w = max(8.0, old[2] - old[0])
        new_h = max(12.0, new[3] - new[1])
        jump = float(np.linalg.norm(_center(new) - _center(old)) / old_h)
        scale = float(new_h / old_h)
        overlap = _iou(old, new)
        feats = state.get('cal_feats') or []
        app = 0.0
        if feats:
            proto = np.median(np.asarray(feats, float), axis=0)
            app = _cosdist(proto, d['feat'])

        # The optical track is updated before detector calibration happens, so
        # normal motion stays well below this gate. A far jump with little box
        # overlap is treated as a likely identity reassignment.
        if jump > 0.72 and overlap < 0.015:
            return state
        if (scale < 0.52 or scale > 1.85) and jump > 0.25:
            return state
        # Once a prototype exists, reject a detector that looks substantially
        # unlike the established identity while also requiring a meaningful move.
        if len(feats) >= 3 and app > 0.62 and jump > 0.25 and overlap < 0.10:
            return state

    return _ORIGINAL_RESET_STATE(state, gray, d, t, calibration=calibration)


def detector_correct_passthrough(states, dets, gray, model, bias, t):
    # V26 holdout correction remains unchanged; the experiment isolates the
    # temporal gate during the calibration/identity formation window.
    return _ORIGINAL_DETECTOR_CORRECT(states, dets, gray, model, bias, t)


def main():
    v19.truth_at = truth_at_native
    v19.CAL_SPLIT = CAL_SPLIT
    v19.reset_state = reset_state_temporal_identity_gate
    v19.detector_correct = detector_correct_passthrough
    v19.fuse = v26.fuse_best_camera
    v19.main()

    out = None
    import sys
    for i, a in enumerate(sys.argv[:-1]):
        if a == '--out':
            out = Path(sys.argv[i + 1])
            break
    if out:
        p = out / 'metrics.json'
        if p.exists():
            m = json.loads(p.read_text(encoding='utf-8'))
            m['version'] = 'v37-temporal-calibration-identity-gate'
            m['native_truth_offset_s'] = NATIVE_OFFSET_S
            m['fusion_policy'] = {
                'selection': 'lowest global validation-MAE camera per identity/time',
                'holdout_ground_truth_used_for_inference': False,
                'calibration_identity_policy': 'reject implausible temporal/scale/appearance identity jumps during t<=3s calibration',
                'holdout_detector_policy': 'unchanged V26 detector correction',
                'objective': 'prevent early calibration identity reassignment from poisoning frozen holdout labels',
            }
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
