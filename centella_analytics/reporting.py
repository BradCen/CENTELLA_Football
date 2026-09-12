from __future__ import annotations

from collections import defaultdict
from typing import Mapping


_PRIORITY = {"high": 0, "medium": 1, "low": 2}


def _fmt(value, digits: int = 2):
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def summarize_report(report: Mapping) -> dict:
    """Build a compact, deterministic executive summary from a platform report."""
    analysis = report.get("analysis", report)
    players = analysis.get("player_intelligence", {}).get("players", {})
    perf = analysis.get("performance_intelligence", {}).get("players", {})
    tactical = analysis.get("tactical", {})
    advanced = analysis.get("advanced_intelligence", {})
    xg = analysis.get("predictive", {}).get("xg", {})
    quality = analysis.get("data_quality", {})

    player_rows = []
    for pid, data in players.items():
        tech = data.get("technical_per_90", {})
        physical = perf.get(pid, {}).get("external_load", {})
        player_rows.append({
            "player_id": pid,
            "pass_completion_rate": tech.get("pass_completion_rate", 0.0),
            "progressive_pass_distance_m_per_90": tech.get("progressive_pass_distance_m", 0.0),
            "key_passes_per_90": tech.get("key_passes", 0.0),
            "duels_won_per_90": tech.get("duels_won", 0.0),
            "distance_m_per_90": physical.get("estimated_distance_m_per_90", 0.0),
            "sprint_distance_m_per_90": physical.get("sprint_distance_m_per_90", 0.0),
            "tracking_confidence": data.get("observation", {}).get("mean_confidence", 0.0),
        })
    leaderboards = {
        "progression": sorted(player_rows, key=lambda r: r["progressive_pass_distance_m_per_90"], reverse=True)[:5],
        "chance_creation": sorted(player_rows, key=lambda r: r["key_passes_per_90"], reverse=True)[:5],
        "duels": sorted(player_rows, key=lambda r: r["duels_won_per_90"], reverse=True)[:5],
        "sprint_exposure": sorted(player_rows, key=lambda r: r["sprint_distance_m_per_90"], reverse=True)[:5],
    }

    insights = list(report.get("coach_intelligence", {}).get("insights", []))
    insights.sort(key=lambda x: (_PRIORITY.get(x.get("priority"), 9), -float(x.get("confidence", 0.0))))

    summary = {
        "team": analysis.get("team"),
        "analysis_version": analysis.get("version"),
        "tracking": analysis.get("tracking", {}),
        "data_quality": quality,
        "headline": {
            "xg": xg.get("xg"),
            "goals": xg.get("goals"),
            "shots": xg.get("shots"),
            "field_tilt_pct": tactical.get("field_tilt", {}).get("field_tilt_pct"),
            "progressed_m": tactical.get("progression", {}).get("progressed_m"),
            "team_control_pct": analysis.get("pitch_control", {}).get("team_control_pct"),
            "numerical_advantage_rate": advanced.get("numerical_superiority", {}).get("team_advantage_rate"),
            "mean_territorial_value": advanced.get("territorial_value", {}).get("mean_territorial_value"),
        },
        "leaderboards": leaderboards,
        "coach_review_prompts": insights[:10],
        "provenance": report.get("provenance", {
            "event_inference_mode": analysis.get("event_inference", {}).get("mode", "supplied_events"),
            "validated_ground_truth": analysis.get("event_inference", {}).get("validated_ground_truth", False),
        }),
    }
    return summary


def to_markdown(summary: Mapping) -> str:
    """Render the deterministic summary as coach-readable Markdown."""
    h = summary.get("headline", {})
    lines = [
        f"# CENTELLA Football — Match Intelligence Report",
        "",
        f"**Team:** {summary.get('team', 'n/a')}  ",
        f"**Analysis version:** {summary.get('analysis_version', 'n/a')}  ",
        f"**Tracking window:** {_fmt(summary.get('tracking', {}).get('first_t'))} → {_fmt(summary.get('tracking', {}).get('last_t'))} s",
        "",
        "## Match headline",
        "",
        f"- Shots: **{h.get('shots', 'n/a')}**",
        f"- xG: **{_fmt(h.get('xg'))}**",
        f"- Goals: **{h.get('goals', 'n/a')}**",
        f"- Field tilt: **{_fmt(h.get('field_tilt_pct'))}%**",
        f"- Progressive movement: **{_fmt(h.get('progressed_m'))} m**",
        f"- Pitch control: **{_fmt(h.get('team_control_pct'))}%**",
        f"- Local numerical advantage rate: **{_fmt(100.0 * h.get('numerical_advantage_rate'), 1) if h.get('numerical_advantage_rate') is not None else 'n/a'}%**",
        "",
        "## Player leaders",
        "",
    ]
    labels = {
        "progression": "Progression (progressive pass distance / 90)",
        "chance_creation": "Chance creation (key passes / 90)",
        "duels": "Duels (duels won / 90)",
        "sprint_exposure": "High-intensity exposure (sprint distance / 90)",
    }
    value_keys = {
        "progression": "progressive_pass_distance_m_per_90",
        "chance_creation": "key_passes_per_90",
        "duels": "duels_won_per_90",
        "sprint_exposure": "sprint_distance_m_per_90",
    }
    for key, title in labels.items():
        lines.append(f"### {title}")
        rows = summary.get("leaderboards", {}).get(key, [])
        if not rows:
            lines.append("No sufficient player observations.")
            lines.append("")
            continue
        lines.append("| Player | Value | Tracking confidence |")
        lines.append("|---|---:|---:|")
        for row in rows:
            lines.append(f"| {row['player_id']} | {_fmt(row[value_keys[key]])} | {_fmt(row['tracking_confidence'], 2)} |")
        lines.append("")

    lines.append("## Coach review prompts")
    lines.append("")
    prompts = summary.get("coach_review_prompts", [])
    if prompts:
        for prompt in prompts:
            lines.append(f"- **{prompt.get('priority', 'review').upper()}** — {prompt.get('message', '')} Confidence: {_fmt(prompt.get('confidence'), 2)}.")
            if prompt.get("action"):
                lines.append(f"  - Review: {prompt['action']}")
    else:
        lines.append("No review prompts were emitted by the configured rules.")
    lines.extend([
        "",
        "## Provenance",
        "",
        f"- Event inference mode: `{summary.get('provenance', {}).get('event_inference_mode', 'n/a')}`",
        f"- Ground-truth validated: **{summary.get('provenance', {}).get('validated_ground_truth', False)}**",
        "- Model-derived quantities remain estimates until calibrated and validated on appropriate labelled data.",
    ])
    return "\n".join(lines) + "\n"


def build_match_report(report: Mapping) -> tuple[dict, str]:
    """Return both machine-readable summary data and coach-readable Markdown."""
    summary = summarize_report(report)
    return summary, to_markdown(summary)
