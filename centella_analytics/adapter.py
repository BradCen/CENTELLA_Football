from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from .events import EventTimeline
from .types import BallSample, PlayerSample, TrackingFrame


def load_tracking_csv(path: str | Path) -> list[TrackingFrame]:
    """Load the canonical tracking CSV schema.

    Required columns: t, player_id, team, x, y. Optional columns are accepted for
    velocity, acceleration, confidence, role and goalkeeper flag.
    """
    frames: dict[float, TrackingFrame] = {}
    with Path(path).open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            t = float(row["t"])
            f = frames.setdefault(t, TrackingFrame(t=t))
            f.players.append(PlayerSample(
                player_id=str(row["player_id"]), team=row["team"],
                x=float(row["x"]), y=float(row["y"]), t=t,
                confidence=float(row.get("confidence") or 1.0),
                vx=float(row.get("vx") or 0.0), vy=float(row.get("vy") or 0.0),
                speed_mps=float(row["speed_mps"]) if row.get("speed_mps") not in (None, "") else None,
                acceleration_mps2=float(row["acceleration_mps2"]) if row.get("acceleration_mps2") not in (None, "") else None,
                role=row.get("role") or None,
                is_goalkeeper=str(row.get("is_goalkeeper", "0")).lower() in {"1", "true", "yes"},
            ))
    return [frames[t] for t in sorted(frames)]


def load_events_json(path: str | Path) -> EventTimeline:
    """Load event dictionaries produced by manual annotation or a vision adapter."""
    from dataclasses import asdict
    from .events import DuelEvent, PassEvent, SetPieceEvent, ShotEvent
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return EventTimeline(
        passes=[PassEvent(**x) for x in data.get("passes", [])],
        shots=[ShotEvent(**x) for x in data.get("shots", [])],
        duels=[DuelEvent(**x) for x in data.get("duels", [])],
        set_pieces=[SetPieceEvent(**x) for x in data.get("set_pieces", [])],
        possession_changes=[tuple(x) for x in data.get("possession_changes", [])],
    )
