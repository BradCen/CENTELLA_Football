from __future__ import annotations

import json
import sys
from pathlib import Path

import alfheim_benchmark as base
import alfheim_benchmark_v19 as v19

# Native cameras start later than the panorama used by the original truth
# loader: 18:01:14.248366 vs 18:01:12.794293.  Native-camera t=0 therefore
# must be evaluated against truth shifted by this fixed offset.
NATIVE_OFFSET_S = 14.248366 - 12.794293
_ORIGINAL_TRUTH_AT = base.truth_at


def truth_at_native(truth_by, t):
    return _ORIGINAL_TRUTH_AT(truth_by, float(t) + NATIVE_OFFSET_S)


def main():
    # Keep v19.NATIVE_START as its original pandas Timestamp.  load_truth()
    # needs that timestamp type; only truth_at() gets the native-video offset.
    v19.truth_at = truth_at_native
    v19.CAL_SPLIT = 3.0
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
            m['version'] = 'v21-native-truth-time-alignment'
            m['native_truth_offset_s'] = NATIVE_OFFSET_S
            m['truth_alignment_note'] = 'native camera t=0 aligned to native start 18:01:14.248366 instead of panorama start 18:01:12.794293'
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
