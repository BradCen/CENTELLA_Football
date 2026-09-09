"""CENTELLA Football Intelligence analytics core.

The package is deliberately decoupled from any detector/tracker.  Vision, wearable,
manual-event and future sensor adapters can all emit the canonical dataclasses used
here.  Metrics report both values and data-coverage so the UI never has to confuse
"not observed" with zero performance.
"""

from .engine import AnalyticsEngine
from .expected import LogisticXGModel, ShotFeatures, fit_xg
from .events import (
    DuelEvent,
    EventTimeline,
    PassEvent,
    SetPieceEvent,
    ShotEvent,
)
from .goalkeeping import GoalkeeperAnalytics
from .pitch_control import PitchControlConfig, pitch_control
from .tactical import block_metrics, pass_network, post_loss_pressure
from .types import BallSample, PlayerSample, TrackingFrame
from .workload import WorkloadProfile, compute_workload

__all__ = [
    "AnalyticsEngine", "BallSample", "PlayerSample", "TrackingFrame",
    "PassEvent", "ShotEvent", "DuelEvent", "SetPieceEvent", "EventTimeline",
    "block_metrics", "pass_network", "post_loss_pressure",
    "PitchControlConfig", "pitch_control",
    "ShotFeatures", "LogisticXGModel", "fit_xg",
    "GoalkeeperAnalytics", "WorkloadProfile", "compute_workload",
]

__version__ = "24.0.0"
