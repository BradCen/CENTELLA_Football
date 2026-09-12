from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .coach_intelligence import coach_intelligence
from .engine import AnalyticsEngine
from .event_inference import EventInferenceConfig
from .events import EventTimeline
from .types import TrackingFrame


@dataclass(slots=True)
class FootballIntelligencePlatform:
    """Unified entry point from synchronized tracking to coach-facing intelligence."""

    engine: AnalyticsEngine = field(default_factory=AnalyticsEngine)
    schema_version: str = "31.0.0"

    def analyze_tracking(
        self,
        frames: Sequence[TrackingFrame],
        team: str,
        opponent: str | None = None,
        config: EventInferenceConfig | None = None,
    ) -> dict:
        analysis = self.engine.analyze_tracking(frames, team=team, opponent=opponent, config=config)
        return self._finalize(analysis)

    def analyze_events(
        self,
        frames: Sequence[TrackingFrame],
        events: EventTimeline,
        team: str,
        opponent: str | None = None,
    ) -> dict:
        analysis = self.engine.analyze_team(frames, events, team=team, opponent=opponent)
        return self._finalize(analysis)

    def _finalize(self, analysis: dict) -> dict:
        insights = coach_intelligence(analysis)
        return {
            "platform": {
                "name": "CENTELLA Football Intelligence Platform",
                "version": self.schema_version,
                "layers": ["vision_contract", "event_inference", "football_analytics", "advanced_intelligence", "player_intelligence", "performance", "coach_intelligence"],
            },
            "provenance": {
                "tracking_frames": analysis.get("tracking", {}).get("frames", 0),
                "event_inference_mode": analysis.get("event_inference", {}).get("mode", "supplied_events"),
                "validated_ground_truth": analysis.get("event_inference", {}).get("validated_ground_truth", False),
                "advanced_intelligence": analysis.get("advanced_intelligence", {}).get("provenance", {}),
            },
            "analysis": analysis,
            "coach_intelligence": insights,
        }
