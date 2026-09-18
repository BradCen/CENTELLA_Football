from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True, slots=True)
class PassEvent:
    t: float
    passer_id: str
    receiver_id: str | None
    team: str
    x: float
    y: float
    end_x: float
    end_y: float
    successful: bool
    progressive_m: float = 0.0
    pressure: bool = False
    through_ball: bool = False
    key_pass: bool = False
    timestamp_end: float | None = None

    @property
    def length_m(self) -> float:
        return float(((self.end_x-self.x)**2 + (self.end_y-self.y)**2) ** 0.5)


@dataclass(frozen=True, slots=True)
class ShotEvent:
    t: float
    player_id: str
    team: str
    x: float
    y: float
    on_target: bool
    goal: bool
    body_part: Literal["foot", "head", "other"] = "foot"
    pressure_count: int = 0
    nearest_defender_m: float | None = None
    angle_rad: float | None = None
    velocity_mps: float | None = None
    xg: float | None = None
    xgot: float | None = None
    assisted_by: str | None = None
    set_piece_type: str | None = None


@dataclass(frozen=True, slots=True)
class DuelEvent:
    t: float
    player_id: str
    opponent_id: str | None
    team: str
    x: float
    y: float
    kind: Literal["ground", "aerial"]
    subtype: Literal["dribble", "tackle", "challenge", "other"] = "challenge"
    won: bool = False
    foul: bool = False


@dataclass(frozen=True, slots=True)
class SetPieceEvent:
    t: float
    team: str
    type: Literal["corner", "free_kick", "penalty", "throw_in"]
    x: float
    y: float
    taker_id: str | None = None
    outcome: Literal["shot", "goal", "possession", "clearance", "turnover", "foul", "unknown"] = "unknown"
    shot_id: str | None = None
    xg: float | None = None
    direct: bool = False


@dataclass(slots=True)
class EventTimeline:
    passes: list[PassEvent] = field(default_factory=list)
    shots: list[ShotEvent] = field(default_factory=list)
    duels: list[DuelEvent] = field(default_factory=list)
    set_pieces: list[SetPieceEvent] = field(default_factory=list)
    possession_changes: list[tuple[float, str, str | None, float, float]] = field(default_factory=list)

    def sorted_times(self) -> list[float]:
        values = [p.t for p in self.passes] + [s.t for s in self.shots]
        values += [d.t for d in self.duels] + [sp.t for sp in self.set_pieces]
        values += [x[0] for x in self.possession_changes]
        return sorted(set(float(t) for t in values))
