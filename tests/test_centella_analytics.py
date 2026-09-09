import math

import numpy as np

from centella_analytics.events import DuelEvent, PassEvent, SetPieceEvent, ShotEvent
from centella_analytics.events_analytics import duel_summary, expected_assists, set_piece_summary, shot_xg, xg_summary
from centella_analytics.expected import ShotFeatures, fit_xg
from centella_analytics.pitch_control import PitchControlConfig, pitch_control
from centella_analytics.tactical import block_metrics, pass_network, post_loss_pressure
from centella_analytics.types import PlayerSample, TrackingFrame
from centella_analytics.workload import WorkloadProfile, compute_workload


def frame(t, positions, team="home"):
    return TrackingFrame(t=t, players=[PlayerSample(player_id=str(i), team=team, x=x, y=y, t=t) for i, (x, y) in enumerate(positions)])


def test_pass_network_and_directional_volume():
    passes = [
        PassEvent(0, "1", "2", "home", 30, 20, 45, 25, True),
        PassEvent(5, "1", "2", "home", 31, 21, 44, 24, False),
        PassEvent(10, "2", "3", "home", 45, 25, 65, 33, True, progressive_m=12, key_pass=True),
    ]
    report = pass_network(iter(passes), "home")
    assert report["total_attempts"] == 3
    assert report["total_completed"] == 2
    assert report["edges"][0]["completion_rate"] == 0.5
    assert report["edges"][1]["progressive_m"] == 12


def test_block_structure():
    f = frame(1.0, [(20, 10), (21, 58), (40, 20), (42, 50), (62, 25), (64, 43)])
    r = block_metrics(f, "home")
    assert r["valid"]
    assert r["block_length_m"] > 0
    assert r["team_width_m"] == 48
    assert r["def_mid_gap_m"] > 0


def test_post_loss_pressure_and_regain():
    frames = [frame(10.0, [(40, 30), (50, 30), (60, 30)]), frame(11.0, [(41, 30), (51, 30), (60, 30)])]
    changes = [(10.0, "away", "home", 42.0, 30.0), (12.0, "home", "away", 44.0, 30.0)]
    r = post_loss_pressure(frames, changes, "home")
    assert r["losses"] == 1
    assert r["median_time_to_pressure_s"] == 0.0
    assert r["median_time_to_regain_s"] == 2.0


def test_pitch_control_is_bounded_and_sums_to_100():
    players = [PlayerSample("h", "home", 30, 34, 0, vx=2), PlayerSample("a", "away", 75, 34, 0)]
    r = pitch_control(players, "home", PitchControlConfig(grid_x=11, grid_y=7))
    assert r["valid"]
    assert 0 < r["team_control_pct"] < 100
    assert math.isclose(r["team_control_pct"] + r["opponent_control_pct"], 100.0, abs_tol=1e-8)


def test_xg_model_is_probabilistic_and_trainable():
    shot = ShotEvent(1, "9", "home", 88, 34, True, False, pressure_count=0)
    xg = shot_xg(shot)
    assert 0 < xg < 1
    assert xg_summary([shot])["shots"] == 1
    shots = [ShotFeatures(x=85, y=34), ShotFeatures(x=55, y=20), ShotFeatures(x=95, y=34), ShotFeatures(x=70, y=55)] * 20
    goals = [1, 0, 1, 0] * 20
    model = fit_xg(shots, goals, epochs=1000)
    pred = model.predict(shots)
    assert np.all((pred > 0) & (pred < 1))
    assert model.metadata()["standardized"] is True


def test_xa_duels_and_set_pieces():
    shot = ShotEvent(5, "9", "home", 90, 34, True, False, assisted_by="10")
    p = PassEvent(4, "10", "9", "home", 70, 34, 90, 34, True)
    assert expected_assists([p], [shot])["linked_passes"] == 1
    duels = duel_summary([DuelEvent(1, "9", "4", "home", 60, 34, "ground", won=True, subtype="dribble")], "home")
    assert duels["win_rate"] == 1
    sp = set_piece_summary([SetPieceEvent(3, "home", "corner", 0, 0, "7", "shot", xg=0.08)], team="home")
    assert sp["by_type"]["corner"]["shots"] == 1


def test_workload_baseline_flag():
    samples = [PlayerSample("1", "home", float(i), 20, i, speed_mps=5 + i * 0.1, acceleration_mps2=0.5) for i in range(10)]
    profile = WorkloadProfile("1", historical_loads=[5, 6, 5, 6, 5])
    r = compute_workload(samples, profile)
    assert r["valid"]
    assert r["distance_m"] > 0
    assert "load_flag" in r
