from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> None:
    print("$ " + " ".join(map(str, cmd)), flush=True)
    subprocess.run(cmd, check=True)


def load_metrics(path: Path) -> dict:
    p = path / "metrics.json"
    if not p.exists():
        raise RuntimeError(f"missing benchmark output: {p}")
    return json.loads(p.read_text())


def main() -> None:
    ap = argparse.ArgumentParser(description="V60 image-only geometry A/B around the V56 anonymous global tracker")
    ap.add_argument("--cam0", required=True)
    ap.add_argument("--cam1", required=True)
    ap.add_argument("--cam2", required=True)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    baseline = out / "baseline"
    geometry = out / "geometry"
    refined_models = out / "geometry_models"
    baseline.mkdir(parents=True, exist_ok=True)
    geometry.mkdir(parents=True, exist_ok=True)
    refined_models.mkdir(parents=True, exist_ok=True)

    here = Path(__file__).resolve().parent
    refine = here / "alfheim_geometry_refine.py"
    benchmark = here / "alfheim_benchmark_v56_oos_globaltrack.py"

    for cam, video in enumerate((args.cam0, args.cam1, args.cam2)):
        run([
            sys.executable, str(refine),
            "--video", video,
            "--cam", str(cam),
            "--out", str(refined_models),
            "--samples", "6",
        ])

    common = [
        sys.executable, str(benchmark),
        "--cam0", args.cam0,
        "--cam1", args.cam1,
        "--cam2", args.cam2,
        "--truth", args.truth,
    ]

    run(common + ["--out", str(baseline)])
    run(common + ["--out", str(geometry), "--geometry-dir", str(refined_models)])

    b = load_metrics(baseline)
    g = load_metrics(geometry)
    bm = b.get("calibration_mapped_holdout_evaluation", {})
    gm = g.get("calibration_mapped_holdout_evaluation", {})
    ba = b.get("anonymous_tracking_diagnostics", {})
    ga = g.get("anonymous_tracking_diagnostics", {})
    bf = b.get("framewise_geometry_evaluation", {})
    gf = g.get("framewise_geometry_evaluation", {})

    comparison = {
        "version": "v60-image-only-geometry-ab",
        "segment": "0059-0061",
        "inference_uses_ground_truth": False,
        "ground_truth_usage": "Only used inside the inherited V56 evaluation/calibration diagnostics, after trajectories are constructed.",
        "baseline": {
            "geometry": "V56 seed camera models",
            "mapped_holdout": bm,
            "anonymous": ba,
            "framewise": bf,
            "geometry_models_loaded": b.get("geometry_models_loaded", []),
        },
        "geometry_refined": {
            "geometry": "image-only field-line refinement accepted by per-camera gate",
            "mapped_holdout": gm,
            "anonymous": ga,
            "framewise": gf,
            "geometry_models_loaded": g.get("geometry_models_loaded", []),
        },
    }

    for section, key in (("mapped_holdout", "mae_m"), ("anonymous", "nearest_match_rate"), ("framewise", "mae_m")):
        bv = comparison["baseline"][section].get(key)
        gv = comparison["geometry_refined"][section].get(key)
        if isinstance(bv, (int, float)) and isinstance(gv, (int, float)):
            comparison["geometry_refined"][section][f"delta_{key}"] = float(gv - bv)
            if key == "mae_m":
                comparison["geometry_refined"][section][f"relative_change_{key}"] = float((gv - bv) / max(abs(bv), 1e-9))
            else:
                comparison["geometry_refined"][section][f"relative_change_{key}"] = float((gv - bv) / max(abs(bv), 1e-9))

    (out / "comparison.json").write_text(json.dumps(comparison, indent=2))
    print(json.dumps(comparison, indent=2), flush=True)


if __name__ == "__main__":
    main()
