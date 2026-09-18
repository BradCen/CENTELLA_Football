from __future__ import annotations

from collections import Counter
from typing import Sequence

import numpy as np

from .events import EventTimeline
from .types import TrackingFrame


def _centroid(players):
    if not players:
        return np.array([np.nan, np.nan], dtype=float)
    return np.mean(np.asarray([[p.x, p.y] for p in players], dtype=float), axis=0)


def _pairwise_mean_distance(players) -> float:
    if len(players) < 2:
        return 0.0
    xy = np.asarray([[p.x, p.y] for p in players], dtype=float)
    d = xy[:, None, :] - xy[None, :, :]
    values = np.sqrt((d * d).sum(axis=2))[np.triu_indices(len(players), 1)]
    return float(values.mean())


def tactical_intelligence(
    frames: Sequence[TrackingFrame],
    events: EventTimeline | None = None,
    team: str = "home",
    opponent: str | None = None,
    pitch_length_m: float = 105.0,
    pitch_width_m: float = 68.0,
    interaction_radius_m: float = 12.0,
) -> dict:
    """Detect repeatable team-structure patterns from synchronized tracking.

    This layer measures interactions between players and teams. Pattern labels are
    observations, not claims about coaching intent or tactical causality.
    """
    events = events or EventTimeline()
    opponent = opponent or ("away" if team == "home" else "home")
    if not frames:
        return {"version": "27.0.0", "valid": False, "reason": "no_tracking"}

    snapshots = []
    overload = 0
    underload = 0
    numerical_samples = 0
    width_values = []
    compact_values = []
    centroid_positions = []
    phase_counts = Counter()

    for frame in frames:
        team_players = frame.team_players(team)
        opp_players = frame.team_players(opponent)
        if not team_players:
            continue
        c = _centroid(team_players)
        centroid_positions.append(c)
        width = max(p.y for p in team_players) - min(p.y for p in team_players) if team_players else 0.0
        width_values.append(float(width))
        compact_values.append(_pairwise_mean_distance(team_players))

        if frame.ball is not None:
            bx, by = frame.ball.x, frame.ball.y
            near_team = sum(((p.x - bx) ** 2 + (p.y - by) ** 2) ** 0.5 <= interaction_radius_m for p in team_players)
            near_opp = sum(((p.x - bx) ** 2 + (p.y - by) ** 2) ** 0.5 <= interaction_radius_m for p in opp_players)
            numerical_samples += 1
            if near_team > near_opp:
                overload += 1
            elif near_opp > near_team:
                underload += 1
            if near_team >= 3 and near_team > near_opp:
                phase_counts["local_overload"] += 1
            if near_opp >= 3 and near_opp > near_team:
                phase_counts["local_underload"] += 1

        span_x = max(p.x for p in team_players) - min(p.x for p in team_players)
        if span_x > pitch_length_m * 0.6 and width > pitch_width_m * 0.55:
            phase_counts["expanded_structure"] += 1
        if span_x < pitch_length_m * 0.35 and width < pitch_width_m * 0.30:
            phase_counts["compressed_structure"] += 1

        avg_speed = float(np.mean([p.speed for p in team_players]))
        if avg_speed >= 4.0:
            phase_counts["high_mobility"] += 1
        elif avg_speed <= 1.0:
            phase_counts["settled_block"] += 1

        snapshots.append(frame)

    if not snapshots:
        return {"version": "27.0.0", "valid": False, "reason": "no_team_tracking"}

    # Link possession-loss observations to the following local pressure window.
    pressure_windows = []
    loss_times = [float(item[0]) for item in events.possession_changes if len(item) >= 3 and item[2] == team]
    for loss_t in loss_times:
        window = [f for f in snapshots if loss_t <= f.t <= loss_t + 5.0]
        if window:
            pressure_windows.append(float(np.mean([
                sum(
                    ((p.x - (f.ball.x if f.ball else p.x)) ** 2 + (p.y - (f.ball.y if f.ball else p.y)) ** 2) ** 0.5 <= interaction_radius_m
                    for p in f.team_players(team)
                ) for f in window
            ])))

    return {
        "version": "27.0.0",
        "valid": True,
        "team": team,
        "observation": {"frames": len(snapshots), "first_t": float(snapshots[0].t), "last_t": float(snapshots[-1].t)},
        "structure": {
            "mean_width_m": float(np.mean(width_values)),
            "max_width_m": float(np.max(width_values)),
            "mean_pairwise_distance_m": float(np.mean(compact_values)),
            "mean_centroid": [float(np.nanmean([c[0] for c in centroid_positions])), float(np.nanmean([c[1] for c in centroid_positions]))],
        },
        "ball_side_interactions": {
            "interaction_radius_m": float(interaction_radius_m),
            "samples_with_ball": numerical_samples,
            "team_numerical_advantage_rate": float(overload / numerical_samples) if numerical_samples else 0.0,
            "team_numerical_disadvantage_rate": float(underload / numerical_samples) if numerical_samples else 0.0,
        },
        "observed_patterns": dict(phase_counts),
        "post_loss_local_pressure": {
            "windows": len(pressure_windows),
            "mean_players_within_interaction_radius": float(np.mean(pressure_windows)) if pressure_windows else 0.0,
        },
        "interpretation": "Observed structure/pattern signals; not a causal or intent model.",
    }
