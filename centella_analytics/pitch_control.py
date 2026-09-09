from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .types import PlayerSample


@dataclass(frozen=True, slots=True)
class PitchControlConfig:
    length_m: float = 105.0
    width_m: float = 68.0
    grid_x: int = 53
    grid_y: int = 35
    max_player_speed_mps: float = 7.0
    reaction_time_s: float = 0.7
    control_sigma_s: float = 0.45
    max_control_time_s: float = 4.0


def pitch_control(
    players: Sequence[PlayerSample],
    team: str,
    config: PitchControlConfig | None = None,
) -> dict:
    """Estimate team control over every pitch cell using arrival-time influence.

    This is a model-based control surface, not a physical truth measurement. Each
    player contributes a sigmoid of arrival-time advantage; the result is normalized
    per cell, so percentages are comparable across frames. Confidence-weighted
    observations reduce the influence of uncertain tracks.
    """
    cfg = config or PitchControlConfig()
    if not players:
        return {"valid": False, "reason": "no_players"}
    xs = np.linspace(0.0, cfg.length_m, cfg.grid_x)
    ys = np.linspace(0.0, cfg.width_m, cfg.grid_y)
    X, Y = np.meshgrid(xs, ys, indexing="xy")
    flat = np.c_[X.ravel(), Y.ravel()]

    controls = {}
    for side in (team, "away" if team == "home" else "home"):
        ps = [p for p in players if p.team == side]
        if not ps:
            controls[side] = np.zeros(len(flat), dtype=float)
            continue
        score = np.zeros(len(flat), dtype=float)
        for p in ps:
            speed = min(cfg.max_player_speed_mps, max(1.0, p.speed))
            dist = np.sqrt((flat[:, 0] - p.x) ** 2 + (flat[:, 1] - p.y) ** 2)
            # Initial reaction delay plus travel time.  Existing velocity is used
            # as a directional bonus to avoid treating every player as stationary.
            vx, vy = p.vx, p.vy
            norm = max(1e-6, (vx * vx + vy * vy) ** 0.5)
            directional = ((flat[:, 0] - p.x) * vx + (flat[:, 1] - p.y) * vy) / max(1e-6, dist * norm)
            bonus = np.clip(directional, -1.0, 1.0) * 0.18
            arrival = cfg.reaction_time_s + dist / speed - bonus
            influence = 1.0 / (1.0 + np.exp(np.clip((arrival - cfg.max_control_time_s) / cfg.control_sigma_s, -30, 30)))
            score += influence * float(np.clip(p.confidence, 0.0, 1.0))
        controls[side] = score

    home_score = controls.get(team, np.zeros(len(flat)))
    other = "away" if team == "home" else "home"
    away_score = controls.get(other, np.zeros(len(flat)))
    denom = home_score + away_score + 1e-8
    share = (home_score / denom).reshape(cfg.grid_y, cfg.grid_x)
    team_percentage = float(100.0 * share.mean())
    centroid_x = float((share * X).sum() / max(1e-8, share.sum()))
    centroid_y = float((share * Y).sum() / max(1e-8, share.sum()))
    return {
        "valid": True,
        "team": team,
        "opponent": other,
        "team_control_pct": team_percentage,
        "opponent_control_pct": float(100.0 - team_percentage),
        "control_centroid": [centroid_x, centroid_y],
        "grid": share.tolist(),
        "x_axis_m": xs.tolist(),
        "y_axis_m": ys.tolist(),
        "config": {
            "length_m": cfg.length_m, "width_m": cfg.width_m,
            "grid_x": cfg.grid_x, "grid_y": cfg.grid_y,
        },
    }
