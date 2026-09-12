from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from .events import EventTimeline
from .types import TrackingFrame


@dataclass(frozen=True, slots=True)
class ContractIssue:
    code: str
    message: str
    severity: str = "error"


def validate_tracking(frames: Sequence[TrackingFrame]) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    if not frames:
        return [ContractIssue("empty_tracking", "No tracking frames were supplied.")]
    previous_t = None
    for index, frame in enumerate(frames):
        if previous_t is not None and frame.t < previous_t:
            issues.append(ContractIssue("non_monotonic_time", f"Frame {index} has timestamp {frame.t} before {previous_t}."))
        previous_t = frame.t
        ids = set()
        for player in frame.players:
            pid = str(player.player_id)
            if pid in ids:
                issues.append(ContractIssue("duplicate_player", f"Duplicate player_id {pid} in frame {index}."))
            ids.add(pid)
            if not (0.0 <= float(player.confidence) <= 1.0):
                issues.append(ContractIssue("invalid_confidence", f"Player {pid} has confidence outside [0,1]."))
        if frame.ball is not None and not (0.0 <= float(frame.ball.confidence) <= 1.0):
            issues.append(ContractIssue("invalid_ball_confidence", f"Frame {index} has ball confidence outside [0,1]."))
    return issues


def validate_events(events: EventTimeline) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    previous = None
    timeline = []
    for collection_name in ("passes", "shots", "duels", "set_pieces"):
        for event in getattr(events, collection_name):
            timeline.append((float(event.t), collection_name))
    for change in events.possession_changes:
        if len(change) >= 1:
            timeline.append((float(change[0]), "possession_change"))
    for t, kind in sorted(timeline):
        if previous is not None and t < previous:
            issues.append(ContractIssue("non_monotonic_event_time", f"Event {kind} has an invalid timeline order."))
        previous = t
    return issues


def validate_analysis_output(report: Mapping) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    required = ("tracking", "data_quality", "tactical", "predictive", "player_intelligence", "performance_intelligence")
    for key in required:
        if key not in report:
            issues.append(ContractIssue("missing_report_section", f"Analysis output is missing '{key}'."))
    provenance = report.get("provenance")
    if provenance is not None and not isinstance(provenance, Mapping):
        issues.append(ContractIssue("invalid_provenance", "Provenance must be a mapping."))
    return issues


def assert_valid_tracking(frames: Sequence[TrackingFrame]) -> None:
    issues = validate_tracking(frames)
    if issues:
        raise ValueError("Invalid tracking contract: " + "; ".join(i.message for i in issues))


def assert_valid_events(events: EventTimeline) -> None:
    issues = validate_events(events)
    if issues:
        raise ValueError("Invalid event contract: " + "; ".join(i.message for i in issues))


CAPABILITY_MANIFEST = {
    "vision": {"tracking": True, "multi_camera_fusion": True, "ball_observations": True, "ground_truth_blind_inference": True},
    "events": {"candidate_possession": True, "candidate_passes": True, "candidate_shots": True, "labelled_event_truth": False},
    "tactical": {"pass_network": True, "block_geometry": True, "post_loss_response": True, "pitch_control": True, "numerical_superiority": True, "rest_defence": True, "observed_pattern_detection": True},
    "predictive": {"xg_heuristic": True, "xg_trainable": True, "xg_production_calibrated": False, "xa": True, "xgot_production_calibrated": False},
    "player": {"passport": True, "role_hypotheses": True, "evolution": True, "similarity": True, "on_off_ball_observation": True},
    "performance": {"external_load": True, "baseline_deviation": True, "medical_diagnosis": False},
    "goalkeeper": {"positioning": True, "shot_difficulty_proxy": True, "distribution": True},
    "reporting": {"json": True, "markdown": True, "provenance": True},
    "production_gaps": ["labelled_real_match_validation", "production_video_ingestion_hardening", "production_model_calibration", "coach/player_UI", "access_control_and_retention_for_deployment"],
}
