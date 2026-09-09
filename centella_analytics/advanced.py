from __future__ import annotations

from typing import Sequence

import numpy as np

from .types import PlayerSample, TrackingFrame


def field_tilt(frames: Sequence[TrackingFrame], team: str, opponent: str | None = None) -> dict:
    """Approximate territorial control from player occupancy, excluding goalkeepers."""
    opponent = opponent or ("away" if team == "home" else "home")
    team_x=[]; opp_x=[]
    for f in frames:
        team_x += [p.x for p in f.players if p.team == team and not p.is_goalkeeper]
        opp_x += [p.x for p in f.players if p.team == opponent and not p.is_goalkeeper]
    if not team_x or not opp_x:
        return {"valid": False, "reason": "insufficient_outfield_observations"}
    # For a normalized, direction-aware field, territory is the share of all
    # outfield observations in the opponent's half of the pitch.
    boundary = (max(team_x + opp_x) + min(team_x + opp_x)) / 2.0
    own = sum(x >= boundary for x in team_x)
    opp = sum(x <= boundary for x in opp_x)
    return {
        "valid": True,
        "team": team,
        "team_observations_in_attacking_territory_pct": float(100.0 * own / len(team_x)),
        "opponent_observations_in_attacking_territory_pct": float(100.0 * opp / len(opp_x)),
        "sample_observations": len(team_x) + len(opp_x),
    }


def progression_rate(frames: Sequence[TrackingFrame], team: str, threshold_m: float = 5.0) -> dict:
    """Quantify forward movement between consecutive tracked samples."""
    by_player: dict[str, list[tuple[float,float]]] = {}
    for f in frames:
        for p in f.players:
            if p.team == team:
                by_player.setdefault(p.player_id, []).append((f.t, p.x))
    actions = 0; meters = 0.0
    for rows in by_player.values():
        rows.sort()
        for (_, x0), (_, x1) in zip(rows, rows[1:]):
            d = x1 - x0
            if d >= threshold_m:
                actions += 1; meters += d
    return {"team": team, "progressive_actions": actions, "progressed_m": float(meters), "threshold_m": threshold_m}


def transition_metrics(frames: Sequence[TrackingFrame], possession_changes, team: str, regain_window_s: float = 8.0) -> dict:
    """Separate transition direction from possession outcome using explicit change events."""
    gains = [c for c in possession_changes if len(c) >= 5 and c[1] == team]
    losses = [c for c in possession_changes if len(c) >= 5 and c[2] == team]
    def outcome(events, target):
        times=[]
        for e in events:
            t0=e[0]
            for c in possession_changes:
                if c[0] > t0 and c[0] <= t0+regain_window_s and c[1] == target:
                    times.append(c[0]-t0); break
        return float(np.median(times)) if times else None
    return {
        "team": team, "possession_gains": len(gains), "possession_losses": len(losses),
        "median_time_to_regain_after_loss_s": outcome(losses, team),
        "median_time_to_next_gain_after_loss_s": outcome(losses, team),
    }
