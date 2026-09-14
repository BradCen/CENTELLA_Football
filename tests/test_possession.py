from centella_analytics.possession import infer_possession_changes, possession_summary
from centella_analytics.types import BallSample, PlayerSample, TrackingFrame


def make_frame(t, owner_x, owner_y, other_x):
    return TrackingFrame(
        t=t,
        ball=BallSample(t=t, x=owner_x, y=owner_y, confidence=1.0),
        players=[
            PlayerSample("p1", "home", owner_x, owner_y, t, confidence=1.0),
            PlayerSample("p2", "away", other_x, owner_y, t, confidence=1.0),
        ],
    )


def test_infers_stable_owner_change():
    frames = [
        make_frame(0.0, 20, 34, 80),
        make_frame(0.2, 20, 34, 80),
        make_frame(0.4, 80, 34, 20),
        make_frame(0.6, 80, 34, 20),
    ]
    changes = infer_possession_changes(frames, min_dwell_s=0.15)
    assert changes[0][1] == "home"
    assert changes[-1][1] == "away"
    assert changes[-1][2] == "home"


def test_possession_summary_does_not_claim_time_possession():
    changes = [(1.0, "home", None, 30, 30), (4.0, "away", "home", 50, 30), (8.0, "home", "away", 40, 30)]
    report = possession_summary(changes)
    assert report["gains"]["home"] == 2
    assert report["gains"]["away"] == 1
    assert "time-of-possession" in report["definition"]
