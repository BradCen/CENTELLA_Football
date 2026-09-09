from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

import numpy as np


@dataclass(frozen=True, slots=True)
class ShotFeatures:
    """Features for an xG model. Coordinates are in metres, origin at attacking goal."""

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
        gx, gy = self.pitch_length, self.pitch_width / 2.0
        return float(math.hypot(gx - self.x, gy - self.y))

    @property
    def angle(self) -> float:
        if self.angle_rad is not None:
            return abs(float(self.angle_rad))
        gx, gy = self.pitch_length, self.pitch_width / 2.0
        a = abs(math.atan2(gy - self.y, gx - self.x))
        return float(math.pi - a) if a > math.pi / 2 else float(a)

    def vector(self) -> np.ndarray:
        d = self.distance_to_goal_m
        a = self.angle
        pressure = min(8.0, max(0.0, float(self.pressure_count)))
        defender = 8.0 if self.nearest_defender_m is None else min(8.0, max(0.0, self.nearest_defender_m))
        return np.asarray([
            1.0,
            d,
            d * d,
            math.sin(a),
            math.sin(a) ** 2,
            pressure,
            defender,
            1.0 if self.body_part == "head" else 0.0,
            1.0 if self.body_part == "other" else 0.0,
            1.0 if self.assisted else 0.0,
            1.0 if self.set_piece else 0.0,
        ], dtype=float)


@dataclass(slots=True)
class LogisticXGModel:
    """Logistic xG model with explicit, serializable coefficients.

    Models trained on real shot labels are the production path. `heuristic()` exists
    only for bootstrapping before sufficient local data has been collected and marks
    itself as uncalibrated in `metadata()`.
    """

    coefficients: np.ndarray
    intercept: float = 0.0
    calibrated: bool = False
    version: str = "centella-xg-1"

    def predict_one(self, features: ShotFeatures) -> float:
        z = float(self.intercept + self.coefficients @ features.vector())
        z = max(-35.0, min(35.0, z))
        return float(1.0 / (1.0 + math.exp(-z)))

    def predict(self, shots: Iterable[ShotFeatures]) -> np.ndarray:
        return np.asarray([self.predict_one(s) for s in shots], dtype=float)

    def metadata(self) -> dict:
        return {
            "version": self.version,
            "calibrated": self.calibrated,
            "feature_count": int(len(self.coefficients)),
            "interpretation": "goal probability per shot; train/calibrate on local labelled shots before claiming production accuracy",
        }

    @classmethod
    def heuristic(cls) -> "LogisticXGModel":
        # Conservative prior: distance hurts, angle helps, defensive pressure hurts.
        # These coefficients are explicitly a bootstrap prior, not a benchmark claim.
        coeffs = np.asarray([
            0.0, -0.075, 0.0010, 2.20, -0.85,
            -0.22, 0.035, -0.35, -0.15, 0.12, -0.10,
        ], dtype=float)
        return cls(coeffs, intercept=-1.65, calibrated=False, version="centella-xg-heuristic-1")


def fit_xg(
    shots: Sequence[ShotFeatures],
    goals: Sequence[int | bool],
    *,
    l2: float = 0.02,
    learning_rate: float = 0.05,
    epochs: int = 2500,
) -> LogisticXGModel:
    """Fit a regularized logistic xG model with pure NumPy.

    `goals` must contain 0/1 labels. A minimum-data warning is returned in metadata
    by the caller rather than hiding a statistically weak model.
    """
    if len(shots) != len(goals) or not shots:
        raise ValueError("shots and goals must be non-empty and have equal length")
    X = np.vstack([s.vector() for s in shots])
    y = np.asarray(goals, dtype=float)
    if not np.all((y == 0) | (y == 1)):
        raise ValueError("goals must contain only 0/1 values")
    w = np.zeros(X.shape[1], dtype=float)
    b = 0.0
    n = len(y)
    for _ in range(max(1, epochs)):
        z = np.clip(b + X @ w, -35.0, 35.0)
        p = 1.0 / (1.0 + np.exp(-z))
        grad_w = (X.T @ (p - y)) / n + l2 * w
        grad_b = float(np.mean(p - y))
        w -= learning_rate * grad_w
        b -= learning_rate * grad_b
    return LogisticXGModel(w, b, calibrated=True, version="centella-xg-logistic-1")
