from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

import alfheim_benchmark as base
import alfheim_benchmark_v19 as v19

NATIVE_OFFSET_S = 14.248366 - 12.794293
_ORIGINAL_TRUTH_AT = base.truth_at
_ORIGINAL_CHOOSE_GEOMETRY = v19.choose_geometry


def truth_at_native(truth_by, t):
    return _ORIGINAL_TRUTH_AT(truth_by, float(t) + NATIVE_OFFSET_S)


def choose_geometry_with_training_bias(cam, records, calibration_seconds=4.0):
    """Keep V21 geometry selection, but use legal calibration evidence for bias.

    Some cameras do not observe a useful player during the 3-4s validation
    slice. The previous implementation then emitted zero geometric bias even
    though it had accepted calibration pairs during t<=3s. This variant keeps
    the original model/candidate selection and only falls back to a robust
    median training residual when validation is genuinely empty.
    """
    model, bias, diag = _ORIGINAL_CHOOSE_GEOMETRY(cam, records, calibration_seconds)
    if int(diag.get('validation_pairs', 0)) > 0:
        return model, bias, diag

    train = [r for r in records if float(r['t']) <= float(v19.CAL_SPLIT)]
    if not train:
        return model, bias, diag

    residuals = []
    for r in train:
        pred = model.project(np.asarray([r['pix']], float))[0]
        residuals.append(np.asarray(r['world'], float) - pred)
    residuals = np.asarray(residuals, float)
    train_bias = np.median(residuals, axis=0)

    # Only apply a bounded robust bias. A very large residual signals bad
    # geometry, and silently translating the whole camera would hide that.
    magnitude = float(np.linalg.norm(train_bias))
    if magnitude > 8.0:
        return model, bias, diag

    diag = dict(diag)
    diag['bias_source'] = 'training_calibration_fallback'
    diag['training_bias_m'] = train_bias.tolist()
    diag['training_bias_norm_m'] = magnitude
    return model, train_bias, diag


def main():
    v19.truth_at = truth_at_native
    v19.CAL_SPLIT = 3.0
    v19.choose_geometry = choose_geometry_with_training_bias
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
            m['version'] = 'v24-training-bias-fallback'
            m['native_truth_offset_s'] = NATIVE_OFFSET_S
            m['calibration_policy'] = {
                'validation_required_for_model_selection': True,
                'zero_validation_bias_source': 'median_training_calibration_residual',
                'max_training_bias_norm_m': 8.0,
            }
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
