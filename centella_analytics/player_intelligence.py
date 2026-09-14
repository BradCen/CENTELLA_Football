from __future__ import annotations

from collections import defaultdict
from math import log2
from typing import Sequence

import numpy as np

from .events import DuelEvent, EventTimeline, PassEvent, ShotEvent
from .types import PlayerSample, TrackingFrame


def _per90(value: float, minutes: float) -> float:
    return float(90.0 * value / minutes) if minutes > 0 else 0.0


def _safe_entropy(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    counts = np.asarray(values, dtype=float)
    counts = counts[counts > 0]
    if counts.size == 0:
        return 0.0
    probs = counts / counts.sum()
    return float(-(probs * np.log2(probs)).sum())


def _player_samples(frames: Sequence[TrackingFrame]) -> dict[str, list[PlayerSample]]:
    grouped: dict[str, list[PlayerSample]] = defaultdict(list)
    for frame in frames:
        for player in frame.players:
            grouped[str(player.player_id)].append(player)
    for values in grouped.values():
        values.sort(key=lambda p: p.t)
    return grouped


def player_intelligence(
    frames: Sequence[TrackingFrame],
    events: EventTimeline | None = None,
    team: str | None = None,
    pitch_length_m: float = 105.0,
    pitch_width_m: float = 68.0,
) -> dict:
    """Build V26 player intelligence from observed tracking and candidate/validated events.

    Metrics are evidence summaries. They do not infer hidden intent, talent, or medical
    state. Event-derived values inherit the provenance of the supplied EventTimeline.
    """
    events = events or EventTimeline()
    grouped = _player_samples(frames)
    if team is not None:
        grouped = {pid: samples for pid, samples in grouped.items() if samples and samples[0].team == team}

    if not grouped:
        return {
            "version": "26.0.0",
            "valid": False,
            "reason": "no_player_tracking",
            "event_provenance": "candidate_or_supplied_timeline",
            "players": {},
        }

    first_t = min(samples[0].t for samples in grouped.values())
    last_t = max(samples[-1].t for samples in grouped.values())
    match_minutes = max(1e-9, (last_t - first_t) / 60.0)
    passes_by_player: dict[str, list[PassEvent]] = defaultdict(list)
    receipts_by_player: dict[str, list[PassEvent]] = defaultdict(list)
    shots_by_player: dict[str, list[ShotEvent]] = defaultdict(list)
    duels_by_player: dict[str, list[DuelEvent]] = defaultdict(list)

    for event in events.passes:
        passes_by_player[event.passer_id].append(event)
        if event.receiver_id:
            receipts_by_player[event.receiver_id].append(event)
    for event in events.shots:
        shots_by_player[event.player_id].append(event)
    for event in events.duels:
        duels_by_player[event.player_id].append(event)

    reports: dict[str, dict] = {}
    for pid, samples in sorted(grouped.items()):
        speeds = np.asarray([p.speed for p in samples], dtype=float)
        xs = np.asarray([p.x for p in samples], dtype=float)
        ys = np.asarray([p.y for p in samples], dtype=float)
        confidences = np.asarray([p.confidence for p in samples], dtype=float)
        player_minutes = max(1e-9, (samples[-1].t - samples[0].t) / 60.0)
        player_passes = passes_by_player[pid]
        receipts = receipts_by_player[pid]
        shots = shots_by_player[pid]
        duels = duels_by_player[pid]
        completed = sum(bool(p.successful) for p in player_passes)
        progressive = sum(max(0.0, float(p.progressive_m)) for p in player_passes)
        key_passes = sum(bool(p.key_pass) for p in player_passes)
        through_balls = sum(bool(p.through_ball) for p in player_passes)
        duel_wins = sum(bool(d.won) for d in duels)
        occupied_y_bins = np.histogram(ys, bins=8, range=(0.0, pitch_width_m))[0].tolist()
        y_entropy = _safe_entropy(occupied_y_bins)
        occupied_x_bins = np.histogram(xs, bins=12, range=(0.0, pitch_length_m))[0].tolist()
        x_entropy = _safe_entropy(occupied_x_bins)
        valid_conf = float(np.clip(confidences.mean(), 0.0, 1.0))
        event_count = len(player_passes) + len(receipts) + len(shots) + len(duels)
        participation = event_count / max(1.0, len(samples))

        reports[pid] = {
            "team": samples[0].team,
            "role_observed": samples[0].role,
            "goalkeeper": bool(samples[0].is_goalkeeper),
            "observation": {
                "duration_min": float(player_minutes),
                "samples": len(samples),
                "mean_confidence": valid_conf,
                "tracking_coverage": float(player_minutes / match_minutes) if match_minutes else 0.0,
            },
            "physical": {
                "mean_speed_mps": float(speeds.mean()),
                "max_speed_mps": float(speeds.max()),
                "high_speed_share": float(np.mean(speeds >= 5.5)),
                "sprint_share": float(np.mean(speeds >= 7.0)),
                "mean_acceleration_mps2": float(np.mean([p.acceleration_mps2 or 0.0 for p in samples])),
                "position_span_m": {"x": float(xs.max() - xs.min()), "y": float(ys.max() - ys.min())},
            },
            "spatial": {
                "mean_position": [float(xs.mean()), float(ys.mean())],
                "mean_position_normalized": [float(xs.mean() / pitch_length_m), float(ys.mean() / pitch_width_m)],
                "longitudinal_entropy": x_entropy,
                "lateral_entropy": y_entropy,
            },
            "technical_per_90": {
                "passes_attempted": _per90(len(player_passes), player_minutes),
                "passes_completed": _per90(completed, player_minutes),
                "pass_completion_rate": float(completed / len(player_passes)) if player_passes else 0.0,
                "progressive_pass_distance_m": _per90(progressive, player_minutes),
                "key_passes": _per90(key_passes, player_minutes),
                "through_balls": _per90(through_balls, player_minutes),
                "received_passes": _per90(len(receipts), player_minutes),
                "shots": _per90(len(shots), player_minutes),
                "duels": _per90(len(duels), player_minutes),
                "duels_won": _per90(duel_wins, player_minutes),
            },
            "involvement": {
                "observed_events": event_count,
                "events_per_tracking_sample": float(participation),
                "on_ball_event_mix": {
                    "passes": len(player_passes),
                    "receipts": len(receipts),
                    "shots": len(shots),
                    "duels": len(duels),
                },
            },
        }

    return {
        "version": "26.0.0",
        "valid": True,
        "team": team,
        "pitch": {"length_m": float(pitch_length_m), "width_m": float(pitch_width_m)},
        "observation_window": {"first_t": float(first_t), "last_t": float(last_t), "duration_min": float(match_minutes)},
        "event_provenance": {
            "passes": len(events.passes),
            "shots": len(events.shots),
            "duels": len(events.duels),
            "possession_changes": len(events.possession_changes),
            "ground_truth_validated": False,
        },
        "players": reports,
    }
