from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .adapter import frames_from_native_outputs
from .event_inference import EventInferenceConfig
from .platform import FootballIntelligencePlatform
from .types import TrackingFrame


@dataclass(slots=True)
class VisionIntelligencePipeline:
    """Bridge the V21 vision output contract into the V31 intelligence platform."""

    platform: FootballIntelligencePlatform = field(default_factory=FootballIntelligencePlatform)
    event_config: EventInferenceConfig = field(default_factory=EventInferenceConfig)

    def from_native_outputs(self, outputs: Iterable[dict], *, team_by_gid: dict[str, str] | None = None) -> list[TrackingFrame]:
        return frames_from_native_outputs(outputs, team_by_gid=team_by_gid)

    def analyze_native_outputs(self, outputs: Iterable[dict], team: str, *, opponent: str | None = None,
                               team_by_gid: dict[str, str] | None = None) -> dict:
        frames = self.from_native_outputs(outputs, team_by_gid=team_by_gid)
        result = self.platform.analyze_tracking(frames, team=team, opponent=opponent, config=self.event_config)
        result["pipeline"] = {
            "name": "CENTELLA Vision → Football Intelligence",
            "vision_contract": "V21/V62 fused rows",
            "analytics_version": "31.0.0",
            "frames_received": len(frames),
        }
        return result

    def analyze_frames(self, frames: Sequence[TrackingFrame], team: str, opponent: str | None = None) -> dict:
        return self.platform.analyze_tracking(frames, team, opponent, self.event_config)
