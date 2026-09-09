from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .expected import LogisticXGModel


def save_xg_model(model: LogisticXGModel, path: str | Path) -> None:
    payload = {
        "coefficients": model.coefficients.tolist(),
        "intercept": model.intercept,
        "calibrated": model.calibrated,
        "version": model.version,
        "feature_mean": model.feature_mean.tolist() if model.feature_mean is not None else None,
        "feature_scale": model.feature_scale.tolist() if model.feature_scale is not None else None,
    }
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_xg_model(path: str | Path) -> LogisticXGModel:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return LogisticXGModel(
        coefficients=np.asarray(payload["coefficients"], dtype=float),
        intercept=float(payload.get("intercept", 0.0)),
        calibrated=bool(payload.get("calibrated", False)),
        version=str(payload.get("version", "centella-xg-1")),
        feature_mean=np.asarray(payload["feature_mean"], dtype=float) if payload.get("feature_mean") is not None else None,
        feature_scale=np.asarray(payload["feature_scale"], dtype=float) if payload.get("feature_scale") is not None else None,
    )
