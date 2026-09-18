from __future__ import annotations

import argparse
import json
import os
import platform
try:
    import resource
except ImportError:  # Windows
    resource = None
import subprocess
import sys
import time
from pathlib import Path


def _rss_mb_from_rusage(value: int | float | None) -> float | None:
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
    return float(getattr(r, "ru_utime", 0.0) + getattr(r, "ru_stime", 0.0)), _rss_mb_from_rusage(getattr(r, "ru_maxrss", None))


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure one external command for production benchmarjÚ[ËB