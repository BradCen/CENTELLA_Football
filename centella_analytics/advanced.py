from __future__ import annotations

from typing import Sequence

import numpy as np

from .types import TrackingFrame


def field_tilt(frames: Sequence[TrackingFrame], team: str, opponent: str | None = None, pitch_length: float = 105.0) -> dict:
    """Measure territorial tilt from outfield-player observations around pitch midpoint."""
    opponent = opponent or ("away" if team == "home" else "home")
    team_x=[]; opp_x=[]
    for f in frames:
        team_x += [p.x for p in f.players if p.team == team and not p.is_goalkeeper]
        opp_x += [p.x for p in f.players if p.team == opponent and not p.is_goalkeeper]
    if not team_x or not opp_x:
        return {"valid": False, "reason": "insufficient_outfield_observations"}
    boundary = pitch_length / 2.0
    team_attacking = sum(x > boundary for x in team_x) / len(team_x)
    opponent_attacking = sum(x < boundary for x in opp_x) / len(opp_x)
    tilt = team_attacking / max(1e-9, team_attacking + opponent_attacking)
    return {
        "valid": True, "team": team, "pitch_midline_m": boundary,
        "team_attacking_half_share_pct": float(100.0 * team_attacking),
        "opponent_attacking_half_share_pct": float(100.0 * opponent_attacking),
        "field_tilt_pct": float(100.0 * tilt),
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
    """Measure explicit possession transitions and time until a subsequent regain."""
    gains = [c for c in possession_changes if len(c) >= 5 and c[1] == team]
    losses = [c for c in possession_changes if len(c) >= 5 and c[2] == team]
    regain_times=[]
    for e in losses:
        t0=e[0]
        for c in possession_changes:
            if c[0] > t0 and c[0] <= t0+regain_window_s and c[1] == team:
                regain_times.append(c[0]-t0); break
    return {
        "team": team, "possession_gains": len(gains), "possession_losses": len(losses),
        "losses_regained_within_window": len(regain_times),
        "median_time_to_regain_after_loss_s": float(np.median(regain_times)) if regain_times else None,
        "regain_window_s": regain_window_s,
    }
