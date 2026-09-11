from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


SEGMENTS = {
    "0059": "0059_2013-11-03 18:01:23.251115000.h264",
    "0060": "0060_2013-11-03 18:01:26.252555000.h264",
    "0061": "0061_2013-11-03 18:01:29.253030000.h264",
}
TRUTH = "2013-11-03_tromso_stromsgodset_first.csv"


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def build_camera(data_dir: Path, cam: int, out_dir: Path) -> Path:
    cam_dir = data_dir / f"cam{cam}"
    sources = []
    for seg, name in SEGMENTS.items():
        p = cam_dir / name
        if not p.exists():
            # Accept sanitized filenames produced by shells/filesystems that
            # replace ':' with '-'.  The contents are still required to be the
            # native H.264 segment from the official dataset.
            p = cam_dir / name.replace(":", "-")
        if not p.exists():
            raise FileNotFoundError(f"missing cam{cam} segment {seg}: {name}")
        sources.append(p)

    out_dir.mkdir(parents=True, exist_ok=True)
    joined = out_dir / f"cam{cam}.h264"
    mp4 = out_dir / f"cam{cam}.mp4"
    with joined.open("wb") as dst:
        for p in sources:
            dst.write(p.read_bytes())
    run([
        "ffmpeg", "-y", "-f", "h264", "-r", "25", "-i", str(joined),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
        "-pix_fmt", "yuv420p", str(mp4),
    ])
    return mp4


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the exact native Alfheim V59 OOS benchmark locally.")
    ap.add_argument("--data", required=True, help="directory containing cam0/, cam1/, cam2/ and zxy/")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    data = Path(args.data).resolve()
    out = Path(args.out).resolve()
    video_dir = out / "video"
    truth = data / "zxy" / TRUTH
    if not truth.exists():
        truth = data / TRUTH
    if not truth.exists():
        raise FileNotFoundError(f"missing ground-truth CSV: {TRUTH}")

    videos = [build_camera(data, cam, video_dir) for cam in range(3)]
    benchmark_out = out / "benchmark"
    run([
        "python", "vision_v1/alfheim_benchmark_v59_oos_trackset_consensus.py",
        "--cam0", str(videos[0]), "--cam1", str(videos[1]), "--cam2", str(videos[2]),
        "--truth", str(truth), "--out", str(benchmark_out),
    ])

    geometry_out = out / "geometry"
    for cam, video in enumerate(videos):
        run([
            "python", "vision_v1/alfheim_geometry_audit.py",
            "--video", str(video), "--cam", str(cam), "--out", str(geometry_out),
        ])

    print(f"V59 benchmark: {benchmark_out / 'metrics.json'}", flush=True)
    print(f"Geometry audit: {geometry_out}", flush=True)


if __name__ == "__main__":
    main()
