from centella_analytics.events import EventTimeline
from centella_analytics.tactical_intelligence import tactical_intelligence
from centella_analytics.types import BallSample, PlayerSample, TrackingFrame


def test_tactical_intelligence_detects_local_numerical_advantage():
    frames = [
        TrackingFrame(0.0, [
            PlayerSample("h1", "home", 20.0, 30.0, 0.0),
            PlayerSample("h2", "home", 25.0, 34.0, 0.0),
            PlayerSample("h3", "home", 28.0, 26.0, 0.0),
            PlayerSample("a1", "away", 45.0, 45.0, 0.0),
            PlayerSample("a2", "away", 60.0, 50.0, 0.0),
        ], BallSample(0.0, 24.0, 30.0)),
        TrackingFrame(1.0, [
            PlayerSample("h1", "home", 21.0, 30.0, 1.0),
            PlayerSample("h2", "home", 26.0, 34.0, 1.0),
            PlayerSample("h3", "home", 29.0, 26.0, 1.0),
            PlayerSample("a1", "away", 45.0, 45.0, 1.0),
            PlayerSample("a2", "away", 60.0, 50.0, 1.0),
        ], BallSample(1.0, 25.0, 30.0)),
    ]
    report = tactical_intelligence(frames, EventTimeline(), team="home")
    assert report["valid"] is True
    assert report["ball_side_interactions"]["team_numerical_advantage_rate"] == 1.0
    assert report["observed_patterns"]["local_overload"] == 2


def test_tactical_intelligence_is_non_fabricating_on_empty_input():
    report = tactical_intelligence([], EventTimeline(), team="home")
    assert report["valid"] is False
    assert report["reason"] == "no_tracking"
