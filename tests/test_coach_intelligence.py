from centella_analytics.coach_intelligence import coach_intelligence


def test_coach_intelligence_surfaces_tracking_quality_with_evidence():
    analysis = {
        "tracking": {"frames": 10},
        "tactical": {"interaction_intelligence": {"ball_side_interactions": {"team_numerical_advantage_rate": 0.5}}},
        "player_intelligence": {"players": {"7": {"observation": {"tracking_coverage": 0.5, "mean_confidence": 0.6}}}},
        "performance_intelligence": {"players": {}},
    }
    report = coach_intelligence(analysis)
    assert report["valid"] is True
    assert report["insight_count"] == 1
    insight = report["insights"][0]
    assert insight["type"] == "tracking_quality_warning"
    assert "tracking_coverage" in insight["evidence"]


def test_coach_intelligence_does_not_emit_insights_without_tracking():
    report = coach_intelligence({"tracking": {"frames": 0}})
    assert report["valid"] is False
    assert report["insights"] == []
