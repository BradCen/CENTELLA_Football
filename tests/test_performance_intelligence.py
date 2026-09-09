from centella_analytics.performance_intelligence import performance_intelligence
from centella_analytics.types import PlayerSample, TrackingFrame


def test_performance_intelligence_respects_elapsed_time_and_thresholds():
    frames = [
        TrackingFrame(0.0, [PlayerSample("7", "home", 0.0, 0.0, 0.0, speed_mps=8.0, acceleration_mps2=3.0)]),
        TrackingFrame(10.0, [PlayerSample("7", "home", 80.0, 0.0, 10.0, speed_mps=8.0, acceleration_mps2=-3.0)]),
    ]
    report = performance_intelligence(frames, team="home")
    load = report["players"]["7"]["external_load"]
    assert report["valid"] is True
    assert load["estimated_distance_m"] == 80.0
    assert load["high_speed_distance_m"] == 80.0
    assert load["sprint_distance_m"] == 80.0
    assert load["acceleration_events"] == 1
    assert load["deceleration_events"] == 1


def test_performance_intelligence_does_not_create_single_sample_load():
    frames = [TrackingFrame(0.0, [PlayerSample("7", "home", 0.0, 0.0, 0.0, speed_mps=8.0)])]
    report = performance_intelligence(frames, team="home")
    assert report["valid"] is False
    assert report["players"] == {}
