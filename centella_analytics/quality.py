from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .types import TrackingFrame


@dataclass(frozen=True, slots=True)
class QualityThresholds:
    min_player_confidence: float = 0.55
    max_frame_gap_s: float = 0.35
    max_speed_mps: float = 12.0


def tracking_quality(frames: Sequence[TrackingFrame], thresholds: QualityThresholds | None = None) -> dict:
    """Score observability without fabricating missing samples."""
    cfg = thresholds or QualityThresholds()
    if not frames:
        return {"valid": False, "reason": "no_frames"}
    times = np.asarray([f.t for f in frames], dtype=float)
    gaps = np.diff(times)
    players = [p for f in frames for p in f.players]
    if players:
        conf = np.asarray([p.confidence for p in players], dtype=float)
        speed = np.asarray([p.speed for p in players], dtype=float)
        conf_rate = float(np.mean(conf >= cfg.min_player_confidence))
        speed_bad = int(np.sum(speed > cfg.max_speed_mps))
    else:
        conf_rate, speed_bad = 0.0, 0
    frame_rate_ok = float(np.mean(gaps <= cfg.max_frame_gap_s)) if len(gaps) else 1.0
    return {
        "valid": True,
        "frames": len(frames),
        "duration_s": float(times[-1] - times[0]) if len(times) > 1 else 0.0,
        "frame_gap_p95_s": float(np.percentile(gaps, 95)) if len(gaps) else 0.0,
        "temporal_continuity_rate": frame_rate_ok,
        "player_confidence_rate": conf_rate,
        "invalid_speed_samples": speed_bad,
        "overall_score": float(0.5 * frame_rate_ok + 0.5 * conf_rate),
    }
