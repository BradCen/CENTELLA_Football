from centella_analytics.reporting import build_match_report


def test_reporting_builds_machine_and_markdown_outputs():
    report = {
        "team": "home",
        "version": "31.0.0",
        "tracking": {"frames": 3, "first_t": 0.0, "last_t": 2.0},
        "data_quality": {"overall_score": 1.0},
        "tactical": {
            "field_tilt": {"field_tilt_pct": 61.0},
            "progression": {"progressed_m": 20.0},
        },
        "predictive": {"xg": {"shots": 2, "xg": 0.4, "goals": 1}},
        "pitch_control": {"team_control_pct": 57.0},
        "advanced_intelligence": {
            "numerical_superiority": {"team_advantage_rate": 0.5},
            "territorial_value": {"mean_territorial_value": 0.6},
        },
        "player_intelligence": {"players": {}},
        "performance_intelligence": {"players": {}},
        "coach_intelligence": {"insights": []},
        "provenance": {"event_inference_mode": "supplied_events", "validated_ground_truth": False},
    }
    summary, markdown = build_match_report(report)
    assert summary["headline"]["xg"] == 0.4
    assert summary["headline"]["field_tilt_pct"] == 61.0
    assert "CENTELLA Football" in markdown
    assert "Ground-truth validated: **False**" in markdown
