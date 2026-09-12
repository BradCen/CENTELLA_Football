from centella_analytics.player_advanced import contribution_profile, player_evolution, player_similarity
from centella_analytics.player_profile import player_passport
from centella_analytics.types import BallSample, PlayerSample, TrackingFrame


def _frames():
    rows = []
    for i in range(16):
        t = float(i)
        rows.append(TrackingFrame(t=t, players=[
            PlayerSample("7", "home", 20+i*0.6, 30+i*0.1, t, speed_mps=3.0+i*0.05),
            PlayerSample("8", "home", 35+i*0.4, 40-i*0.1, t, speed_mps=4.0),
            PlayerSample("9", "away", 70-i*0.2, 34, t, speed_mps=3.5),
        ], ball=BallSample(t=t, x=25+i*0.5, y=34, confidence=0.9)))
    return rows


def test_player_evolution_and_contribution():
    frames = _frames()
    evolution = player_evolution(frames, "7", windows=4)
    assert evolution["valid"]
    assert evolution["first_to_last_delta"]["mean_x_m"] > 0
    contribution = contribution_profile(frames, "7", team="home")
    assert contribution["valid"]
    assert contribution["off_ball"]["spatial_observations"] == 16


def test_player_similarity_accepts_multiple_passports():
    frames = _frames()
    p7 = player_passport([p for f in frames for p in f.players if p.player_id == "7"])
    p8 = player_passport([p for f in frames for p in f.players if p.player_id == "8"])
    result = player_similarity({"7": p7, "8": p8}, player_id="7")
    assert result["valid"]
    assert result["players"]["7"][0]["player_id"] == "8"
