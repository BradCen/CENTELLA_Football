from __future__ import annotations

from collections import Counter, defaultdict
from typing import Sequence

import numpy as np

from .events import DuelEvent, EventTimeline, SetPieceEvent, ShotEvent
from .expected import LogisticXGModel, ShotFeatures


def shot_xg(shot: ShotEvent, model: LogisticXGModel | None = None) -> float:
    if shot.xg is not None:
        return float(np.clip(shot.xg, 0.0, 1.0))
    model = model or LogisticXGModel.heuristic()
    return model.predict_one(ShotFeatures(
        x=shot.x, y=shot.y, angle_rad=shot.angle_rad,
        pressure_count=shot.pressure_count,
        nearest_defender_m=shot.nearest_defender_m,
        body_part=shot.body_part,
        assisted=shot.assisted_by is not None,
        set_piece=shot.set_piece_type is not None,
    ))


def xg_summary(shots: Sequence[ShotEvent], model: LogisticXGModel | None = None) -> dict:
    if not shots:
        return {"shots": 0, "xg": 0.0, "goals": 0, "conversion": None}
    vals = [shot_xg(s, model) for s in shots]
    goals = sum(bool(s.goal) for s in shots)
    return {
        "shots": len(shots),
        "xg": float(sum(vals)),
        "goals": int(goals),
        "xg_per_shot": float(np.mean(vals)),
        "goals_minus_xg": float(goals - sum(vals)),
        "on_target": int(sum(bool(s.on_target) for s in shots)),
        "conversion": float(goals / len(shots)),
    }


def expected_assists(
    passes,
    shots: Sequence[ShotEvent],
    model: LogisticXGModel | None = None,
    max_gap_s: float = 15.0,
) -> dict:
    """Estimate xA as downstream shot probability × shot quality.

    An explicit receiver->shot link is preferred. When unavailable, the closest
    assisted_by marker within `max_gap_s` is used. This keeps xA auditable rather
    than crediting every forward pass near a shot.
    """
    shots_by_player = defaultdict(list)
    for s in shots:
        if s.assisted_by:
            shots_by_player[s.assisted_by].append(s)

    totals = defaultdict(float)
    details = []
    for p in passes:
        if not p.successful:
            continue
        candidates = [s for s in shots_by_player.get(p.passer_id, []) if 0 <= s.t - p.t <= max_gap_s]
        if not candidates and p.receiver_id:
            candidates = [s for s in shots if s.player_id == p.receiver_id and 0 <= s.t-p.t <= max_gap_s and p.team == s.team]
        if not candidates:
            continue
        shot = min(candidates, key=lambda s: s.t - p.t)
        probability = min(1.0, 0.5 + 0.5 * max(0.0, 1.0 - (shot.t-p.t)/max_gap_s))
        value = float(probability * shot_xg(shot, model))
        totals[p.passer_id] += value
        details.append({"t": p.t, "passer_id": p.passer_id, "shot_player_id": shot.player_id, "xA": value})
    return {"players": dict(totals), "total_xA": float(sum(totals.values())), "linked_passes": len(details), "details": details}


def duel_summary(duels: Sequence[DuelEvent], team: str | None = None) -> dict:
    rows = [d for d in duels if team is None or d.team == team]
    if not rows:
        return {"duels": 0}
    by_kind = {}
    for kind in ("ground", "aerial"):
        k = [d for d in rows if d.kind == kind]
        if k:
            by_kind[kind] = {
                "attempts": len(k),
                "won": sum(d.won for d in k),
                "win_rate": float(sum(d.won for d in k) / len(k)),
                "fouls": sum(d.foul for d in k),
            }
    return {
        "duels": len(rows),
        "won": sum(d.won for d in rows),
        "win_rate": float(sum(d.won for d in rows) / len(rows)),
        "ground_vs_aerial": by_kind,
        "dribble_attempts": sum(d.subtype == "dribble" for d in rows),
        "successful_dribbles": sum(d.subtype == "dribble" and d.won for d in rows),
        "tackle_attempts": sum(d.subtype == "tackle" for d in rows),
        "tackle_wins": sum(d.subtype == "tackle" and d.won for d in rows),
    }


def set_piece_summary(
    pieces: Sequence[SetPieceEvent],
    shots: Sequence[ShotEvent] = (),
    team: str | None = None,
) -> dict:
    rows = [p for p in pieces if team is None or p.team == team]
    if not rows:
        return {"events": 0}
    summary = {}
    for typ in ("corner", "free_kick", "penalty", "throw_in"):
        r = [p for p in rows if p.type == typ]
        if not r:
            continue
        shots_n = sum(p.outcome in {"shot", "goal"} for p in r)
        goals = sum(p.outcome == "goal" for p in r)
        xg = sum((p.xg or 0.0) for p in r)
        summary[typ] = {
            "attempts": len(r),
            "shots": shots_n,
            "goals": goals,
            "shot_rate": float(shots_n / len(r)),
            "goal_rate": float(goals / len(r)),
            "xg": float(xg),
        }
    takers = Counter(p.taker_id for p in rows if p.taker_id)
    return {"events": len(rows), "by_type": summary, "taker_volume": dict(takers)}
