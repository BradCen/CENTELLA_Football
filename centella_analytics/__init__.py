"""CENTELLA Football Intelligence analytics core."""

from .adapter import frames_from_native_outputs, load_events_json, load_tracking_csv
from .advanced import field_tilt, progression_rate, transition_metrics
from .engine import AnalyticsEngine
from .event_inference import EventInferenceConfig, infer_events, infer_passes, infer_possession, infer_shots
from .events import DuelEvent, EventTimeline, PassEvent, SetPieceEvent, ShotEvent
from .expected import LogisticXGModel, ShotFeatures, fit_xg
from .goalkeeping import GoalkeeperAnalytics
from .pitch_control import PitchControlConfig, pitch_control
from .player_intelligence import player_intelligence
from .player_profile import player_passport, role_suitability
from .possession import infer_possession_changes, possession_summary
from .performance_intelligence import performance_intelligence
from .quality import QualityThresholds, tracking_quality
from .serialization import load_xg_model, save_xg_model
from .tactical import aggregate_block_metrics, block_metrics, pass_network, post_loss_pressure
from .tactical_intelligence import tactical_intelligence
from .types import BallSample, PlayerSample, TrackingFrame
from .v25 import VisionIntelligencePipeline
from .workload import WorkloadProfile, compute_workload

__all__ = [
    "AnalyticsEngine", "VisionIntelligencePipeline", "BallSample", "PlayerSample", "TrackingFrame",
    "PassEvent", "ShotEvent", "DuelEvent", "SetPieceEvent", "EventTimeline",
    "block_metrics", "aggregate_block_metrics", "pass_network", "post_loss_pressure",
    "PitchControlConfig", "pitch_control", "field_tilt", "progression_rate", "transition_metrics",
    "infer_possession_changes", "possession_summary",
    "EventInferenceConfig", "infer_events", "infer_passes", "infer_possession", "infer_shots",
    "ShotFeatures", "LogisticXGModel", "fit_xg", "save_xg_model", "load_xg_model",
    "GoalkeeperAnalytics", "WorkloadProfile", "compute_workload", "QualityThresholds", "tracking_quality",
    "load_tracking_csv", "load_events_json", "frames_from_native_outputs",
    "player_passport", "role_suitability", "player_intelligence", "tactical_intelligence",
    "performance_intelligence",
]

__version__ = "28.0.0"
