from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

import alfheim_benchmark_v19 as v19
import alfheim_benchmark_v26 as v26

NATIVE_OFFSET_S = v26.NATIVE_OFFSET_S
_ORIGINAL_TRUTH_AT = v26._ORIGINAL_TRUTH_AT
_ORIGINAL_DETECTOR_CORRECT = v19.detector_correct


def truth_at_native(truth_by, t):
    return _ORIGINAL_TRUTH_AT(truth_by, float(t) + NATIVE_OFFSET_S)


def detector_correct_healthy_lock(states, dets, gray, model, bias, t):
    """V26 detector correction, but never overwrite a healthy optical lock.

    The holdout identity diagnostic showed that identity swaps, rather than
    camera geometry, dominate the remaining error. A detector correction is
    therefore allowed only when the optical track has actually failed. Healthy
    tracks continue on Lucas-Kanade flow uninterrupted.
    """
    work = {}
    for gid, state in states.items():
        if int(state.get('fail_frames', 0)) == 0:
            clone = dict(state)
            clone['bbox'] = None
            work[gid] = clone
        else:
            work[gid] = state
    return _ORIGINAL_DETECTOR_CORRECT(work, dets, gray, model, bias, t)


def main():
    v19.truth_at = truth_at_native
    v19.CAL_SPLIT = 3.0
    v19.detector_correct = detector_correct_healthy_lock
    v19.fuse = v26.fuse_best_camera
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
            m['version'] = 'v36-healthy-optical-lock'
            m['native_truth_offset_s'] = NATIVE_OFFSET_S
            m['fusion_policy'] = {
                'selection': 'lowest global validation-MAE camera per identity/time',
                'holdout_ground_truth_used_for_inference': False,
                'detector_policy': 'detector correction disabled for healthy optical locks; enabled after optical failure',
                'objective': 'reduce identity flips caused by detector overwrite during healthy optical tracking',
            }
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
