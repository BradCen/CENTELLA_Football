from centella_analytics.platform import FootballIntelligencePlatform
from centella_analytics.types import PlayerSample, TrackingFrame


def test_platform_preserves_provenance_and_final_layers():
    frames = [
        TrackingFrame(0.0, [PlayerSample("7", "home", 20.0, 30.0, 0.0), PlayerSample("9", "away", 70.0, 40.0, 0.0)]),
        TrackingFrame(1.0, [PlayerSample("7", "home", 21.0, 30.0, 1.0), PlayerSample("9", "away", 69.0, 40.0, 1.0)]),
    ]
    report = FootballIntelligencePlatform().analyze_tracking(frames, team="home")
    assert report["platform"]["version"] == "30.0.0"
    assert report["provenance"]["tracking_frames"] == 2
    assert report["provenance"]["validated_ground_truth"] is False
    assert "player_intelligence" in report["analysis"]
    assert "coach_intelligence" in report
