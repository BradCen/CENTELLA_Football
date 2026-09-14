from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from .types import PlayerSample


@dataclass(slots=True)
class WorkloadProfile:
    player_id: str
    historical_loads: list[float] = field(default_factory=list)
    historical_minutes: list[float] = field(default_factory=list)
    max_speed_mps: float = 0.0

    def baseline(self) -> dict:
        if not self.historical_loads:
            return {"samples": 0, "baseline_load": None, "std_load": None}
        a = np.asarray(self.historical_loads, dtype=float)
        return {"samples": int(len(a)), "baseline_load": float(np.median(a)), "std_load": float(np.std(a))}


def compute_workload(samples: Sequence[PlayerSample], profile: WorkloadProfile | None = None) -> dict:
    """Derive external-load indicators from tracking and compare to player baseline.

    This deliberately avoids a medical injury probability. Flags are workload
    deviations that should trigger coach/medical review, not diagnoses.
    """
    if not samples:
        return {"valid": False, "reason": "no_samples"}
    times = np.asarray([p.t for p in samples], dtype=float)
    order = np.argsort(times)
    s = [samples[i] for i in order]
    duration = max(1e-6, s[-1].t - s[0].t)
    speeds = np.asarray([p.speed for p in s], dtype=float)
    accel = np.asarray([abs(p.acceleration_mps2) for p in s if p.acceleration_mps2 is not None], dtype=float)
    # Proxy load: integrate speed change magnitude.  It is intentionally named
    # external_load_proxy so it cannot be mistaken for Catapult PlayerLoad.
    load = float(np.sum(np.abs(np.diff(speeds))))
    distance = float(np.sum([np.hypot(s[i].x-s[i-1].x, s[i].y-s[i-1].y) for i in range(1, len(s))]))
    high_speed = float(np.sum(speeds >= 5.5) / len(s))
    sprint = float(np.sum(speeds >= 7.0) / len(s))
    baseline = profile.baseline() if profile else {"samples": 0, "baseline_load": None, "std_load": None}
    z = None
    flag = "unknown"
    if baseline["baseline_load"] is not None:
        sd = max(1e-6, float(baseline["std_load"]))
        z = (load - float(baseline["baseline_load"])) / sd
        flag = "high_deviation" if z >= 2.0 else "moderate_deviation" if z >= 1.0 else "within_baseline"
    return {
        "valid": True,
        "duration_s": float(duration),
        "distance_m": distance,
        "mean_speed_mps": float(speeds.mean()),
        "max_speed_mps": float(speeds.max()),
        "high_speed_observation_share": high_speed,
        "sprint_observation_share": sprint,
        "acceleration_abs_mean_mps2": float(accel.mean()) if len(accel) else None,
        "external_load_proxy": load,
        "baseline": baseline,
        "baseline_z": float(z) if z is not None else None,
        "load_flag": flag,
        "medical_safety_note": "This is not an injury diagnosis or medical risk score.",
    }
