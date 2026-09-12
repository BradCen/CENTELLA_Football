from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import least_squares

from alfheim_seed_geometry import SEED, seed_model
from alfheim_geometry_audit import detect_lines, field_segments, nearest_field_line, project


def straight_field_segments():
    return [
        (a, b, tag) for a, b, tag in field_segments()
        if tag != "center_circle"
    ]


def line_to_world_seed(H0, line):
    w = project(H0, line)
    if not np.all(np.isfinite(w)) or np.max(np.abs(w)) > 250:
        return None
    return w


def line_equation(a, b):
    v = b - a
    n = np.array([-v[1], v[0]], float)
    norm = float(np.linalg.norm(n))
    if norm < 1e-9:
        return None
    n /= norm
    c = -float(np.dot(n, a))
    return n, c


def collect_line_constraints(video: str, cam: int, sample_count: int = 4):
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = n / max(fps, 1e-6)
    times = np.linspace(0.0, max(0.001, duration - 0.04), max(2, sample_count))
    H0 = seed_model(cam).H
    segments = straight_field_segments()
    constraints = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t * 1000.0))
        ok, frame = cap.read()
        if not ok:
            continue
        for line in detect_lines(frame):
            world = line_to_world_seed(H0, line)
            if world is None:
                continue
            d, _ = nearest_field_line(world, segments)
            mean_d = float(np.mean(d))
            if mean_d > 4.5:
                continue
            eq_candidates = []
            obs_eq = line_equation(world[0], world[1])
            if obs_eq is None:
                continue
            on, oc = obs_eq
            obs_dir = world[1] - world[0]
            obs_dir /= max(float(np.linalg.norm(obs_dir)), 1e-9)
            for a, b, tag in segments:
                field_dir = b - a
                field_dir /= max(float(np.linalg.norm(field_dir)), 1e-9)
                parallel = abs(float(np.dot(obs_dir, field_dir)))
                pa = float(np.linalg.norm(world[0] - a))
                pb = float(np.linalg.norm(world[1] - b))
                da = float(point_distance_to_infinite_line(world[0], a, b))
                db = float(point_distance_to_infinite_line(world[1], a, b))
                score = 3.0 * mean_d + 2.0 * (1.0 - parallel) + 0.15 * min(pa, pb) + 0.5 * (da + db)
                eq_candidates.append((score, a, b, tag))
            if not eq_candidates:
                continue
            _, a, b, tag = min(eq_candidates, key=lambda x: x[0])
            eq = line_equation(a, b)
            if eq is None:
                continue
            nvec, c = eq
            img_pts = np.linspace(0.1, 0.9, 5)[:, None]
            pts = line[0][None, :] * (1.0 - img_pts) + line[1][None, :] * img_pts
            constraints.append({
                "points": pts.reshape(-1, 2),
                "normal": nvec,
                "c": c,
                "weight": max(float(np.linalg.norm(line[1] - line[0])), 1.0),
                "tag": tag,
            })
    cap.release()
    return constraints


def point_distance_to_infinite_line(p, a, b):
    eq = line_equation(a, b)
    if eq is None:
        return 999.0
    n, c = eq
    return abs(float(np.dot(n, p) + c))


def unpack(H0, p):
    H = np.asarray(H0, float).reshape(3, 3).copy().flatten()
    scale = np.maximum(np.abs(np.asarray(H0, float).reshape(3, 3).flatten()[:8]), 1e-3)
    H[:8] += np.asarray(p, float) * scale
    H = H.reshape(3, 3)
    if abs(H[2, 2]) < 1e-8:
        return None
    return H / H[2, 2]


def residuals_factory(H0, constraints, anchors, anchor_world):
    scale = np.maximum(np.abs(np.asarray(H0, float).reshape(3, 3).flatten()[:8]), 1e-3)

    def unpack_local(p):
        return unpack(H0, p)

    def residuals(p):
        H = unpack_local(p)
        if H is None:
            return np.full(64, 1e3, float)
        out = []
        for item in constraints:
            world = project(H, item["points"])
            nvec = item["normal"]
            vals = world @ nvec + item["c"]
            out.extend((vals * np.sqrt(item["weight"])).tolist())
        aw = project(H, anchors)
        anchor_delta = (aw - anchor_world).reshape(-1)
        out.extend((0.20 * anchor_delta).tolist())
        return np.asarray(out, float)

    return residuals


def refine(video: str, cam: int, sample_count: int = 4):
    H0 = seed_model(cam).H
    constraints = collect_line_constraints(video, cam, sample_count)
    if len(constraints) < 8:
        return {
            "accepted": False,
            "reason": "insufficient line constraints",
            "constraints": int(len(constraints)),
            "seed_h": H0.tolist(),
        }

    sp, sw = SEED[cam]
    residuals = residuals_factory(H0, constraints, sp, sw)
    p0 = np.zeros(8, float)
    base = float(np.mean(residuals(p0) ** 2))
    result = least_squares(
        residuals,
        p0,
        method="trf",
        loss="soft_l1",
        f_scale=0.75,
        max_nfev=120,
        xtol=1e-7,
        ftol=1e-7,
        gtol=1e-7,
    )
    H1 = unpack(H0, result.x)
    if H1 is None:
        return {
            "accepted": False,
            "reason": "optimizer produced invalid homography",
            "constraints": int(len(constraints)),
            "seed_h": H0.tolist(),
        }
    refined = float(np.mean(residuals(result.x) ** 2))
    seed_anchor = project(H0, sp)
    refined_anchor = project(H1, sp)
    anchor_shift = np.linalg.norm(refined_anchor - seed_anchor, axis=1)
    improvement = (base - refined) / max(base, 1e-9)
    accepted = bool(result.success and improvement >= 0.05 and float(np.max(anchor_shift)) <= 3.0)
    chosen = H1 if accepted else H0
    return {
        "accepted": accepted,
        "optimizer": "scipy.least_squares_soft_l1_line_residuals",
        "optimizer_success": bool(result.success),
        "optimizer_message": str(result.message),
        "constraints": int(len(constraints)),
        "base_objective": base,
        "refined_objective": refined,
        "relative_improvement": float(improvement),
        "max_seed_anchor_shift_m": float(np.max(anchor_shift)),
        "seed_h": H0.tolist(),
        "refined_h": H1.tolist(),
        "chosen_h": np.asarray(chosen, float).tolist(),
        "note": "Image-only line/geometry refinement. Ground truth is not consumed during inference. Fast bounded least-squares replaces the previous expensive nearest-segment Nelder-Mead loop.",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--cam", type=int, required=True, choices=[0, 1, 2])
    ap.add_argument("--out", required=True)
    ap.add_argument("--samples", type=int, default=4)
    args = ap.parse_args()
    result = refine(args.video, args.cam, args.samples)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"cam{args.cam}_geometry_refinement.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
