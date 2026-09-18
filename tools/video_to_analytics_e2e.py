from __future__ import annotations

import argparse
import sys
import csv
import json
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from centella_analytics.engine import AnalyticsEngine
from centella_analytics.events import EventTimeline
from centella_analytics.reporting import build_match_report
from centella_analytics.types import PlayerSample, TrackingFrame


def load_v62_tracking(path: str) -> list[TrackingFrame]:
    rows = list(csv.DictReader(Path(path).open("r", encoding="utf-8", newline="")))
    by_t: dict[float, TrackingFrame] = {}
    # V62 is an anonymous multi-camera video tracker. Team identity is NOT
    # inferred from ground truth here. For this structural E2E validation we
    # assign the anonymous track IDs deterministically to two analysis sides.
    # Ground-truth columns are deliberately ignored.
    for row in rows:
        t = float(row["t"])
        tid = int(row["track_id"])
        f = by_t.setdefault(t, TrackingFrame(t=t))
        team = "home" if tid < 5 else "away"
        f.players.append(
            PlayerSample(
                player_id=str(tid),
                team=team,
                x=float(row["pred_x"]),
                y=float(row["pred_y"]),
                t=t,
                confidence=max(0.0, min(1.0, 1.0 - float(row["position_error_m"]) / 10.0)),
            )
        )
    return [by_t[t] for t in sorted(by_t)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tracking", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    frames = load_v62_tracking(args.tracking)
    if not frames:
        raise SystemExit("No V62 tracking observations were produced")

    engine = AnalyticsEngine()
    # Empty EventTimeline is intentional: this run validates the real-video
    # tracking -> V24-V32 engine -> report path without fabricating event labels.
    events = EventTimeline()
    report = engine.analyze_team(frames, events, "home", "away")
    report["event_inference"] = {
        "mode": "real_video_v62_tracking_no_event_labels",
        "passes": 0,
        "shots": 0,
        "possession_changes": 0,
        "validated_ground_truth": False,
    }
    report["provenance"] = {
        "source": "Alfheim OOS V62 real-video tracker output",
        "ground_truth_used_for_analysis": False,
        "team_assignment": "deterministic anonymous-track partition for structural E2E only",
    }

    summary, markdown = build_match_report(report)
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "report.md").write_text(markdown, encoding="utf-8")

    required = [
        "tracking", "data_quality", "tactical", "predictive", "duels",
        "set_pieces", "player_intelligence", "player_advanced",
        "performance_intelligence", "advanced_intelligence", "pitch_control",
    ]
    missing = [k for k in required if k not in report]
    if missing:
        raise SystemExit(f"Missing analytics sections: {missing}")
    assert report["tracking"]["frames"] > 0
    assert report["pitch_control"]["valid"] is True
    assert summary["tracking"]["frames"] == report["tracking"]["frames"]
    assert "CENTELLA Football" in markdown
    print(json.dumps({
        "status": "PASS",
        "frames": len(frames),
        "players": len({p.player_id for f in frames for p in f.players}),
        "sections": required,
        "report": str(out / "report.json"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
