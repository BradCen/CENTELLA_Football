from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .adapter import frames_from_native_outputs
from .engine import AnalyticsEngine
from .event_inference import EventInferenceConfig
from .types import TrackingFrame


@dataclass(slots=True)
class VisionIntelligencePipeline:
    """Bridge the V21 vision output contract into the V24 intelligence layer."""

    engine: AnalyticsEngine = field(default_factory=AnalyticsEngine)
    event_config: EventInferenceConfig = field(default_factory=EventInferenceConfig)

    def from_native_outputs(self, outputs: Iterable[dict], *, team_by_gid: dict[str, str] | None = None) -> list[TrackingFrame]:
        return frames_from_native_outputs(outputs, team_by_gid=team_by_gid)

    def analyze_native_outputs(self, outputs: Iterable[dict], team: str, *, opponent: str | None = None,
                               team_by_gid: dict[str, str] | None = None) -> dict:
        frames = self.from_native_outputs(outputs, team_by_gid=team_by_gid)
        report = self.engine.analyze_tracking(frames, team, opponent, self.event_config)
        report["pipeline"] = {
            "name": "CENTELLA Vision → Football Intelligence",
            "vision_contract": "V21 fused rows",
            "analytics_version": "24.0.0",
            "frames_received": len(frames),
        }
        return report

    def analyze_frames(self, frames: Sequence[TrackingFrame], team: str, opponent: str | None = None) -> dict:
        return self.engine.analyze_tracking(frames, team, opponent, self.event_config)
