from __future__ import annotations

import argparse
import json
import os
import platform
try:
    import resource
except ImportError:
    resource = None
import subprocess
import sys
import time
from pathlib import Path


def _rss_mb(value: int | float | None) -> float | None:
    if value is None:
        return None
    value = float(value)
    if platform.system() == "Darwin":
        return value / (1024 * 1024)
    return value / 1024.0


def _children_rusage() -> tuple[float | None, float | None]:
    if resource is None or not hasattr(resource, "RUSAGE_CHILDREN"):
        return None, None
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    return (
        float(getattr(r, "ru_utime", 0.0) + getattr(r, "ru_stime", 0.0)),
        _rss_mb(getattr(r, "ru_maxrss", None)),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure one external command.")
    ap.add_argument("--name", required=True)
    ap.add_argument("--json-out", required=True)
    ap.add_argument("--cwd", default=None)
    ap.add_argument("command", nargs=argparse.REMAINDER)
    args = ap.parse_args()

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("No command supplied")

    before_cpu, _ = _children_rusage()
    started = time.perf_counter()
    proc = subprocess.run(command, cwd=args.cwd, check=False)
    wall = time.perf_counter() - started
    after_cpu, peak_rss = _children_rusage()

    metrics = {
        "name": args.name,
        "command": command,
        "returncode": int(proc.returncode),
        "wall_seconds": float(wall),
        "child_cpu_seconds": (
            float(max(0.0, (after_cpu or 0.0) - (before_cpu or 0.0)))
            if after_cpu is not None and before_cpu is not None
            else None
        ),
        "peak_child_rss_mb": peak_rss,
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "logical_cpus": os.cpu_count(),
    }

    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2), flush=True)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
