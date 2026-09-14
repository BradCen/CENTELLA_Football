import pytest

from centella_analytics.contracts import CAPABILITY_MANIFEST, assert_valid_tracking, validate_analysis_output
from centella_analytics.types import PlayerSample, TrackingFrame


def test_tracking_contract_rejects_duplicate_player_ids():
    frame = TrackingFrame(t=0.0, players=[
        PlayerSample("7", "home", 10.0, 10.0, 0.0),
        PlayerSample("7", "home", 11.0, 11.0, 0.0),
    ])
    with pytest.raises(ValueError):
        assert_valid_tracking([frame])


def test_capability_manifest_is_explicit_about_production_gaps():
    assert CAPABILITY_MANIFEST["vision"]["ground_truth_blind_inference"] is True
    assert CAPABILITY_MANIFEST["predictive"]["xg_production_calibrated"] is False
    assert "coach/player_UI" in CAPABILITY_MANIFEST["production_gaps"]


def test_analysis_contract_finds_missing_sections():
    issues = validate_analysis_output({"tracking": {}, "data_quality": {}})
    assert any(i.code == "missing_report_section" for i in issues)
