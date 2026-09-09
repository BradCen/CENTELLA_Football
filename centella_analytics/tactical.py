from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Iterable, Sequence

import numpy as np

from .events import PassEvent
from .types import TrackingFrame


def _players(frames: Sequence[TrackingFrame], team: str) -> list[tuple[str, float, float, float]]:
    return [(p.player_id, p.x, p.y, f.t) for f in frames for p in f.players if p.team == team]


def pass_network(passes: Iterable[PassEvent], team: str | None = None) -> dict:
    """Build a directed weighted pass network; failed attempts remain measurable."""
    rows = [p for p in passes if team is None or p.team == team]
    duration = _network_duration(rows)
    attempts: dict[tuple[str, str], int] = defaultdict(int)
    completions: dict[tuple[str, str], int] = defaultdict(int)
    progressive: dict[tuple[str, str], float] = defaultdict(float)
    length_sum: dict[tuple[str, str], float] = defaultdict(float)
    key_passes: dict[str, int] = defaultdict(int)
    player_volume: dict[str, int] = defaultdict(int)
    for p in rows:
        if not p.receiver_id:
            continue
        edge = (p.passer_id, p.receiver_id)
        attempts[edge] += 1
        player_volume[p.passer_id] += 1
        if p.successful:
            completions[edge] += 1
            progressive[edge] += max(0.0, p.progressive_m)
        length_sum[edge] += p.length_m
        if p.key_pass:
            key_passes[p.passer_id] += 1
    edges = []
    for edge, attempted in sorted(attempts.items()):
        completed = completions[edge]
        edges.append({
            "passer_id": edge[0], "receiver_id": edge[1], "attempts": attempted,
            "completed": completed, "completion_rate": completed / attempted,
            "frequency_hz": completed / duration, "progressive_m": progressive[edge],
            "mean_length_m": length_sum[edge] / attempted,
        })
    players = sorted(set(player_volume) | {e["receiver_id"] for e in edges})
    degree = {pid: 0 for pid in players}; weighted_degree = {pid: 0 for pid in players}
    for e in edges:
        if e["completed"] > 0:
            for pid in (e["passer_id"], e["receiver_id"]):
                degree[pid] += 1; weighted_degree[pid] += e["completed"]
    density_den = len(players) * max(1, len(players) - 1)
    density = len([e for e in edges if e["completed"] > 0]) / density_den if density_den else 0.0
    return {
        "team": team, "players": players, "edges": edges,
        "network_density": float(density), "degree": degree,
        "weighted_degree": weighted_degree, "key_passes": dict(key_passes),
        "total_attempts": int(sum(attempts.values())), "total_completed": int(sum(completions.values())),
        "completion_rate": float(sum(completions.values()) / sum(attempts.values())) if attempts else 0.0,
        "duration_s": duration,
    }


def _network_duration(passes: Sequence[PassEvent]) -> float:
    values = [p.t for p in passes]
    return max(1.0, max(values) - min(values)) if len(values) >= 2 else 1.0


def _line_groups(players) -> tuple[list, list, list]:
    outfield = [p for p in players if not p.is_goalkeeper] or list(players)
    xs = np.asarray([p.x for p in outfield], dtype=float)
    q1, q2 = np.quantile(xs, [0.34, 0.67]) if len(xs) >= 3 else (np.median(xs), np.median(xs))
    return ([p for p in outfield if p.x <= q1], [p for p in outfield if q1 < p.x <= q2], [p for p in outfield if p.x > q2])


def block_metrics(frame: TrackingFrame, team: str, pitch_length: float = 105.0, pitch_width: float = 68.0) -> dict:
    """Measure block length, width, line heights and inter-line gaps in metres."""
    players = frame.team_players(team)
    if len(players) < 3:
        return {"valid": False, "reason": "insufficient_players"}
    backs, mids, fronts = _line_groups(players)
    def centroid(group):
        return np.mean([(p.x, p.y) for p in group], axis=0) if group else np.array([np.nan, np.nan])
    def spread_y(group):
        ys = [p.y for p in group]
        return float(max(ys) - min(ys)) if len(ys) >= 2 else 0.0
    bx = [p.x for p in backs] or [p.x for p in players]; fx = [p.x for p in fronts] or [p.x for p in players]
    all_y = [p.y for p in players]
    bc, mc, fc = centroid(backs), centroid(mids), centroid(fronts)
    return {
        "valid": True, "t": float(frame.t), "block_length_m": float(max(fx) - min(bx)),
        "team_width_m": float(max(all_y) - min(all_y)), "defensive_line_height_m": float(np.mean(bx)),
        "attacking_line_height_m": float(np.mean(fx)), "back_line_width_m": spread_y(backs),
        "midfield_line_width_m": spread_y(mids), "front_line_width_m": spread_y(fronts),
        "def_mid_gap_m": abs(float(bc[0] - mc[0])) if np.isfinite(mc[0]) else float("nan"),
        "mid_attack_gap_m": abs(float(mc[0] - fc[0])) if np.isfinite(mc[0]) else float("nan"),
        "stretch_index": float((max(fx) - min(bx)) / max(1.0, pitch_length)),
        "width_index": float((max(all_y) - min(all_y)) / max(1.0, pitch_width)),
    }


def aggregate_block_metrics(frames: Sequence[TrackingFrame], team: str, pitch_length=105.0, pitch_width=68.0) -> dict:
    rows = [r for r in (block_metrics(f, team, pitch_length, pitch_width) for f in frames) if r.get("valid")]
    if not rows:
        return {"valid": False, "samples": 0}
    numeric = [k for k in rows[0] if k not in {"valid", "t"}]
    return {"valid": True, "samples": len(rows), **{k: float(np.nanmedian([r[k] for r in rows])) for k in numeric}}


def post_loss_pressure(frames: Sequence[TrackingFrame], possession_changes, team: str, window_s: float = 5.0, pressure_radius_m: float = 8.0) -> dict:
    """Measure time-to-pressure and time-to-regain after explicit possession losses."""
    losses = [c for c in possession_changes if len(c) >= 5 and c[2] == team]
    if not losses:
        return {"valid": False, "losses": 0}
    rows = []
    for t0, new_team, _, bx, by in losses:
        pressure_t = regain_t = None; nearest_initial = float("inf")
        for f in frames:
            dt = f.t - t0
            if dt < 0 or dt > window_s: continue
            mates = f.team_players(team)
            if mates:
                nearest = min(np.hypot(p.x-bx, p.y-by) for p in mates)
                if dt <= 0.25: nearest_initial = nearest
                if pressure_t is None and nearest <= pressure_radius_m: pressure_t = max(0.0, dt)
        for c in possession_changes:
            if c[0] >= t0 and c[0] <= t0 + window_s and c[1] == team:
                regain_t = c[0] - t0; break
        rows.append({"t": float(t0), "opponent_team": new_team, "time_to_pressure_s": pressure_t,
                     "time_to_regain_s": regain_t,
                     "nearest_player_at_loss_m": nearest_initial if np.isfinite(nearest_initial) else None})
    pressure_values = [r["time_to_pressure_s"] for r in rows if r["time_to_pressure_s"] is not None]
    regain_values = [r["time_to_regain_s"] for r in rows if r["time_to_regain_s"] is not None]
    return {"valid": True, "losses": len(rows), "pressures_5s": len(pressure_values), "regains_5s": len(regain_values),
            "median_time_to_pressure_s": float(median(pressure_values)) if pressure_values else None,
            "median_time_to_regain_s": float(median(regain_values)) if regain_values else None, "events": rows}
