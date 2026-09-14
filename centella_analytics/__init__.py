"""CENTELLA Football Intelligence analytics core."""

from .adapter import frames_from_native_outputs, load_events_json, load_tracking_csv
from .advanced import field_tilt, progression_rate, transition_metrics
from .coach_intelligence import coach_intelligence
from .contracts import CAPABILITY_MANIFEST, ContractIssue, assert_valid_events, assert_valid_tracking, validate_analysis_output, validate_events, validate_tracking
from .engine import AnalyticsEngine
from .event_inference import EventInferenceConfig, infer_events, infer_passes, infer_possession, infer_shots
from .events import DuelEvent, EventTimeline, PassEvent, SetPieceEvent, ShotEvent
from .expected import LogisticXGModel, ShotFeatures, fit_xg
from .extended import advanced_intelligence, ball_progression, ball_side_pressing, defensive_line, numerical_superiority, rest_defence, territorial_value, zone_occupation
from .goalkeeping import GoalkeeperAnalytics
from .performance_intelligence import performance_intelligence
from .pitch_control import PitchControlConfig, pitch_control
from .player_advanced import contribution_profile, player_evolution, player_similarity
from .player_intelligence import player_intelligence
from .player_profile import player_passport, role_suitability
from .platform import FootballIntelligencePlatform
from .possession import infer_possession_changes, possession_summary
from .quality import QualityThresholds, tracking_quality
from .reporting import build_match_report, summarize_report, to_markdown
from .serialization import load_xg_model, save_xg_model
from .tactical import aggregate_block_metrics, block_metrics, pass_network, post_loss_pressure
from .tactical_intelligence import tactical_intelligence
from .types import BallSample, PlayerSample, TrackingFrame
from .v25 import VisionIntelligencePipeline
from .workload import WorkloadProfile, compute_workload

__all__ = [
    "AnalyticsEngine", "FootballIntelligencePlatform", "VisionIntelligencePipeline", "BallSample", "PlayerSample", "TrackingFrame",
    "PassEvent", "ShotEvent", "DuelEvent", "SetPieceEvent", "EventTimeline",
    "block_metrics", "aggregate_block_metrics", "pass_network", "post_loss_pressure",
    "PitchControlConfig", "pitch_control", "field_tilt", "progression_rate", "transition_metrics",
    "advanced_intelligence", "zone_occupation", "territorial_value", "ball_progression", "numerical_superiority", "rest_defence", "defensive_line", "ball_side_pressing",
    "infer_possession_changes", "possession_summary",
    "EventInferenceConfig", "infer_events", "infer_passes", "infer_possession", "infer_shots",
    "ShotFeatures", "LogisticXGModel", "fit_xg", "save_xg_model", "load_xg_model",
    "GoalkeeperAnalytics", "WorkloadProfile", "compute_workload", "QualityThresholds", "tracking_quality",
    "load_tracking_csv", "load_events_json", "frames_from_native_outputs",
    "player_passport", "role_suitability", "player_intelligence", "player_evolution", "player_similarity", "contribution_profile",
    "tactical_intelligence", "performance_intelligence", "coach_intelligence",
    "summarize_report", "to_markdown", "build_match_report",
    "ContractIssue", "CAPABILITY_MANIFEST", "validate_tracking", "validate_events", "validate_analysis_output", "assert_valid_tracking", "assert_valid_events",
]

__version__ = "32.0.0"
