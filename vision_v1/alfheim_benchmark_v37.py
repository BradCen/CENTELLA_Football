from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import alfheim_benchmark_v19 as v19
import alfheim_benchmark_v26 as v26

NATIVE_OFFSET_S = v26.NATIVE_OFFSET_S
_ORIGINAL_TRUTH_AT = v26._ORIGINAL_TRUTH_AT
_ORIGINAL_DETECTOR_CORRECT = v19.detector_correct


def truth_at_native(truth_by, t):
    return _ORIGINAL_TRUTH_AT(truth_by, float(t) + NATIVE_OFFSET_S)


def _bbox_close(a, b):
    if a is None or b is None:
        return False
    a = __import__('numpy').asarray(a, float)
    b = __import__('numpy').asarray(b, float)
    h = max(12.0, float(a[3] - a[1]))
    center_gap = float(__import__('numpy').linalg.norm(
        __import__('numpy').asarray([(a[0] + a[2]) / 2, (a[1] + a[3]) / 2]) -
        __import__('numpy').asarray([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2])
    )) / h
    return center_gap <= 0.22


_PENDING = {}


def detector_correct_transition_persistence(states, dets, gray, model, bias, t):
    """V39: a detector-induced identity transition must repeat coherently twice.

    The original V26 correction remains the candidate generator. Any state change
    caused by detector reacquisition is rolled back on the first observation and
    only committed on the next detector opportunity when the proposed bbox remains
    spatially coherent. Optical tracking itself is untouched.
    """
    global _PENDING
    before = {gid: copy.deepcopy(state) for gid, state in states.items()}
    n_original = _ORIGINAL_DETECTOR_CORRECT(states, dets, gray, model, bias, t)
    if n_original <= 0:
        _PENDING.clear()
        return 0

    accepted = 0
    changed = set()
    for gid, state in states.items():
        b0 = before[gid].get('bbox')
        b1 = state.get('bbox')
        if b0 is None or b1 is None:
            continue
        if not _bbox_close(b0, b1):
            changed.add(gid)

    for gid in changed:
        proposal = __import__('numpy').asarray(states[gid]['bbox'], float).copy()
        prev = _PENDING.get(gid)
        same = prev is not None and _bbox_close(prev['bbox'], proposal)
        count = int(prev['count']) + 1 if same else 1
        if count >= 2:
            _PENDING.pop(gid, None)
            accepted += 1
            continue
        states[gid].clear()
        states[gid].update(copy.deepcopy(before[gid]))
        _PENDING[gid] = {'bbox': proposal, 'count': count}

    # Corrections not seen again are not retained as latent candidates.
    for gid in list(_PENDING):
        if gid not in changed:
            _PENDING.pop(gid, None)

    # Return only transitions actually committed. The underlying routine may have
    # performed several candidate resets, but unconfirmed ones are fully reverted.
    return accepted


def main():
    v19.truth_at = truth_at_native
    v19.CAL_SPLIT = 3.0
    v19.detector_correct = detector_correct_transition_persistence
    v19.fuse = v26.fuse_best_camera
    v19.main()
    out = None
    for i, a in enumerate(sys.argv[:-1]):
        if a == '--out':
            out = Path(sys.argv[i + 1]); break
    if out:
        p = out / 'metrics.json'
        if p.exists():
            m = json.loads(p.read_text(encoding='utf-8'))
            m['version'] = 'v39-detector-transition-persistence'
            m['native_truth_offset_s'] = NATIVE_OFFSET_S
            m['fusion_policy'] = {
                'selection': 'lowest global validation-MAE camera per identity/time',
                'holdout_ground_truth_used_for_inference': False,
                'detector_policy': 'detector-induced identity transitions require two coherent consecutive detector observations before commit',
                'objective': 'prevent one-opportunity detector reacquisition swaps while preserving V26 optical/geometry behavior',
            }
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
