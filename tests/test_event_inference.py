from centella_analytics.event_inference import EventInferenceConfig, infer_events, infer_passes
from centella_analytics.types import BallSample, PlayerSample, TrackingFrame


def make_frame(t, p1, p2, ball):
    return TrackingFrame(
        t=t,
        players=[
            PlayerSample("1", "home", *p1, t),
            PlayerSample("2", "home", *p2, t),
            PlayerSample("3", "away", 80, 34, t),
        ],
        ball=ball,
    )


def test_candidate_pass_from_tracking():
    cfg = EventInferenceConfig(possession_radius_m=2.0, pass_min_distance_m=3.0)
    frames = [
        make_frame(0.0, (30, 30), (40, 30), BallSample(0.0, 30, 30, vx=5)),
        make_frame(0.6, (31, 30), (38, 30), BallSample(0.6, 38, 30, vx=12)),
        make_frame(1.0, (32, 30), (38, 30), BallSample(1.0, 38, 30)),
    ]
    events = infer_passes(frames, cfg)
    assert len(events) == 1
    assert events[0].passer_id == "1"
    assert events[0].receiver_id == "2"
    assert events[0].successful is True


def test_complete_inference_keeps_explicit_candidate_mode():
    frames = [make_frame(0.0, (30, 30), (40, 30), BallSample(0.0, 30, 30))]
    events = infer_events(frames)
    assert events.possession_changes == []
    assert isinstance(events.passes, list)
    assert isinstance(events.shots, list)
