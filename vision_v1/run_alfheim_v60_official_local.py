from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


SEGMENTS = ("0059", "0060", "0061")


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def concat_h264(paths: list[Path], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as dst:
        for p in paths:
            if not p.is_file() or p.stat().st_size == 0:
                raise FileNotFoundError(p)
            dst.write(p.read_bytes())


def make_mp4(parts: list[Path], out: Path) -> None:
    raw = out.with_suffix(".h264")
    concat_h264(parts, raw)
    run(["ffmpeg", "-y", "-f", "h264", "-r", "25", "-i", str(raw), "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-pix_fmt", "yuv420p", str(out)])


def main() -> int:
    ap = argparse.ArgumentParser(description="Run CENTELLA V60 on official local Alfheim OOS files 0059-0061.")
    ap.add_argument("--cam-root", required=True, type=Path, help="Directory containing cam0/, cam1/, cam2/ with 0059-0061 .h264 files")
    ap.add_argument("--truth", required=True, type=Path, help="Official first-half ZXY CSV")
    ap.add_argument("--out", default=Path("output/alfheim_v60_official"), type=Path)
    args = ap.parse_args()

    if not args.truth.is_file() or args.truth.stat().st_size == 0:
        raise FileNotFoundError(f"truth CSV not found: {args.truth}")
    args.out.mkdir(parents=True, exist_ok=True)
    videos = []
    for cam in range(3):
        parts = []
        for seg in SEGMENTS:
            matches = sorted((args.cam_root / f"cam{cam}").glob(f"{seg}_*.h264"))
            if len(matches) != 1:
                raise FileNotFoundError(f"cam{cam} segment {seg}: expected one .h264, found {len(matches)}")
            parts.append(matches[0])
        out = args.out / f"cam{cam}.mp4"
        make_mp4(parts, out)
        videos.append(out)

    script = Path(__file__).with_name("alfheim_benchmark_v60_geometry_ab.py")
    run([sys.executable, str(script), "--cam0", str(videos[0]), "--cam1", str(videos[1]), "--cam2", str(videos[2]), "--truth", str(args.truth), "--out", str(args.out / "ab")])
    report = args.out / "ab" / "comparison.json"
    if report.is_file():
        data = json.loads(report.read_text(encoding="utf-8"))
        print(json.dumps(data, indent=2), flush=True)
    else:
        print(f"WARNING: comparison report missing: {report}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
