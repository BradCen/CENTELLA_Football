from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from .events import EventTimeline
from .types import PlayerSample, TrackingFrame


def load_tracking_csv(path: str | Path) -> list[TrackingFrame]:
    """Load canonical tracking CSV: t, player_id, team, x, y + optional kinematics."""
    frames: dict[float, TrackingFrame] = {}
    with Path(path).open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            t = float(row["t"])
            f = frames.setdefault(t, TrackingFrame(t=t))
            f.players.append(PlayerSample(
                player_id=str(row["player_id"]), team=row["team"], x=float(row["x"]), y=float(row["y"]), t=t,
                confidence=float(row.get("confidence") or 1.0), vx=float(row.get("vx") or 0.0), vy=float(row.get("vy") or 0.0),
                speed_mps=float(row["speed_mps"]) if row.get("speed_mps") not in (None, "") else None,
                acceleration_mps2=float(row["acceleration_mps2"]) if row.get("acceleration_mps2") not in (None, "") else None,
                role=row.get("role") or None,
                is_goalkeeper=str(row.get("is_goalkeeper", "0")).lower() in {"1", "true", "yes"},
            ))
    return [frames[t] for t in sorted(frames)]


def frames_from_native_outputs(outputs: Iterable[dict], team_by_gid: dict[str, str] | None = None) -> list[TrackingFrame]:
    """Bridge the existing multicamera V21 fused rows (`t`, `gid`, `xy`) into V24."""
    grouped: dict[float, TrackingFrame] = {}
    team_by_gid = team_by_gid or {}
    for row in outputs:
        if "t" not in row or "gid" not in row or "xy" not in row:
            continue
        xy = row["xy"]
        if len(xy) < 2:
            continue
        t = float(row["t"]); gid = str(row["gid"])
        f = grouped.setdefault(t, TrackingFrame(t=t))
        f.players.append(PlayerSample(
            player_id=gid,
            team=team_by_gid.get(gid, row.get("team", "unknown")),
            x=float(xy[0]), y=float(xy[1]), t=t,
            confidence=float(row.get("confidence", 1.0)),
            speed_mps=float(row["speed_mps"]) if row.get("speed_mps") is not None else None,
            acceleration_mps2=float(row["acceleration_mps2"]) if row.get("acceleration_mps2") is not None else None,
            role=row.get("role") or None,
            is_goalkeeper=bool(row.get("is_goalkeeper", False)),
        ))
    return [grouped[t] for t in sorted(grouped)]


def load_events_json(path: str | Path) -> EventTimeline:
    """Load event dictionaries produced by manual annotation or a vision adapter."""
    from .events import DuelEvent, PassEvent, SetPieceEvent, ShotEvent
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return EventTimeline(
        passes=[PassEvent(**x) for x in data.get("passes", [])],
        shots=[ShotEvent(**x) for x in data.get("shots", [])],
        duels=[DuelEvent(**x) for x in data.get("duels", [])],
        set_pieces=[SetPieceEvent(**x) for x in data.get("set_pieces", [])],
        possession_changes=[tuple(x) for x in data.get("possession_changes", [])],
    )
