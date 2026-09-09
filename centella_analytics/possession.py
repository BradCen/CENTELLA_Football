from __future__ import annotations

from collections import defaultdict
from typing import Sequence

import numpy as np

from .types import TrackingFrame


def infer_possession_changes(
    frames: Sequence[TrackingFrame],
    *,
    max_ball_owner_distance_m: float = 2.6,
    min_player_confidence: float = 0.45,
    min_dwell_s: float = 0.20,
) -> list[tuple[float, str, str | None, float, float]]:
    """Infer possession-owner changes from tracked players + ball.

    The output uses the canonical `(t, new_team, previous_team, ball_x, ball_y)`
    tuple expected by the tactical transition modules. A change is emitted only
    after a candidate owner remains closest for `min_dwell_s`; this suppresses
    one-frame identity noise. The function returns an empty list when no ball
    observations exist instead of inventing possession.
    """
    owner_rows: list[tuple[float, str | None, str | None, float, float]] = []
    pending_owner: str | None = None
    pending_since: float | None = None
    committed_owner: str | None = None

    for frame in sorted(frames, key=lambda f: f.t):
        ball = frame.ball
        if ball is None or ball.confidence < min_player_confidence:
            continue
        candidates = [p for p in frame.players if p.confidence >= min_player_confidence]
        if not candidates:
            continue
        nearest = min(candidates, key=lambda p: float(np.hypot(p.x - ball.x, p.y - ball.y)))
        distance = float(np.hypot(nearest.x - ball.x, nearest.y - ball.y))
        candidate_owner = nearest.player_id if distance <= max_ball_owner_distance_m else None
        candidate_team = nearest.team if candidate_owner is not None else None

        if candidate_team == committed_owner:
            pending_owner = None
            pending_since = None
            continue

        if candidate_team != pending_owner:
            pending_owner = candidate_team
            pending_since = frame.t
            continue

        if pending_since is None or frame.t - pending_since < min_dwell_s:
            continue

        previous = committed_owner
        committed_owner = pending_owner
        pending_owner = None
        pending_since = None
        owner_rows.append((float(frame.t), committed_owner, previous, float(ball.x), float(ball.y)))

    return owner_rows


def possession_summary(changes: Sequence[tuple[float, str, str | None, float, float]], teams=("home", "away")) -> dict:
    """Summarize explicit/inferred possession changes without forcing percentages."""
    gains = defaultdict(int)
    losses = defaultdict(int)
    for row in changes:
        if len(row) < 3:
            continue
        _, new_team, previous_team, *_ = row
        if new_team in teams:
            gains[new_team] += 1
        if previous_team in teams:
            losses[previous_team] += 1
    completed = sum(gains[t] for t in teams)
    return {
        "changes": len(changes),
        "gains": dict(gains),
        "losses": dict(losses),
        "change_based_share_pct": {
            t: float(100.0 * gains[t] / completed) if completed else None for t in teams
        },
        "definition": "share of explicitly observed/inferred possession changes, not time-of-possession",
    }
