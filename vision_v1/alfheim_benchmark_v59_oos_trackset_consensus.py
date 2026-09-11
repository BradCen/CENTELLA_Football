from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

import alfheim_benchmark as base
import alfheim_benchmark_v56_oos_globaltrack as v56

CAL = v56.CAL
MIN_LEN = 8
MAX_CANDIDATES = 60
MAX_TRACKS = 10
USE_PENALTY = 1.15
MAX_REUSE = 3
CONFLICT_RADIUS_M = 2.5
STRICT_CONFLICT = 0.30
RELAXED_CONFLICT = 0.55


def node_quality(d: dict) -> float:
    conf = float(d.get("conf", 0.0))
    node = float(d.get("node_score", 0.0))
    cams = len(set(d.get("cams", ())))
    return 0.55 * conf + 0.30 * node + 0.15 * min(1.0, cams / 2.0)


def soft_best_path(frames, usage, motion_scale=1.0, app_scale=1.0):
    nodes = []
    by_t = defaultdict(list)
    for ti, frame in enumerate(frames):
        for di, det in enumerate(frame["fused"]):
            k = len(nodes)
            nodes.append((ti, di, det))
            by_t[ti].append(k)

    if not nodes:
        return []

    dp = {}
    prev = {}
    for ti in sorted(by_t):
        for k in by_t[ti]:
            _, di, det = nodes[k]
            key = (ti, di)
            uq = float(usage.get(key, 0))
            if uq > MAX_REUSE:
                continue
            best = v56.BIRTH_PENALTY + v56.SKIP_PENALTY + USE_PENALTY * uq
            pk = None
            for pt in range(ti - 1, max(-1, ti - 3), -1):
                dt = frames[ti]["t"] - frames[pt]["t"]
                if dt > v56.MAX_GAP_S:
                    break
                for q in by_t.get(pt, ()):
                    if q not in dp:
                        continue
                    a = nodes[q][2]
                    # Reuse the validated V56 motion/appearance model, but add
                    # a soft occupancy cost so candidate generation explores
                    # alternate trajectories instead of hard-blocking detections.
                    ec = v56.edge_cost(a, det, dt)
                    if ec is None:
                        continue
                    motion_component = v56.TRANS_WEIGHT * np.linalg.norm(
                        np.asarray(a["xy"]) - np.asarray(det["xy"])
                    ) / max(0.75, v56.MAX_SPEED * dt)
                    app_component = v56.APP_WEIGHT * v56.app_cost(a, det)
                    ec += (motion_scale - 1.0) * motion_component
                    ec += (app_scale - 1.0) * app_component
                    val = dp[q] + ec + USE_PENALTY * uq
                    if val < best:
                        best = val
                        pk = q
            dp[k] = best
            prev[k] = pk

    if not dp:
        return []

    # Favor coherent late-reaching paths without making path length the only
    # criterion. The final candidate-set selector performs the global tradeoff.
    _, k = min(
        (cost - 1.8 * math.log1p(1 + nodes[idx][0]), idx)
        for idx, cost in dp.items()
    )
    path = []
    while k is not None:
        path.append(k)
        k = prev.get(k)
    path.reverse()

    return [(nodes[k][0], nodes[k][1], nodes[k][2]) for k in path]


def trajectory_features(path):
    if not path:
        return {
            "length": 0,
            "score": -1e9,
            "mean_conf": 0.0,
            "camera_count": 0,
            "mean_speed_m_s": 0.0,
            "accel_spike_fraction": 1.0,
            "edge_fraction": 1.0,
            "corner_fraction": 1.0,
            "spatial_span_m": 0.0,
        }

    xy = np.asarray([d[2]["xy"] for d in path], float)
    ts = np.asarray([d[2].get("t", d[0] / v56.FPS) for d in path], float)
    conf = float(np.mean([float(d[2].get("conf", 0.0)) for d in path]))
    cams = set(c for d in path for c in d[2].get("cams", ()))

    if len(xy) > 1:
        dt = np.maximum(np.diff(ts), 1e-3)
        speeds = np.linalg.norm(np.diff(xy, axis=0), axis=1) / dt
    else:
        speeds = np.zeros(1)

    if len(speeds) > 1:
        accel = np.abs(np.diff(speeds)) / np.maximum(np.diff(ts)[1:], 1e-3)
        accel_spike_fraction = float(np.mean(accel > 8.0))
    else:
        accel_spike_fraction = 0.0

    edge = []
    corner = []
    for x, y in xy:
        edge.append(min(x + 1, 106 - x + 1, y + 1, 69 - y + 1))
        corner.append(
            min(
                np.hypot(x, y),
                np.hypot(x, y - 68),
                np.hypot(x - 105, y),
                np.hypot(x - 105, y - 68),
            )
        )
    edge_fraction = float(np.mean(np.asarray(edge) < 2.0))
    corner_fraction = float(np.mean(np.asarray(corner) < 6.0))
    spatial_span = float(np.linalg.norm(np.ptp(xy, axis=0))) if len(xy) > 1 else 0.0

    length_term = math.log1p(len(path))
    speed_term = min(1.5, float(np.mean(speeds)) / 3.0)
    score = (
        1.20 * length_term
        + 0.90 * conf
        + 0.35 * min(2, len(cams))
        + 0.12 * speed_term
        + 0.05 * min(3.0, spatial_span / 10.0)
        - 0.90 * edge_fraction
        - 1.00 * corner_fraction
        - 0.80 * accel_spike_fraction
    )
    return {
        "length": len(path),
        "score": float(score),
        "mean_conf": conf,
        "camera_count": len(cams),
        "mean_speed_m_s": float(np.mean(speeds)),
        "accel_spike_fraction": accel_spike_fraction,
        "edge_fraction": edge_fraction,
        "corner_fraction": corner_fraction,
        "spatial_span_m": spatial_span,
    }


def path_to_track(path, track_id):
    obs = []
    for ti, di, det in path:
        obs.append(
            {
                "t": float(det.get("t", ti / v56.FPS)),
                "xy": np.asarray(det["xy"], float),
                "feat": np.asarray(det.get("feat", []), float),
                "cams": tuple(det.get("cams", ())),
                "conf": float(det.get("conf", 0.0)),
            }
        )
    return {"track_id": int(track_id), "obs": obs}


def overlap_fraction(a, b, radius=CONFLICT_RADIUS_M):
    A = {round(o["t"], 3): o["xy"] for o in a["obs"]}
    B = {round(o["t"], 3): o["xy"] for o in b["obs"]}
    common = set(A) & set(B)
    if not common:
        return 0.0
    close = [np.linalg.norm(A[t] - B[t]) < radius for t in common]
    return float(np.mean(close))


def select_consensus(candidates):
    valid = []
    for c in candidates:
        f = trajectory_features(c)
        if f["length"] >= MIN_LEN:
            valid.append((f["score"], c, f))
    valid.sort(key=lambda x: x[0], reverse=True)

    chosen = []
    chosen_features = []
    for threshold in (STRICT_CONFLICT, RELAXED_CONFLICT):
        for _, candidate, features in valid:
            if any(overlap_fraction(candidate, old) >= threshold for old in chosen):
                continue
            chosen.append(candidate)
            chosen_features.append(features)
            if len(chosen) >= MAX_TRACKS:
                break
        if len(chosen) >= MAX_TRACKS:
            break

    tracks = [path_to_track(p, i) for i, p in enumerate(chosen[:MAX_TRACKS])]
    return tracks, chosen_features, valid


def main():
    ap = argparse.ArgumentParser()
    for i in range(3):
        ap.add_argument(f"--cam{i}", required=True)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    frames, duration, detector_diag = v56.build({0: args.cam0, 1: args.cam1, 2: args.cam2})

    candidates = []
    usage = defaultdict(int)
    variants = ((1.0, 1.0), (0.85, 1.0), (1.15, 1.0), (1.0, 0.70), (1.0, 1.30))

    for i in range(MAX_CANDIDATES):
        ms, aps = variants[i % len(variants)]
        path = soft_best_path(frames, usage, motion_scale=ms, app_scale=aps)
        if len(path) < MIN_LEN:
            break
        candidates.append(path)
        # Soft reuse discourages identical candidates without making a single
        # detection permanently unavailable to the global consensus selector.
        for ti, di, _ in path:
            usage[(ti, di)] += 1

    tracks, selected_features, ranked = select_consensus(candidates)

    tb = base.load_truth(args.truth, video_start=v56.v9.NATIVE_START)
    anonymous = v56.anonymous_eval(tracks, tb)
    mapping, mapdiag = v56.calibration_mapping(tracks, tb)
    mapped, rows = v56.mapped_eval(tracks, mapping, tb)
    framewise = v56.framewise_eval(frames, tb)

    result = {
        "version": "v59-oos-anonymous-trackset-consensus",
        "segment": "0059-0061",
        "duration_s": duration,
        "sample_fps": v56.FPS,
        "calibration_seconds": CAL,
        "inference_uses_ground_truth": False,
        "truth_usage": "ground truth is loaded only after anonymous trajectory construction for evaluation/diagnostics",
        "candidate_tracks": len(candidates),
        "ranked_valid_candidates": len(ranked),
        "selected_tracks": len(tracks),
        "candidate_generation": {
            "max_candidates": MAX_CANDIDATES,
            "reuse_penalty": USE_PENALTY,
            "max_reuse": MAX_REUSE,
            "strict_conflict": STRICT_CONFLICT,
            "relaxed_conflict": RELAXED_CONFLICT,
            "variants": [list(x) for x in variants],
        },
        "selected_track_features": selected_features,
        "framewise_geometry_evaluation": framewise,
        "anonymous_tracking_diagnostics": anonymous,
        "calibration_mapped_holdout_evaluation": mapped,
        "track_identity_mapping": mapdiag,
        "track_lengths": [len(t["obs"]) for t in tracks],
        "detector_selection_diagnostics": detector_diag,
    }

    (out / "metrics.json").write_text(json.dumps(result, indent=2))
    pd.DataFrame(rows).to_csv(out / "matched_observations.csv", index=False)
    pd.DataFrame(
        [
            {"track_id": t["track_id"], "samples": len(t["obs"]), "score": selected_features[i]["score"]}
            for i, t in enumerate(tracks)
        ]
    ).to_csv(out / "tracks_summary.csv", index=False)
    pd.DataFrame(
        [
            {"candidate_index": i, **features}
            for i, (_, _, features) in enumerate(ranked)
        ]
    ).to_csv(out / "candidate_summary.csv", index=False)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
