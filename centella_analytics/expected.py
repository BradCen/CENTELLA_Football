from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

import numpy as np


@dataclass(frozen=True, slots=True)
class ShotFeatures:
    x: float
    y: float
    pitch_length: float = 105.0
    pitch_width: float = 68.0
    angle_rad: float | None = None
    pressure_count: int = 0
    nearest_defender_m: float | None = None
    body_part: str = "foot"
    assisted: bool = False
    set_piece: bool = False

    @property
    def distance_to_goal_m(self) -> float:
        return float(math.hypot(self.pitch_length - self.x, self.pitch_width / 2.0 - self.y))

    @property
    def angle(self) -> float:
        if self.angle_rad is not None:
            return abs(float(self.angle_rad))
        dx = self.pitch_length - self.x
        dy = self.pitch_width / 2.0 - self.y
        return float(abs(math.atan2(dy, max(1e-9, dx))))

    def vector(self) -> np.ndarray:
        d = self.distance_to_goal_m
        a = self.angle
        pressure = min(8.0, max(0.0, float(self.pressure_count)))
        defender = 8.0 if self.nearest_defender_m is None else min(8.0, max(0.0, self.nearest_defender_m))
        return np.asarray([
            1.0, d, d * d, math.sin(a), math.sin(a) ** 2, pressure, defender,
            float(self.body_part == "head"), float(self.body_part == "other"),
            float(self.assisted), float(self.set_piece),
        ], dtype=float)


@dataclass(slots=True)
class LogisticXGModel:
    coefficients: np.ndarray
    intercept: float = 0.0
    calibrated: bool = False
    version: str = "centella-xg-1"
    feature_mean: np.ndarray | None = None
    feature_scale: np.ndarray | None = None

    def _transform(self, vector: np.ndarray) -> np.ndarray:
        if self.feature_mean is None or self.feature_scale is None:
            return vector
        return (vector - self.feature_mean) / self.feature_scale

    def predict_one(self, features: ShotFeatures) -> float:
        z = float(self.intercept + self.coefficients @ self._transform(features.vector()))
        z = max(-35.0, min(35.0, z))
        return float(1.0 / (1.0 + math.exp(-z)))

    def predict(self, shots: Iterable[ShotFeatures]) -> np.ndarray:
        return np.asarray([self.predict_one(s) for s in shots], dtype=float)

    def metadata(self) -> dict:
        return {
            "version": self.version,
            "calibrated": self.calibrated,
            "feature_count": int(len(self.coefficients)),
            "standardized": self.feature_mean is not None,
            "interpretation": "goal probability per shot; calibrate on labelled local shots before claiming production accuracy",
        }

    @classmethod
    def heuristic(cls) -> "LogisticXGModel":
        coeffs = np.asarray([0.0, -0.075, 0.0010, 2.20, -0.85, -0.22, 0.035, -0.35, -0.15, 0.12, -0.10], dtype=float)
        return cls(coeffs, intercept=-1.65, calibrated=False, version="centella-xg-heuristic-1")


def fit_xg(
    shots: Sequence[ShotFeatures],
    goals: Sequence[int | bool],
    *,
    l2: float = 0.02,
    learning_rate: float = 0.08,
    epochs: int = 3000,
) -> LogisticXGModel:
    """Fit a regularized logistic xG model with stable feature standardization."""
    if len(shots) != len(goals) or not shots:
        raise ValueError("shots and goals must be non-empty and have equal length")
    X_raw = np.vstack([s.vector() for s in shots])
    y = np.asarray(goals, dtype=float)
    if not np.all((y == 0) | (y == 1)):
        raise ValueError("goals must contain only 0/1 values")
    mean = X_raw.mean(axis=0); scale = X_raw.std(axis=0)
    mean[0] = 0.0; scale[0] = 1.0
    scale[scale < 1e-8] = 1.0
    X = (X_raw - mean) / scale
    w = np.zeros(X.shape[1], dtype=float); b = 0.0; n = len(y)
    for _ in range(max(1, epochs)):
        z = np.clip(b + X @ w, -35.0, 35.0)
        p = 1.0 / (1.0 + np.exp(-z))
        grad_w = (X.T @ (p - y)) / n + l2 * w
        grad_b = float(np.mean(p - y))
        w -= learning_rate * grad_w; b -= learning_rate * grad_b
    return LogisticXGModel(w, b, calibrated=True, version="centella-xg-logistic-1", feature_mean=mean, feature_scale=scale)
