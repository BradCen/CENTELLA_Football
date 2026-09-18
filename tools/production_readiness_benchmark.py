from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import statistics
import time
from collections import OrderedDict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from centella_analytics.engine import AnalyticsEngine
from centella_analytics.events import EventTimeline
from centella_analytics.reporting import build_match_report
from centella_analytics.types import PlayerSample, TrackingFrame


def _float(row: dict, *names: str, default: float = 0.0) -> float:
    for name in names:
        if name in row and row[name] not in ("", None):
            return float(row[name])
    return default


def load_tracking(path: str) -> tuple[list[TrackingFrame], dict]:
    rows = list(csv.DictReader(Path(path).open("r", encoding="utf-8", newline="")))
    if not rows:
        raise SystemExit("Tracking CSV is empty")

    by_t: "OrderedDict[float, TrackingFrame]" = OrderedDict()
    player_ids: set[str] = set()

    for row in rows:
        t = _float(row, "t")
        tid = str(row.get("player_id") or row.get("track_id") or "").strip()
        if not tid:
            raise SystemExit("Tracking CSV has an empty player/track id")

        x = _float(row, "x", "pred_x")
        y = _float(row, "y", "pred_y")

        try:
            numeric_tid = int(float(tid))
        except ValueError:
            numeric_tid = int(hashlib.sha1(tid.encode()).hexdigest()[:8], 16)

        team = row.get("team") or ("home" if numeric_tid < 5 else "away")
        if team not in ("home", "away"):
            team = "home" if numeric_tid < 5 else "away"

        if "confidence" in row and row["confidence"]:
            conf = max(0.0, min(1.0, float(row["confidence"])))
        elif "position_error_m" in row and row["position_error_m"]:
            conf = max(0.0, min(1.0, 1.0 - float(row["position_error_m"]) / 10.0))
        else:
            conf = 1.0

        frame = by_t.setdefault(t, TrackingFrame(t=t))
        frame.players.append(
            PlayerSample(
                player_id=tid,
                team=team,
                x=x,
                y=y,
                t=t,
                confidence=conf,
            )
        )
        player_ids.add(tid)

    frames = [by_t[k] for k in sorted(by_t)]
    ts = [f.t for f in frames]
    deltas = [b - a for a, b in zip(ts, ts[1:]) if b > a]
    cadence = statistics.median(deltas) if deltas else None
    duration_s = (ts[-1] - ts[0]) if len(ts) > 1 else 0.0
    sample_fps = (1.0 / cadence) if cadence and cadence > 0 else None

    return frames, {
        "rows": len(rows),
        "frames": len(frames),
        "players": len(player_ids),
        "first_t": ts[0],
        "last_t": ts[-1],
        "duration_s": duration_s,
        "sample_fps": sample_fps,
        "csv_bytes": Path(path).stat().st_size,
        "platform": platform.platform(),
        "logical_cpus": os.cpu_count(),
    }


def run_analytics(frames: list[TrackingFrame]) -> tuple[dict, float, str, float]:
    engine = AnalyticsEngine()
    events = EventTimeline()

    warm_start = time.perf_counter()
    engine.analyze_team(frames, events, "home", "away")
    warm = time.perf_counter() - warm_start

    start = time.perf_counter()
    report = engine.analyze_team(frames, events, "home", "away")
    wall = time.perf_counter() - start

    summary, markdown = build_match_report(report)
    assert report["version"] == "32.0.0"
    assert report["tracking"]["frames"] == len(frames)
    assert summary["analysis_version"] == "32.0.0"
    assert "CENTELLA Football" in markdown
    return report, wall, markdown, warm


def expand_to_matchday_roster(frames: list[TrackingFrame], target_players: int) -> list[TrackingFrame]:
    if not frames:
        return []
    target_players = max(2, int(target_players))
    ordered = sorted(
        {p.player_id: p for f in frames for p in f.players}.values(),
        key=lambda p: (p.team != "home", p.player_id),
    )
    seeds = {
        "home": [p for p in ordered if p.team == "home"] or [ordered[0]],
        "away": [p for p in ordered if p.team == "away"] or [ordered[-1]],
    }
    roster: list[tuple[str, str, PlayerSample]] = []
    per_team = target_players // 2
    for team in ("home", "away"):
        for i in range(per_team):
            seed = seeds[team][i % len(seeds[team])]
            roster.append((f"{team}_{i+1:02d}", team, seed))

    start_t = frames[0].t
    normalized_frames = [
        TrackingFrame(
            t=frame.t - start_t,
            players=frame.players,
            ball=frame.ball,
        )
        for frame in frames
    ]
    expanded: list[TrackingFrame] = []
    for frame in normalized_frames:
        players: list[PlayerSample] = []
        for idx, (pid, team, seed) in enumerate(roster):
            template = next((p for p in frame.players if p.player_id == seed.player_id), frame.players[0])
            # Small deterministic offsets spread cloned observations over the pitch.
            row = idx % 4
            col = (idx // 4) % 6
            dx = (col - 2.5) * 1.6
            dy = (row - 1.5) * 2.0
            x = min(104.0, max(1.0, template.x + dx))
            y = min(67.0, max(1.0, template.y + dy))
            players.append(
                PlayerSample(
                    player_id=pid,
                    team=team,
                    x=x,
                    y=y,
                    t=frame.t,
                    confidence=template.confidence,
                    vx=template.vx,
                    vy=template.vy,
                    speed_mps=template.speed_mps,
                    acceleration_mps2=template.acceleration_mps2,
                    role=template.role,
                    is_goalkeeper=template.is_goalkeeper and i == 0,
                )
            )
        expanded.append(TrackingFrame(t=frame.t, players=players, ball=frame.ball))
    return expanded


def synthesize_match(base_frames: list[TrackingFrame], match_minutes: float, target_players: int) -> list[TrackingFrame]:
    expanded = expand_to_matchday_roster(base_frames, target_players)
    if not expanded:
        return []

    span = expanded[-1].t if len(expanded) > 1 else 1.0
    deltas = [b.t - a.t for a, b in zip(expanded, expanded[1:]) if b.t > a.t]
    cadence = statistics.median(deltas) if deltas else 0.125
    target_frames = max(2, int(round(match_minutes * 60.0 / cadence)))

    out: list[TrackingFrame] = []
    for idx in range(target_frames):
        src = expanded[idx % len(expanded)]
        cycle = idx // len(expanded)
        t = src.t + cycle * (span + cadence)
        if t > match_minutes * 60.0:
            break
        players = [
            PlayerSample(
                player_id=p.player_id,
                team=p.team,
                x=p.x,
                y=p.y,
                t=t,
                confidence=p.confidence,
                vx=p.vx,
                vy=p.vy,
                speed_mps=p.speed_mps,
                acceleration_mps2=p.acceleration_mps2,
                role=p.role,
                is_goalkeeper=p.is_goalkeeper,
            )
            for p in src.players
        ]
        out.append(TrackingFrame(t=t, players=players, ball=src.ball))
    return out

def main() -> int:
    ap = argparse.ArgumentParser(description="CENTELLA Production Readiness analytics benchmark")
    ap.add_argument("--tracking", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--match-minutes", type=float, default=90.0)
    ap.add_argument("--players", type=int, default=22)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    frames, fixture = load_tracking(args.tracking)
    report, wall, markdown, warm = run_analytics(frames)

    fixture["analytics_warmup_seconds"] = warm
    fixture["analytics_wall_seconds"] = wall
    fixture["analytics_frames_per_second"] = len(frames) / max(wall, 1e-9)
    fixture["analytics_real_time_factor"] = (
        fixture["duration_s"] / max(wall, 1e-9)
        if fixture["duration_s"] > 0 else None
    )
    fixture["projected_90min_runtime_minutes"] = (
        90.0 / fixture["analytics_real_time_factor"]
        if fixture["analytics_real_time_factor"] else None
    )

    capacity_frames = synthesize_match(frames, args.match_minutes, args.players)
    cap_start = time.perf_counter()
    cap_engine = AnalyticsEngine()
    cap_report = cap_engine.analyze_team(capacity_frames, EventTimeline(), "home", "away")
    cap_wall = time.perf_counter() - cap_start
    cap_summary, cap_markdown = build_match_report(cap_report)

    assert cap_report["version"] == "32.0.0"
    assert cap_report["tracking"]["frames"] == len(capacity_frames)
    assert cap_summary["analysis_version"] == "32.0.0"
    assert "CENTELLA Football" in cap_markdown

    capacity = {
        "target_match_minutes": args.match_minutes,
        "target_players": args.players,
        "synthetic_frames": len(capacity_frames),
        "synthetic_players_per_frame": args.players,
        "wall_seconds": cap_wall,
        "frames_per_second": len(capacity_frames) / max(cap_wall, 1e-9),
        "equivalent_real_time_factor": (args.match_minutes * 60.0) / max(cap_wall, 1e-9),
        "synthetic_semantics": "volume/capacity stress only; repeated fixture observations are not a real match",
    }

    (out / "analytics_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out / "analytics_summary.json").write_text(
        json.dumps(cap_summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out / "analytics_report.md").write_text(cap_markdown, encoding="utf-8")

    benchmark = {
        "benchmark_version": "1.0.0",
        "benchmark_type": "production-readiness",
        "fixture": fixture,
        "capacity_stress": capacity,
        "requirements_logic": {
            "analytics_target_real_time_factor": 1.0,
            "analytics_comfort_real_time_factor": 2.0,
            "ram_headroom_factor": 1.5,
            "storage_note": "camera storage is derived separately from native camera media bitrate; commercial camera codecs/configurations must be re-measured on site",
        },
    }

    (out / "analytics_benchmark.json").write_text(
        json.dumps(benchmark, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(benchmark, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
