from __future__ import annotations

import argparse
import json
import os
import platform
from pathlib import Path


def load(path: str) -> dict:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble CENTELLA Production Readiness report")
    ap.add_argument("--analytics", required=True)
    ap.add_argument("--analytics-process", required=True)
    ap.add_argument("--vision", required=True)
    ap.add_argument("--media", required=True)
    ap.add_argument("--host", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    analytics = load(args.analytics)
    analytics_process = load(args.analytics_process)
    vision = load(args.vision)
    media = load(args.media)
    host = load(args.host) if args.host else {}

    fx = analytics["fixture"]
    cap = analytics["capacity_stress"]
    duration_s = float(vision.get("fixture_duration_s", 0.0))
    vision_wall = float(vision.get("wall_seconds", 0.0))
    vision_rtf = duration_s / vision_wall if duration_s > 0 and vision_wall > 0 else None
    vision_projected_90 = 90.0 / vision_rtf if vision_rtf else None

    total_mbps = sum(float(c.get("avg_source_mbps", 0.0)) for c in media["cameras"])
    storage_90_gb = total_mbps * 5400.0 / 8.0 / 1000.0

    report = {
        "benchmark_version": "1.0.0",
        "status": "COMPUTE_AND_MEDIA_BASELINE",
        "status_explanation": (
            "Real OOS video plus real V62 tracking were benchmarked. "
            "The benchmark is the acceptance test for candidate field hardware; "
            "a commercial SKU is locked after the same run is repeated on that target PC/GPU."
        ),
        "system": {
            "platform": host.get("platform", platform.platform()),
            "python": host.get("python"),
            "logical_cpus": host.get("logical_cpus", os.cpu_count()),
            "physical_cpus": host.get("physical_cpus"),
            "memory_total_gb": host.get("memory_total_gb"),
        },
        "vision": {
            "fixture_duration_s": duration_s,
            "wall_seconds": vision_wall,
            "real_time_factor": vision_rtf,
            "projected_90min_runtime_minutes": vision_projected_90,
            "returncode": vision.get("returncode"),
            "peak_rss_mb": vision.get("peak_child_rss_mb"),
            "child_cpu_seconds": vision.get("child_cpu_seconds"),
        },
        "analytics": {
            "fixture_frames": fx["frames"],
            "fixture_duration_s": fx["duration_s"],
            "wall_seconds": fx["analytics_wall_seconds"],
            "real_time_factor": fx["analytics_real_time_factor"],
            "projected_90min_runtime_minutes": fx["projected_90min_runtime_minutes"],
            "capacity_90min_wall_seconds": cap["wall_seconds"],
            "capacity_90min_real_time_factor": cap["equivalent_real_time_factor"],
            "capacity_peak_rss_mb": analytics_process.get("peak_child_rss_mb"),
            "capacity_child_cpu_seconds": analytics_process.get("child_cpu_seconds"),
        },
        "media": {
            "camera_count": len(media["cameras"]),
            "ingest_bandwidth_mbps": total_mbps,
            "storage_per_90min_gb": storage_90_gb,
            "cameras": media["cameras"],
        },
        "requirements": {
            "validated_reference_camera_configuration": "3 fixed cameras, current Alfheim OOS protocol",
            "analytics_pilot_minimum": {
                "cpu": "6 physical cores minimum; 8+ recommended",
                "ram": "16 GB minimum; 32 GB recommended",
                "system_storage": "500 GB SSD minimum; 1 TB NVMe recommended",
                "gpu": "Not required by the current V24-V32 Analytics engine",
            },
            "vision_pilot_baseline": {
                "cpu": "8 physical cores recommended",
                "ram": "32 GB recommended",
                "gpu": (
                    "Discrete NVIDIA GPU with at least 8 GB VRAM as the provisional "
                    "multi-camera field baseline; exact GPU SKU is locked by the target-hardware matrix"
                ),
                "storage": "1 TB NVMe for OS/runtime plus dedicated video storage",
                "camera_network": "PoE/IP switching sized above measured aggregate camera bitrate with operating headroom",
            },
            "camera": {
                "coverage": (
                    "The current validated reference is 3 cameras. "
                    "Final field count is determined by pitch coverage, mounting and overlap."
                ),
                "capture": (
                    "Fixed and stable mounting; known timestamps/synchronization; "
                    "the V62 reference decodes 25 FPS and samples tracking at 8 FPS."
                ),
            },
            "internet": {
                "runtime": "Local processing does not require continuous internet after runtime/models are installed",
                "recommended": "Internet for updates, remote dashboard access, backups and telemetry",
            },
            "storage_sizing_formula": "90-minute storage (GB) ≈ aggregate camera bitrate (Mbps) × 67.5",
        },
        "acceptance_targets": {
            "analytics_target_real_time_factor": 1.0,
            "analytics_comfort_real_time_factor": 2.0,
            "description": (
                "1.0x means roughly 90 minutes to process a 90-minute match; "
                "2.0x means roughly 45 minutes."
            ),
        },
        "readiness_gates": {
            "real_video_processed": vision.get("returncode") == 0,
            "analytics_engine_completed": True,
            "full_match_capacity_stress_completed": cap["wall_seconds"] > 0,
            "commercial_hardware_locked": False,
        },
        "limitations": [
            "The source benchmark is an Alfheim research fixture, not local Fundecin footage.",
            "The 90-minute Analytics stress repeats a short real tracking fixture to test computational volume, not football semantics.",
            "Vision 90-minute runtime is a linear projection from a short OOS segment, not a measured full-match vision run.",
            "Commercial camera bitrate, codec, lighting, field mounting and network topology must be measured on the actual site.",
        ],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
