from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .events import EventTimeline, PassEvent, ShotEvent
from .types import TrackingFrame


@dataclass(frozen=True, slots=True)
class EventInferenceConfig:
    """Conservative candidate-event inference from tracking + ball data.

    Outputs are candidate events and must be validated against labelled video before
    being treated as ground truth. The inference intentionally prefers precision over
    recall; downstream UI can surface gaps instead of manufacturing events.
    """
    possession_radius_m: float = 2.0
    pass_min_distance_m: float = 3.0
    pass_max_duration_s: float = 1.8
    shot_min_ball_speed_mps: float = 12.0
    shot_min_distance_from_goal_m: float = 8.0
    event_merge_window_s: float = 0.25


def _nearest(frame: TrackingFrame, team: str | None = None):
    if frame.ball is None:
        return None, float("inf")
    players = [p for p in frame.players if team is None or p.team == team]
    if not players:
        return None, float("inf")
    distances = [((p.x-frame.ball.x) ** 2 + (p.y-frame.ball.y) ** 2) ** 0.5 for p in players]
    i = int(np.argmin(distances))
    return players[i], float(distances[i])


def infer_possession(frames: Sequence[TrackingFrame], cfg: EventInferenceConfig | None = None):
    cfg = cfg or EventInferenceConfig()
    changes = []
    last_team = None
    for frame in frames:
        player, distance = _nearest(frame)
        if player is None or distance > cfg.possession_radius_m:
            continue
        if last_team is None:
            last_team = player.team
            continue
        if player.team != last_team:
            ball = frame.ball
            changes.append((float(frame.t), player.team, last_team, float(ball.x), float(ball.y)))
            last_team = player.team
    return changes


def infer_passes(frames: Sequence[TrackingFrame], cfg: EventInferenceConfig | None = None) -> list[PassEvent]:
    cfg = cfg or EventInferenceConfig()
    frames = [f for f in frames if f.ball is not None]
    events: list[PassEvent] = []
    for i, start in enumerate(frames):
        passer, start_distance = _nearest(start)
        if passer is None or start_distance > cfg.possession_radius_m:
            continue
        for end in frames[i+1:]:
            dt = end.t - start.t
            if dt <= 0:
                continue
            if dt > cfg.pass_max_duration_s:
                break
            receiver, end_distance = _nearest(end, passer.team)
            if receiver is None or receiver.player_id == passer.player_id or end_distance > cfg.possession_radius_m:
                continue
            dx = end.ball.x - start.ball.x
            dy = end.ball.y - start.ball.y
            length = float((dx*dx + dy*dy) ** 0.5)
            if length < cfg.pass_min_distance_m:
                continue
            events.append(PassEvent(
                t=float(start.t), passer_id=passer.player_id, receiver_id=receiver.player_id,
                team=passer.team, x=float(start.ball.x), y=float(start.ball.y),
                end_x=float(end.ball.x), end_y=float(end.ball.y), successful=True,
                progressive_m=max(0.0, float(dx)), timestamp_end=float(end.t),
            ))
            break
    return _dedupe_passes(events, cfg.event_merge_window_s)


def infer_shots(frames: Sequence[TrackingFrame], cfg: EventInferenceConfig | None = None,
                pitch_length_m: float = 105.0, pitch_width_m: float = 68.0) -> list[ShotEvent]:
    cfg = cfg or EventInferenceConfig()
    shots: list[ShotEvent] = []
    goal_x, goal_y = pitch_length_m, pitch_width_m / 2.0
    for frame in frames:
        ball = frame.ball
        if ball is None or ball.speed_mps < cfg.shot_min_ball_speed_mps:
            continue
        shooter, distance = _nearest(frame)
        if shooter is None or distance > cfg.possession_radius_m * 1.5:
            continue
        if ball.vx <= 2.0:
            continue
        distance_to_goal = float(((ball.x-goal_x)**2 + (ball.y-goal_y)**2) ** 0.5)
        if distance_to_goal < cfg.shot_min_distance_from_goal_m:
            continue
        defenders = [p for p in frame.players if p.team != shooter.team]
        nearest_defender = min(
            ((((p.x-ball.x)**2 + (p.y-ball.y)**2)**0.5) for p in defenders),
            default=None,
        )
        shots.append(ShotEvent(
            t=float(frame.t), player_id=shooter.player_id, team=shooter.team,
            x=float(ball.x), y=float(ball.y), on_target=False, goal=False,
            nearest_defender_m=None if nearest_defender is None else float(nearest_defender),
            velocity_mps=float(ball.speed_mps),
        ))
    return _dedupe_shots(shots, cfg.event_merge_window_s)


def infer_events(frames: Sequence[TrackingFrame], cfg: EventInferenceConfig | None = None) -> EventTimeline:
    cfg = cfg or EventInferenceConfig()
    return EventTimeline(
        passes=infer_passes(frames, cfg),
        shots=infer_shots(frames, cfg),
        possession_changes=infer_possession(frames, cfg),
    )


def _dedupe_passes(events, window):
    output = []
    for event in sorted(events, key=lambda x: x.t):
        duplicate = any(
            abs(event.t-existing.t) <= window
            and event.passer_id == existing.passer_id
            and event.receiver_id == existing.receiver_id
            for existing in output
        )
        if not duplicate:
            output.append(event)
    return output


def _dedupe_shots(events, window):
    output = []
    for event in sorted(events, key=lambda x: x.t):
        duplicate = any(abs(event.t-existing.t) <= window and event.player_id == existing.player_id for existing in output)
        if not duplicate:
            output.append(event)
    return output
