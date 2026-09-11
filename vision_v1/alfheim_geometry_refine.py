from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import minimize

from alfheim_benchmark_v9 import SEED, seed_model
from alfheim_geometry_audit import detect_lines, field_segments, nearest_field_line, project


def collect_line_points(video: str, cam: int, sample_count: int = 6):
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = n / max(fps, 1e-6)
    times = np.linspace(0.0, max(0.001, duration - 0.04), max(1, sample_count))
    H0 = seed_model(cam).H
    segments = field_segments()
    chunks = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t * 1000.0))
        ok, frame = cap.read()
        if not ok:
            continue
        for line in detect_lines(frame):
            w = project(H0, line)
            if not np.all(np.isfinite(w)) or np.max(np.abs(w)) > 250:
                continue
            d, _ = nearest_field_line(w, segments)
            if float(np.mean(d)) > 5.5:
                continue
            samples = np.linspace(0.08, 0.92, 7)
            pts = line[0][None, :] * (1.0 - samples[:, None]) + line[1][None, :] * samples[:, None]
            chunks.append((pts, float(np.linalg.norm(line[1] - line[0]))))
    cap.release()
    if not chunks:
        return np.empty((0, 2), float), np.empty((0,), float)
    pts = np.concatenate([x[0] for x in chunks], axis=0)
    weights = np.concatenate([np.full(len(x[0]), x[1], float) for x in chunks])
    return pts, weights


def objective_factory(H0, points, weights, anchors, anchor_world, segments):
    scale = np.maximum(np.abs(H0).flatten()[:8], 1e-3)

    def unpack(p):
        H = np.asarray(H0, float).copy().flatten()
        H[:8] += np.asarray(p, float) * scale
        H = H.reshape(3, 3)
        if abs(H[2, 2]) < 1e-8:
            return None
        return H / H[2, 2]

    def objective(p):
        H = unpack(p)
        if H is None:
            return 1e6
        world = project(H, points)
        if not np.all(np.isfinite(world)):
            return 1e6
        inside = (world[:, 0] > -6) & (world[:, 0] < 111) & (world[:, 1] > -6) & (world[:, 1] < 74)
        if inside.mean() < 0.75:
            return 1e5 + 1e4 * (0.75 - inside.mean())
        d, _ = nearest_field_line(world, segments)
        d = np.minimum(d, 12.0)
        w = np.asarray(weights, float)
        fit = float(np.average(d * d, weights=w))
        aw = project(H, anchors)
        anchor_err = np.linalg.norm(aw - anchor_world, axis=1)
        regularized = fit + 0.035 * float(np.mean(anchor_err * anchor_err))
        return regularized

    return objective, unpack


def refine(video: str, cam: int, sample_count: int = 6):
    H0 = seed_model(cam).H
    points, weights = collect_line_points(video, cam, sample_count)
    if len(points) < 40:
        return {
            "accepted": False,
            "reason": "insufficient line evidence",
            "points": int(len(points)),
            "seed_h": H0.tolist(),
        }

    sp, sw = SEED[cam]
    segments = field_segments()
    objective, unpack = objective_factory(H0, points, weights, sp, sw, segments)
    base_score = objective(np.zeros(8))
    result = minimize(
        objective,
        np.zeros(8),
        method="Nelder-Mead",
        options={"maxiter": 900, "xatol": 1e-7, "fatol": 1e-5, "adaptive": True},
    )
    H1 = unpack(result.x)
    if H1 is None:
        return {"accepted": False, "reason": "optimizer produced invalid homography", "points": int(len(points)), "seed_h": H0.tolist()}

    refined_score = objective(result.x)
    seed_anchor = project(H0, sp)
    refined_anchor = project(H1, sp)
    anchor_shift = np.linalg.norm(refined_anchor - seed_anchor, axis=1)
    improvement = (base_score - refined_score) / max(base_score, 1e-9)

    # Image-only acceptance gate: require a meaningful line-fit improvement and
    # keep the known seed landmarks from moving by more than a few metres.
    accepted = bool(result.success and improvement >= 0.05 and float(np.max(anchor_shift)) <= 3.0)
    chosen = H1 if accepted else H0
    return {
        "accepted": accepted,
        "optimizer_success": bool(result.success),
        "optimizer_message": str(result.message),
        "points": int(len(points)),
        "base_objective": float(base_score),
        "refined_objective": float(refined_score),
        "relative_improvement": float(improvement),
        "max_seed_anchor_shift_m": float(np.max(anchor_shift)),
        "seed_h": H0.tolist(),
        "refined_h": H1.tolist(),
        "chosen_h": np.asarray(chosen, float).tolist(),
        "note": "No ZXY/ground truth is used. This is a geometry-only candidate generator; it must still be benchmarked end-to-end on the OOS set before claiming an accuracy gain.",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--cam", type=int, required=True, choices=[0, 1, 2])
    ap.add_argument("--out", required=True)
    ap.add_argument("--samples", type=int, default=6)
    args = ap.parse_args()
    result = refine(args.video, args.cam, args.samples)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"cam{args.cam}_geometry_refinement.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
