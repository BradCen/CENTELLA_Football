from centella_analytics.events import EventTimeline, PassEvent, ShotEvent
from centella_analytics.player_intelligence import player_intelligence
from centella_analytics.types import BallSample, PlayerSample, TrackingFrame


def test_player_intelligence_keeps_player_metrics_separate_and_per90():
    frames = [
        TrackingFrame(0.0, [
            PlayerSample("7", "home", 20.0, 20.0, 0.0, speed_mps=2.0),
            PlayerSample("9", "away", 70.0, 40.0, 0.0, speed_mps=1.0),
        ]),
        TrackingFrame(60.0, [
            PlayerSample("7", "home", 30.0, 25.0, 60.0, speed_mps=4.0),
            PlayerSample("9", "away", 68.0, 39.0, 60.0, speed_mps=2.0),
        ]),
    ]
    events = EventTimeline(passes=[
        PassEvent(10.0, "7", "7", "home", 20.0, 20.0, 30.0, 25.0, True, progressive_m=10.0),
    ], shots=[ShotEvent(50.0, "7", "home", 30.0, 25.0, False, False)])
    report = player_intelligence(frames, events, team="home")
    player = report["players"]["7"]
    assert report["valid"] is True
    assert player["technical_per_90"]["passes_completed"] == 90.0
    assert player["technical_per_90"]["progressive_pass_distance_m"] == 900.0
    assert player["technical_per_90"]["shots"] == 90.0
    assert player["team"] == "home"


def test_empty_tracking_does_not_fabricate_players():
    report = player_intelligence([], EventTimeline())
    assert report["valid"] is False
    assert report["players"] == {}


def test_ball_object_is_not_required_for_player_intelligence():
    frame = TrackingFrame(0.0, [PlayerSample("1", "home", 10.0, 10.0, 0.0)], BallSample(0.0, 10.0, 10.0))
    report = player_intelligence([frame], EventTimeline(), team="home")
    assert "1" in report["players"]
