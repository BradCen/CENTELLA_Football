from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Team = Literal["home", "away", "referee", "unknown"]


@dataclass(frozen=True, slots=True)
class PlayerSample:
    """A single player observation in pitch metres.

    x is the longitudinal coordinate (0..length) and y the lateral coordinate
    (0..width).  Optional velocity/acceleration fields may come from vision,
    GNSS/UWB/IMU fusion or be derived by the adapter.
    """

    player_id: str
    team: Team
    x: float
    y: float
    t: float
    confidence: float = 1.0
    vx: float = 0.0
    vy: float = 0.0
    speed_mps: float | None = None
    acceleration_mps2: float | None = None
    role: str | None = None
    is_goalkeeper: bool = False

    @property
    def speed(self) -> float:
        if self.speed_mps is not None:
            return max(0.0, float(self.speed_mps))
        return float((self.vx * self.vx + self.vy * self.vy) ** 0.5)


@dataclass(frozen=True, slots=True)
class BallSample:
    t: float
    x: float
    y: float
    z: float = 0.0
    confidence: float = 1.0
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0

    @property
    def speed_mps(self) -> float:
        return float((self.vx**2 + self.vy**2 + self.vz**2) ** 0.5)


@dataclass(slots=True)
class TrackingFrame:
    """One synchronized frame/window of tracking state."""

    t: float
    players: list[PlayerSample] = field(default_factory=list)
    ball: BallSample | None = None

    def team_players(self, team: Team) -> list[PlayerSample]:
        return [p for p in self.players if p.team == team]

    def player_map(self) -> dict[str, PlayerSample]:
        return {p.player_id: p for p in self.players}
