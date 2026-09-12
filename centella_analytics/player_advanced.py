from __future__ import annotations

from typing import Sequence
import numpy as np

from .types import TrackingFrame


def player_evolution(frames: Sequence[TrackingFrame], player_id: str, events=(), windows: int = 4) -> dict:
    """Chronological change profile for one observed player."""
    samples = [p for f in frames for p in f.players if p.player_id == player_id]
    if len(samples) < max(8, windows * 2):
        return {"valid": False, "reason": "insufficient_player_samples", "player_id": player_id}
    samples.sort(key=lambda p: p.t)
    chunks = np.array_split(np.asarray(samples, dtype=object), windows)
    snapshots = []
    for i, chunk in enumerate(chunks):
        vals = list(chunk)
        if len(vals) < 2:
            continue
        t0, t1 = vals[0].t, vals[-1].t
        mins = max(1e-6, (t1 - t0) / 60.0)
        speeds = np.asarray([p.speed for p in vals], float)
        passes = [e for e in events if getattr(e, "passer_id", None) == player_id and t0 <= e.t <= t1]
        shots = [e for e in events if getattr(e, "player_id", None) == player_id and t0 <= e.t <= t1]
        snapshots.append({
            "window": i, "start_t": float(t0), "end_t": float(t1), "samples": len(vals),
            "mean_speed_mps": float(speeds.mean()), "max_speed_mps": float(speeds.max()),
            "mean_x_m": float(np.mean([p.x for p in vals])), "mean_y_m": float(np.mean([p.y for p in vals])),
            "sprint_share": float(np.mean(speeds >= 7.0)),
            "passes_per_90": float(90.0 * len(passes) / mins),
            "shots_per_90": float(90.0 * len(shots) / mins),
        })
    first, last = snapshots[0], snapshots[-1]
    keys = ("mean_speed_mps", "max_speed_mps", "mean_x_m", "mean_y_m", "sprint_share", "passes_per_90", "shots_per_90")
    return {"valid": True, "player_id": player_id, "windows": snapshots, "first_to_last_delta": {k: float(last[k] - first[k]) for k in keys}}


def player_similarity(passports: dict[str, dict], player_id: str | None = None, top_k: int = 5) -> dict:
    """Compare player passports using normalized observed physical/technical features."""
    if len(passports) < 2:
        return {"valid": False, "reason": "need_at_least_two_passports"}
    features = (
        ("physical", "mean_speed_mps"), ("physical", "max_speed_mps"),
        ("physical", "high_speed_share"), ("physical", "sprint_share"),
        ("physical", "coverage_span_x_m"), ("physical", "coverage_span_y_m"),
        ("technical_event_rates_per_90", "passes_attempted"),
        ("technical_event_rates_per_90", "progressive_pass_distance_m"),
        ("technical_event_rates_per_90", "shots"), ("technical_event_rates_per_90", "duels_won"),
    )
    ids = list(passports)
    X = np.asarray([[float(passports[pid].get(s, {}).get(k, 0.0)) for s, k in features] for pid in ids], float)
    mu, sig = X.mean(0), X.std(0); sig[sig < 1e-8] = 1.0
    Z = (X - mu) / sig
    def nearest(i):
        d = np.linalg.norm(Z - Z[i], axis=1)
        order = np.argsort(d)
        return [{"player_id": ids[j], "distance": float(d[j]), "similarity_pct": float(100.0*np.exp(-d[j]))} for j in order if j != i][:top_k]
    if player_id is None:
        groups = {pid: nearest(i) for i, pid in enumerate(ids)}
    elif player_id in passports:
        groups = {player_id: nearest(ids.index(player_id))}
    else:
        return {"valid": False, "reason": "unknown_player_id", "player_id": player_id}
    return {"valid": True, "reference_player_id": player_id, "players": groups, "features": [f"{s}.{k}" for s, k in features]}


def contribution_profile(frames: Sequence[TrackingFrame], player_id: str, events=(), team: str | None = None, radius_m: float = 12.0) -> dict:
    """Separate observable on-ball activity from off-ball spatial/physical signals."""
    samples = [p for f in frames for p in f.players if p.player_id == player_id]
    if not samples:
        return {"valid": False, "reason": "no_player_samples", "player_id": player_id}
    team = team or samples[0].team
    passes = [e for e in events if getattr(e, "passer_id", None) == player_id]
    receipts = [e for e in events if getattr(e, "receiver_id", None) == player_id]
    shots = [e for e in events if getattr(e, "player_id", None) == player_id]
    duels = [e for e in events if getattr(e, "player_id", None) == player_id]
    near_ball, support = [], []
    for f in frames:
        p = next((x for x in f.players if x.player_id == player_id), None)
        if p is None or f.ball is None:
            continue
        near_ball.append(float(np.hypot(p.x-f.ball.x, p.y-f.ball.y)) <= radius_m)
        mates = [x for x in f.players if x.team == team and x.player_id != player_id]
        support.append(sum(float(np.hypot(x.x-p.x, x.y-p.y)) <= radius_m for x in mates))
    return {
        "valid": True, "player_id": player_id, "team": team,
        "on_ball": {"passes": len(passes), "receipts": len(receipts), "shots": len(shots), "duels": len(duels), "observed_ball_proximity_rate": float(np.mean(near_ball)) if near_ball else None},
        "off_ball": {"mean_near_teammates_within_radius": float(np.mean(support)) if support else None, "spatial_observations": len(samples), "mean_x_m": float(np.mean([p.x for p in samples])), "mean_y_m": float(np.mean([p.y for p in samples])), "movement_span_x_m": float(max(p.x for p in samples)-min(p.x for p in samples)), "movement_span_y_m": float(max(p.y for p in samples)-min(p.y for p in samples))},
        "provenance": "observed tracking/event contribution proxies; not causal player-value attribution",
    }
