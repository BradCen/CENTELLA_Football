from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .adapter import load_events_json, load_tracking_csv
from .engine import AnalyticsEngine
from .quality import tracking_quality


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="CENTELLA Football Intelligence V24 analytics")
    parser.add_argument("--tracking", required=True, help="Canonical tracking CSV")
    parser.add_argument("--events", required=True, help="EventTimeline JSON")
    parser.add_argument("--team", required=True, choices=("home", "away"))
    parser.add_argument("--goalkeeper", help="Optional goalkeeper player ID")
    parser.add_argument("--out", required=True, help="Output report JSON")
    args = parser.parse_args(argv)

    frames = load_tracking_csv(args.tracking)
    events = load_events_json(args.events)
    engine = AnalyticsEngine()
    report = engine.analyze_team(frames, events, args.team)
    report["data_quality"] = tracking_quality(frames)
    if args.goalkeeper:
        report["goalkeeper"] = engine.analyze_goalkeeper(args.goalkeeper, frames)
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
