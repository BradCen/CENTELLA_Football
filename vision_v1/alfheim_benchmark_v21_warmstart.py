from __future__ import annotations

import json
import sys
from pathlib import Path

import alfheim_benchmark_v19 as v19

# V20 showed that the short 4 s cold-start calibration is too restrictive for
# player identity.  V21 uses a practical 10 s warm-start window and reserves
# the remaining sequence as a completely unseen holdout.  The sensor truth is
# still used only during calibration/evaluation; it is never consulted by the
# tracker during holdout.
CAL_SPLIT_S = 7.0


def main():
    v19.CAL_SPLIT = CAL_SPLIT_S
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
            m['version'] = 'v21-warmstart-native'
            m['calibration_seconds'] = 10.0
            m['geometry_train_split_seconds'] = CAL_SPLIT_S
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
