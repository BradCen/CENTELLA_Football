from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .events import EventTimeline
from .events_analytics import duel_summary, expected_assists, set_piece_summary, xg_summary
from .goalkeeping import goalkeeper_positioning
from .pitch_control import PitchControlConfig, pitch_control
from .tactical import aggregate_block_metrics, pass_network, post_loss_pressure
from .types import TrackingFrame


@dataclass(slots=True)
class AnalyticsEngine:
    """Orchestrates the full V24 analytical layer without coupling it to vision."""

    pitch_length_m: float = 105.0
    pitch_width_m: float = 68.0
    control_config: PitchControlConfig | None = None

    def analyze_team(
        self,
        frames: Sequence[TrackingFrame],
        events: EventTimeline,
        team: str,
        opponent: str | None = None,
    ) -> dict:
        opponent = opponent or ("away" if team == "home" else "home")
        latest = frames[-1] if frames else None
        report = {
            "version": "24.0.0",
            "team": team,
            "tracking": {
                "frames": len(frames),
                "first_t": float(frames[0].t) if frames else None,
                "last_t": float(frames[-1].t) if frames else None,
            },
            "tactical": {
                "pass_network": pass_network(events.passes, team),
                "block": aggregate_block_metrics(frames, team, self.pitch_length_m, self.pitch_width_m),
                "post_loss_pressure": post_loss_pressure(frames, events.possession_changes, team),
            },
            "predictive": {
                "xg": xg_summary([s for s in events.shots if s.team == team]),
                "xA": expected_assists([p for p in events.passes if p.team == team], events.shots),
            },
            "duels": duel_summary(events.duels, team),
            "set_pieces": set_piece_summary(events.set_pieces, events.shots, team),
        }
        if latest:
            report["pitch_control"] = pitch_control(latest.players, team, self.control_config)
        return report

    def analyze_goalkeeper(
        self,
        goalkeeper_id: str,
        frames: Sequence[TrackingFrame],
        shots_faced=None,
        saves=None,
    ) -> dict:
        from .goalkeeping import GoalkeeperAnalytics
        gk = GoalkeeperAnalytics(goalkeeper_id=goalkeeper_id)
        gk.saves.extend(list(saves or []))
        gk.conceded.extend(list(shots_faced or []))
        result = gk.report()
        result["positioning"] = goalkeeper_positioning(frames, goalkeeper_id, self.pitch_length_m, self.pitch_width_m)
        return result
