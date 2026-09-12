from centella_analytics.v25 import VisionIntelligencePipeline


def test_native_output_bridge_keeps_players_and_pipeline_contract():
    pipeline = VisionIntelligencePipeline()
    frames = pipeline.from_native_outputs([
        {"t": 1.0, "gid": 7, "xy": [20.0, 30.0], "confidence": 0.9, "team": "home"},
        {"t": 1.0, "gid": 9, "xy": [40.0, 30.0], "confidence": 0.8, "team": "away"},
    ])
    assert len(frames) == 1
    assert len(frames[0].players) == 2
    assert frames[0].players[0].player_id == "7"


def test_empty_native_analysis_reports_no_fabricated_events():
    report = VisionIntelligencePipeline().analyze_native_outputs([], "home")
    assert report["tracking"]["frames"] == 0
    assert report["event_inference"]["validated_ground_truth"] is False
    assert report["event_inference"]["passes"] == 0
