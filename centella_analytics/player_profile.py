from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Sequence

import numpy as np

from .events import DuelEvent, PassEvent, ShotEvent
from .types import PlayerSample


def _rate(count: int, minutes: float) -> float:
    return float(90.0 * count / minutes) if minutes > 0 else 0.0


def player_passport(
    samples: Sequence[PlayerSample],
    passes: Sequence[PassEvent] = (),
    shots: Sequence[ShotEvent] = (),
    duels: Sequence[DuelEvent] = (),
) -> dict:
    """Create an objective player passport from observed physical + event data.

    The result separates measured rates from role interpretation. It intentionally does
    not force a single "best position" when the available evidence is insufficient.
    """
    if not samples:
        return {"valid": False, "reason": "no_player_samples"}
    samples = sorted(samples, key=lambda p: p.t)
    pid = samples[0].player_id
    duration_s = max(1e-6, samples[-1].t - samples[0].t)
    speeds = np.asarray([p.speed for p in samples], dtype=float)
    x = np.asarray([p.x for p in samples], dtype=float); y = np.asarray([p.y for p in samples], dtype=float)
    minutes = duration_s / 60.0
    player_passes = [p for p in passes if p.passer_id == pid]
    player_shots = [s for s in shots if s.player_id == pid]
    player_duels = [d for d in duels if d.player_id == pid]
    completed = sum(p.successful for p in player_passes)
    progressive = sum(max(0.0, p.progressive_m) for p in player_passes)
    wins = sum(d.won for d in player_duels)
    high_speed = float(np.mean(speeds >= 5.5))
    sprint = float(np.mean(speeds >= 7.0))
    return {
        "valid": True,
        "player_id": pid,
        "observed_duration_min": float(minutes),
        "physical": {
            "mean_speed_mps": float(speeds.mean()),
            "max_speed_mps": float(speeds.max()),
            "high_speed_share": high_speed,
            "sprint_share": sprint,
            "coverage_span_x_m": float(x.max() - x.min()),
            "coverage_span_y_m": float(y.max() - y.min()),
            "mean_position": [float(x.mean()), float(y.mean())],
        },
        "technical_event_rates_per_90": {
            "passes_attempted": _rate(len(player_passes), minutes),
            "passes_completed": _rate(completed, minutes),
            "shots": _rate(len(player_shots), minutes),
            "duels": _rate(len(player_duels), minutes),
            "duels_won": _rate(wins, minutes),
            "progressive_pass_distance_m": _rate(int(round(progressive)), minutes),
        },
        "evidence": {
            "pass_events": len(player_passes),
            "shot_events": len(player_shots),
            "duel_events": len(player_duels),
        },
    }


def role_suitability(passport: dict) -> dict:
    """Rank broad role families from measurable indicators; coach confirmation remains required."""
    if not passport.get("valid"):
        return {"valid": False, "reason": "invalid_passport"}
    ph = passport["physical"]; tr = passport["technical_event_rates_per_90"]
    speed = min(1.0, ph["max_speed_mps"] / 9.0)
    width = min(1.0, ph["coverage_span_y_m"] / 40.0)
    progression = min(1.0, tr["progressive_pass_distance_m"] / 500.0)
    duels = min(1.0, tr["duels_won"] / 5.0)
    shot = min(1.0, tr["shots"] / 4.0)
    return {
        "valid": True,
        "roles": {
            "winger": round(100 * (0.45*speed + 0.25*width + 0.15*shot + 0.15*duels), 1),
            "fullback": round(100 * (0.35*speed + 0.30*width + 0.20*progression + 0.15*duels), 1),
            "midfielder": round(100 * (0.15*speed + 0.20*width + 0.50*progression + 0.15*duels), 1),
            "forward": round(100 * (0.40*speed + 0.10*width + 0.40*shot + 0.10*duels), 1),
            "centerback": round(100 * (0.10*speed + 0.10*width + 0.25*progression + 0.55*duels), 1),
        },
        "warning": "Role scores are developmental hypotheses, not automatic position assignments.",
    }
