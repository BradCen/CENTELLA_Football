from centella_analytics.events import EventTimeline
from centella_analytics.extended import (
    advanced_intelligence,
    ball_progression,
    defensive_line,
    numerical_superiority,
    rest_defence,
    territorial_value,
    zone_occupation,
)
from centella_analytics.types import BallSample, PlayerSample, TrackingFrame


def make_frames():
    frames = []
    for t, bx in [(0.0, 40.0), (1.0, 45.0), (2.0, 50.0)]:
        players = [
            PlayerSample("h1", "home", 35 + t, 30, t),
            PlayerSample("h2", "home", 42 + t, 34, t),
            PlayerSample("h3", "home", 55 + t, 50, t),
            PlayerSample("a1", "away", 65 - t, 34, t),
            PlayerSample("a2", "away", 70 - t, 20, t),
            PlayerSample("a3", "away", 75 - t, 50, t),
        ]
        ball = BallSample(t=t, x=bx, y=34, vx=5.0)
        frames.append(TrackingFrame(t=t, players=players, ball=ball))
    return frames


def test_extended_spatial_metrics_are_valid():
    frames = make_frames()
    assert zone_occupation(frames, "home")["valid"]
    assert numerical_superiority(frames, "home")["valid"]
    assert rest_defence(frames, "home")["valid"]
    assert defensive_line(frames, "home")["valid"]
    assert territorial_value(frames, "home")["valid"]
    assert ball_progression(frames)["valid"]


def test_extended_aggregation_keeps_provenance():
    result = advanced_intelligence(frames := make_frames(), EventTimeline(), "home")
    assert result["version"] == "31.0.0"
    assert result["provenance"]["ground_truth_required"] is False
    assert result["provenance"]["learned_model"] is False
    assert result["ball_progression"]["net_distance_m"] > 0
