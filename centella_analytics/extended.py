from __future__ import annotations

from collections import defaultdict
from typing import Sequence

import numpy as np

from .events import EventTimeline
from .types import TrackingFrame


def _side(team: str, opponent: str | None) -> str:
    return opponent or ("away" if team == "home" else "home")


def _team_positions(frame: TrackingFrame, team: str):
    return [p for p in frame.players if p.team == team and not p.is_goalkeeper]


def _zone(x: float, y: float, length: float, width: float) -> tuple[int, int]:
    ix = min(5, max(0, int(x / max(1e-9, length) * 6)))
    iy = min(4, max(0, int(y / max(1e-9, width) * 5)))
    return ix, iy


def zone_occupation(
    frames: Sequence[TrackingFrame],
    team: str,
    pitch_length_m: float = 105.0,
    pitch_width_m: float = 68.0,
) -> dict:
    """Return 6x5 occupancy shares and a per-player spatial footprint."""
    counts = np.zeros((5, 6), dtype=float)
    player_counts: dict[str, np.ndarray] = defaultdict(lambda: np.zeros((5, 6), dtype=float))
    total = 0
    for frame in frames:
        for p in _team_positions(frame, team):
            ix, iy = _zone(p.x, p.y, pitch_length_m, pitch_width_m)
            counts[iy, ix] += 1.0
            player_counts[p.player_id][iy, ix] += 1.0
            total += 1
    if total == 0:
        return {"valid": False, "reason": "no_team_observations"}
    matrix = counts / total
    return {
        "valid": True,
        "team": team,
        "grid": matrix.tolist(),
        "zone_count": int(total),
        "dominant_zone": [int(np.unravel_index(np.argmax(matrix), matrix.shape)[1]), int(np.unravel_index(np.argmax(matrix), matrix.shape)[0])],
        "player_footprints": {
            pid: (m / max(1.0, m.sum())).tolist() for pid, m in player_counts.items()
        },
        "definition": "share of observed player-position samples by pitch zone; not possession time",
    }


def territorial_value(
    frames: Sequence[TrackingFrame],
    team: str,
    pitch_length_m: float = 105.0,
    pitch_width_m: float = 68.0,
) -> dict:
    """Estimate territorial ball value from a smooth field-position prior.

    This is deliberately not labelled as learned xT/OBV. It is a transparent positional
    value signal that rewards advancement and centrality and can be compared over time.
    """
    samples = []
    previous = None
    gains = losses = 0.0
    for frame in sorted(frames, key=lambda f: f.t):
        ball = frame.ball
        if ball is None or ball.confidence <= 0:
            continue
        centrality = 1.0 - min(1.0, abs(ball.y - pitch_width_m / 2.0) / (pitch_width_m / 2.0))
        advance = np.clip(ball.x / max(1e-9, pitch_length_m), 0.0, 1.0)
        value = float(np.clip(0.65 * advance + 0.35 * centrality, 0.0, 1.0))
        samples.append(value)
        if previous is not None:
            delta = value - previous
            if delta > 0:
                gains += float(delta)
            elif delta < 0:
                losses += float(-delta)
        previous = value
    if not samples:
        return {"valid": False, "reason": "no_ball_observations"}
    return {
        "valid": True,
        "team": team,
        "mean_territorial_value": float(np.mean(samples)),
        "peak_territorial_value": float(np.max(samples)),
        "positive_value_change_sum": gains,
        "negative_value_change_sum": losses,
        "net_value_change": float(gains - losses),
        "observations": len(samples),
        "definition": "transparent position-based value prior; not trained xT/OBV",
    }


def ball_progression(
    frames: Sequence[TrackingFrame],
    pitch_length_m: float = 105.0,
) -> dict:
    """Measure observed ball advancement/deceleration without assigning event causality."""
    rows = [(f.t, f.ball.x, f.ball.y) for f in sorted(frames, key=lambda f: f.t) if f.ball is not None]
    if len(rows) < 2:
        return {"valid": False, "reason": "insufficient_ball_observations"}
    dx = np.diff([r[1] for r in rows])
    dt = np.maximum(1e-6, np.diff([r[0] for r in rows]))
    velocity = dx / dt
    forward = dx[dx > 0]
    backward = -dx[dx < 0]
    return {
        "valid": True,
        "observations": len(rows),
        "forward_distance_m": float(forward.sum()) if len(forward) else 0.0,
        "backward_distance_m": float(backward.sum()) if len(backward) else 0.0,
        "net_distance_m": float(rows[-1][1] - rows[0][1]),
        "peak_forward_ball_speed_mps": float(max(0.0, velocity.max())),
        "ball_progression_pct_of_pitch": float(100.0 * (rows[-1][1] - rows[0][1]) / max(1e-9, pitch_length_m)),
    }


def numerical_superiority(
    frames: Sequence[TrackingFrame],
    team: str,
    opponent: str | None = None,
    radius_m: float = 12.0,
) -> dict:
    """Quantify local player-number advantage around the tracked ball."""
    opponent = _side(team, opponent)
    ratios = []; advantages = []
    for frame in frames:
        if frame.ball is None:
            continue
        bx, by = frame.ball.x, frame.ball.y
        tp = _team_positions(frame, team)
        op = _team_positions(frame, opponent)
        nt = sum(float(np.hypot(p.x - bx, p.y - by) <= radius_m) for p in tp)
        no = sum(float(np.hypot(p.x - bx, p.y - by) <= radius_m) for p in op)
        ratios.append(nt / max(1, nt + no)); advantages.append(nt - no)
    if not ratios:
        return {"valid": False, "reason": "no_ball_observations"}
    return {
        "valid": True,
        "team": team,
        "opponent": opponent,
        "radius_m": float(radius_m),
        "team_advantage_rate": float(np.mean(np.asarray(advantages) > 0)),
        "team_disadvantage_rate": float(np.mean(np.asarray(advantages) < 0)),
        "mean_players_advantage": float(np.mean(advantages)),
        "median_local_team_share": float(np.median(ratios)),
        "samples": len(ratios),
    }


def rest_defence(
    frames: Sequence[TrackingFrame],
    team: str,
    opponent: str | None = None,
    pitch_length_m: float = 105.0,
) -> dict:
    """Measure how many outfield players remain behind the ball during observations."""
    opponent = _side(team, opponent)
    rows = []
    for frame in frames:
        if frame.ball is None:
            continue
        behind = [p for p in _team_positions(frame, team) if p.x < frame.ball.x]
        opp = _team_positions(frame, opponent)
        rows.append({
            "behind_ball": len(behind),
            "opponent_ahead": sum(p.x > frame.ball.x for p in opp),
            "deepest_x": min((p.x for p in behind), default=frame.ball.x),
        })
    if not rows:
        return {"valid": False, "reason": "no_ball_observations"}
    return {
        "valid": True,
        "team": team,
        "mean_players_behind_ball": float(np.mean([r["behind_ball"] for r in rows])),
        "share_with_3plus_behind": float(np.mean([r["behind_ball"] >= 3 for r in rows])),
        "mean_opponent_ahead": float(np.mean([r["opponent_ahead"] for r in rows])),
        "mean_deepest_player_x_m": float(np.mean([r["deepest_x"] for r in rows])),
        "pitch_length_m": float(pitch_length_m),
    }


def defensive_line(
    frames: Sequence[TrackingFrame],
    team: str,
    opponent: str | None = None,
) -> dict:
    """Describe the last and penultimate outfield-player longitudinal lines."""
    opponent = _side(team, opponent)
    rows = []
    for frame in frames:
        players = sorted(_team_positions(frame, team), key=lambda p: p.x)
        if len(players) < 3:
            continue
        xs = [p.x for p in players]
        rows.append({
            "last_line_x": float(xs[-3]),
            "highest_x": float(xs[-1]),
            "line_span_m": float(xs[-1] - xs[-3]),
            "opponent_highest_x": float(max((p.x for p in _team_positions(frame, opponent)), default=np.nan)),
        })
    if not rows:
        return {"valid": False, "reason": "insufficient_players"}
    return {
        "valid": True,
        "team": team,
        "median_defensive_line_x_m": float(np.median([r["last_line_x"] for r in rows])),
        "median_line_span_m": float(np.median([r["line_span_m"] for r in rows])),
        "median_highest_team_x_m": float(np.median([r["highest_x"] for r in rows])),
        "median_highest_opponent_x_m": float(np.nanmedian([r["opponent_highest_x"] for r in rows])),
        "observations": len(rows),
        "interpretation": "geometric line proxy; not an offside-law decision",
    }


def ball_side_pressing(
    frames: Sequence[TrackingFrame],
    team: str,
    radius_m: float = 8.0,
) -> dict:
    """Estimate observed defensive proximity to the ball; no pressure event labels are invented."""
    rows = []
    for frame in frames:
        if frame.ball is None:
            continue
        distances = [float(np.hypot(p.x-frame.ball.x, p.y-frame.ball.y)) for p in frame.team_players(team)]
        if distances:
            rows.append(min(distances))
    if not rows:
        return {"valid": False, "reason": "no_ball_or_team_observations"}
    a = np.asarray(rows, dtype=float)
    return {
        "valid": True,
        "team": team,
        "pressure_proximity_rate": float(np.mean(a <= radius_m)),
        "median_nearest_player_to_ball_m": float(np.median(a)),
        "p90_nearest_player_to_ball_m": float(np.percentile(a, 90)),
        "radius_m": float(radius_m),
        "definition": "geometric proximity proxy, not labelled pressure-action count",
    }


def match_timeline(events: EventTimeline) -> dict:
    """Provide a compact chronological event index for report/UI layers."""
    rows = []
    for p in events.passes:
        rows.append({"t": float(p.t), "type": "pass", "team": p.team, "player_id": p.passer_id, "receiver_id": p.receiver_id, "successful": p.successful, "progressive_m": p.progressive_m})
    for s in events.shots:
        rows.append({"t": float(s.t), "type": "shot", "team": s.team, "player_id": s.player_id, "goal": s.goal, "xg": s.xg})
    for d in events.duels:
        rows.append({"t": float(d.t), "type": "duel", "team": d.team, "player_id": d.player_id, "kind": d.kind, "won": d.won})
    for sp in events.set_pieces:
        rows.append({"t": float(sp.t), "type": "set_piece", "team": sp.team, "set_piece_type": sp.type, "taker_id": sp.taker_id, "outcome": sp.outcome})
    for c in events.possession_changes:
        if len(c) >= 3:
            rows.append({"t": float(c[0]), "type": "possession_change", "team": c[1], "previous_team": c[2], "x": c[3] if len(c) > 3 else None, "y": c[4] if len(c) > 4 else None})
    rows.sort(key=lambda x: x["t"])
    return {"events": rows, "count": len(rows)}


def advanced_intelligence(
    frames: Sequence[TrackingFrame],
    events: EventTimeline,
    team: str,
    opponent: str | None = None,
    pitch_length_m: float = 105.0,
    pitch_width_m: float = 68.0,
) -> dict:
    """One deterministic aggregation of extra tactical/physical/spatial signals."""
    opponent = _side(team, opponent)
    return {
        "version": "31.0.0",
        "valid": bool(frames),
        "team": team,
        "zone_occupation": zone_occupation(frames, team, pitch_length_m, pitch_width_m),
        "territorial_value": territorial_value(frames, team, pitch_length_m, pitch_width_m),
        "ball_progression": ball_progression(frames, pitch_length_m),
        "numerical_superiority": numerical_superiority(frames, team, opponent),
        "rest_defence": rest_defence(frames, team, opponent, pitch_length_m),
        "defensive_line": defensive_line(frames, team, opponent),
        "ball_side_pressing": ball_side_pressing(frames, team),
        "match_timeline": match_timeline(events),
        "provenance": {
            "source": "tracking + supplied/inferred events",
            "ground_truth_required": False,
            "learned_model": False,
        },
    }
