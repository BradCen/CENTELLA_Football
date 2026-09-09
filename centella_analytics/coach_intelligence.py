from __future__ import annotations


def coach_intelligence(analysis: dict, min_confidence: float = 0.55) -> dict:
    """Turn measured signals into ranked, explainable coaching observations.

    Rules are deterministic and evidence-backed. They are not autonomous tactical commands;
    each insight includes the measurements that triggered it and an explicit uncertainty field.
    """
    insights = []
    tactical = analysis.get("tactical", {})
    predictive = analysis.get("predictive", {})
    players = analysis.get("player_intelligence", {}).get("players", {})
    perf = analysis.get("performance_intelligence", {}).get("players", {})

    interaction = tactical.get("interaction_intelligence", {})
    overload_rate = interaction.get("ball_side_interactions", {}).get("team_numerical_advantage_rate", 0.0)
    if overload_rate < 0.35:
        confidence = max(0.0, min(0.95, 0.55 + (0.35 - overload_rate)))
        if confidence >= min_confidence:
            insights.append({
                "type": "local_support_constraint",
                "priority": "medium",
                "confidence": round(confidence, 3),
                "evidence": {"team_numerical_advantage_rate": overload_rate},
                "message": "The team frequently lacks local numerical advantage around the ball in the observed samples.",
                "action": "Review spacing and support-player proximity on the corresponding clips before changing structure.",
            })

    xg = predictive.get("xg", {})
    shot_count = xg.get("shots", 0)
    total_xg = xg.get("total_xg", 0.0)
    if shot_count and total_xg / shot_count < 0.08:
        confidence = min(0.9, 0.55 + min(0.35, shot_count / 20.0))
        if confidence >= min_confidence:
            insights.append({
                "type": "shot_quality",
                "priority": "medium",
                "confidence": round(confidence, 3),
                "evidence": {"shots": shot_count, "xg_per_shot": total_xg / shot_count},
                "message": "Observed shot volume is associated with low average pre-shot probability in the available event model.",
                "action": "Review shot locations and preceding possessions rather than treating volume alone as attacking quality.",
            })

    for pid, info in sorted(players.items()):
        confidence = info.get("observation", {}).get("mean_confidence", 1.0)
        coverage = info.get("observation", {}).get("tracking_coverage", 0.0)
        load = perf.get(pid, {}).get("external_load", {})
        sprint_m90 = load.get("sprint_distance_m_per_90", 0.0)
        if coverage < 0.75 and confidence < 0.85:
            c = max(0.0, min(0.9, 0.45 + (0.75 - coverage) + (0.85 - confidence)))
            if c >= min_confidence:
                insights.append({
                    "type": "tracking_quality_warning",
                    "priority": "high",
                    "confidence": round(c, 3),
                    "player_id": pid,
                    "evidence": {"tracking_coverage": coverage, "mean_confidence": confidence},
                    "message": "Player tracking coverage is limited; individual conclusions may be unstable.",
                    "action": "Validate the relevant video segment before using this player's metrics for selection or workload decisions.",
                })
        if sprint_m90 > 900.0:
            insights.append({
                "type": "high_intensity_exposure",
                "priority": "low",
                "confidence": 0.7,
                "player_id": pid,
                "evidence": {"sprint_distance_m_per_90": sprint_m90},
                "message": "Observed sprint-distance exposure is high relative to the configured monitoring threshold.",
                "action": "Compare with the player's historical baseline and match context before interpreting the load.",
            })

    priority_rank = {"high": 0, "medium": 1, "low": 2}
    insights.sort(key=lambda x: (priority_rank.get(x["priority"], 9), -x["confidence"]))
    return {
        "version": "29.0.0",
        "valid": bool(analysis.get("tracking", {}).get("frames", 0) > 0),
        "insight_count": len(insights),
        "insights": insights,
        "disclaimer": "Insights are evidence-backed review prompts, not autonomous coaching decisions.",
    }
