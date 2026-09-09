from __future__ import annotations

from collections import defaultdict
from typing import Sequence

import numpy as np

from .types import PlayerSample, TrackingFrame


def _dt_pairs(samples: Sequence[PlayerSample]):
    for prev, cur in zip(samples, samples[1:]):
        dt = float(cur.t - prev.t)
        if dt > 0:
            yield prev, cur, dt


def _per90(value: float, minutes: float) -> float:
    return float(90.0 * value / minutes) if minutes > 0 else 0.0


def performance_intelligence(
    frames: Sequence[TrackingFrame],
    team: str | None = None,
    high_speed_mps: float = 5.5,
    sprint_mps: float = 7.0,
    acceleration_threshold_mps2: float = 2.5,
) -> dict:
    """Estimate external-load and movement-performance signals from tracking.

    This is performance monitoring, not injury prediction or medical advice. Distances
    are estimated from observed speed and elapsed time; irregular sampling is respected.
    """
    grouped: dict[str, list[PlayerSample]] = defaultdict(list)
    for frame in frames:
        for player in frame.players:
            if team is None or player.team == team:
                grouped[player.player_id].append(player)
    for values in grouped.values():
        values.sort(key=lambda p: p.t)

    reports = {}
    for pid, samples in sorted(grouped.items()):
        if len(samples) < 2:
            continue
        duration_s = max(0.0, samples[-1].t - samples[0].t)
        minutes = duration_s / 60.0
        total_distance = 0.0
        hsr_distance = 0.0
        sprint_distance = 0.0
        high_intensity_time = 0.0
        sprint_time = 0.0
        accel_events = 0
        decel_events = 0
        peak_speed = 0.0
        was_accelerating = False
        was_decelerating = False
        for prev, cur, dt in _dt_pairs(samples):
            speed = float(cur.speed)
            total_distance += speed * dt
            if speed >= high_speed_mps:
                hsr_distance += speed * dt
                high_intensity_time += dt
            if speed >= sprint_mps:
                sprint_distance += speed * dt
                sprint_time += dt
            acc = cur.acceleration_mps2
            if acc is not None:
                is_accelerating = acc >= acceleration_threshold_mps2
                is_decelerating = acc <= -acceleration_threshold_mps2
                if is_accelerating and not was_accelerating:
                    accel_events += 1
                if is_decelerating and not was_decelerating:
                    decel_events += 1
                was_accelerating = is_accelerating
                was_decelerating = is_decelerating
            peak_speed = max(peak_speed, speed)

        reports[pid] = {
            "team": samples[0].team,
            "duration_min": float(minutes),
            "coverage_samples": len(samples),
            "peak_speed_mps": peak_speed,
            "external_load": {
                "estimated_distance_m": total_distance,
                "estimated_distance_m_per_90": _per90(total_distance, minutes),
                "high_speed_distance_m": hsr_distance,
                "high_speed_distance_m_per_90": _per90(hsr_distance, minutes),
                "sprint_distance_m": sprint_distance,
                "sprint_distance_m_per_90": _per90(sprint_distance, minutes),
                "high_intensity_time_s": high_intensity_time,
                "sprint_time_s": sprint_time,
                "acceleration_events": accel_events,
                "deceleration_events": decel_events,
            },
            "monitoring": {
                "high_speed_threshold_mps": float(high_speed_mps),
                "sprint_threshold_mps": float(sprint_mps),
                "acceleration_threshold_mps2": float(acceleration_threshold_mps2),
                "interpretation": "Observed external-load signal; not an injury or medical assessment.",
            },
        }

    return {
        "version": "28.0.0",
        "valid": bool(reports),
        "team": team,
        "players": reports,
        "aggregation": {
            "players_observed": len(reports),
            "mean_peak_speed_mps": float(np.mean([p["peak_speed_mps"] for p in reports.values()])) if reports else 0.0,
            "mean_distance_m_per_90": float(np.mean([p["external_load"]["estimated_distance_m_per_90"] for p in reports.values()])) if reports else 0.0,
        },
    }
