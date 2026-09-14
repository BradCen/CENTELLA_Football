from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

import alfheim_benchmark_v9 as v9
import alfheim_benchmark_v10 as v10
import alfheim_benchmark_v11 as v11
from alfheim_benchmark import load_truth, truth_at

NATIVE_START = v9.NATIVE_START
TARGET_IDS = v9.TARGET_IDS
TRAIN_END = 3.0
CAL_END = 4.0


def cosine_distance(a, b):
    if a is None or b is None:
        return 0.0
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    den = float(np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9
    return 1.0 - float(np.dot(a, b) / den)


def robust_median(xs):
    if not xs:
        return None
    return np.median(np.asarray(xs, float), axis=0)


def cap_velocity(v, vmax=10.5):
    v = np.asarray(v, float)
    s = float(np.linalg.norm(v))
    if s > vmax:
        v = v * (vmax / s)
    return v


def project_detections(model, detections):
    if not detections:
        return np.empty((0, 2), float)
    return model.project(np.asarray([d["foot"] for d in detections], float))


def calibration_pairs(frames, model, lo=-1e9, hi=TRAIN_END, gate=4.2):
    P, W, gids, costs = [], [], [], []
    for f in frames:
        if not (lo < f["t"] <= hi):
            continue
        ds = f["det"]
        if not ds or not f["gt"]:
            continue
        pred = project_detections(model, ds)
        pairs = v9.hungarian_pairs(pred, f["gt"], gate)
        for i, j, c in pairs:
            if c > gate:
                continue
            P.append(ds[i]["foot"])
            W.append([f["gt"][j]["x"], f["gt"][j]["y"]])
            gids.append(int(f["gt"][j]["id"]))
            costs.append(float(c))
    return np.asarray(P, float), np.asarray(W, float), gids, costs


def geometry_quality(frames, model, lo, hi, gate=3.5):
    errs = []
    matched = 0
    gt_count = 0
    det_count = 0
    for f in frames:
        if not (lo < f["t"] <= hi):
            continue
        ds = f["det"]
        gt_count += len(f["gt"])
        det_count += len(ds)
        pred = project_detections(model, ds)
        pairs = v9.hungarian_pairs(pred, f["gt"], gate)
        matched += len(pairs)
        errs.extend(c for _, _, c in pairs)
    if not errs:
        return {
            "matched": 0, "gt_points": gt_count, "detections": det_count,
            "recall": 0.0, "precision_proxy": 0.0,
            "mae_m": 99.0, "p95_m": 99.0,
        }
    a = np.asarray(errs, float)
    return {
        "matched": matched, "gt_points": gt_count, "detections": det_count,
        "recall": matched / max(1, gt_count),
        "precision_proxy": matched / max(1, det_count),
        "mae_m": float(a.mean()),
        "p95_m": float(np.percentile(a, 95)),
    }


def fit_geometry(cam, frames):
    seed = v10.seed_model(cam)
    P, W, _, _ = calibration_pairs(frames, seed, hi=TRAIN_END, gate=4.5)
    candidates = [("seed", seed)]
    if len(P) >= 8:
        for ransac in (1.8, 1.35, 1.0):
            candidates.append((f"pure_h_{ransac}", v10.fit_pure_h(P, W, cam, ransac)))
        if len(P) >= 14:
            try:
                candidates.append(("residual", v9.fit_camera_model(P, W, use_residual=True)))
            except Exception:
                pass

    rows = []
    max_match = 1
    for name, model in candidates:
        q = geometry_quality(frames, model, TRAIN_END, CAL_END, gate=3.5)
        max_match = max(max_match, q["matched"])
        rows.append({"name": name, "model": model, "validation": q})
    for r in rows:
        q = r["validation"]
        coverage = q["matched"] / max_match
        r["score"] = q["mae_m"] + 0.18 * q["p95_m"] + 1.35 * (1.0 - coverage)
    best = min(rows, key=lambda r: r["score"])
    diag = {
        "chosen": best["name"],
        "train_pairs": int(len(P)),
        "validation": best["validation"],
        "candidates": [
            {"name": r["name"], "score": float(r["score"]), "validation": r["validation"]}
            for r in rows
        ],
    }
    return best["model"], diag


def collect_identity_prototypes(frames, model, calibration_end=CAL_END):
    feat = {gid: [] for gid in TARGET_IDS}
    kit = {gid: [] for gid in TARGET_IDS}
    conf = {gid: [] for gid in TARGET_IDS}
    residual = {gid: [] for gid in TARGET_IDS}
    matches = {gid: 0 for gid in TARGET_IDS}
    all_res = []

    for f in frames:
        if f["t"] > calibration_end:
            continue
        ds = f["det"]
        if not ds:
            continue
        pred = project_detections(model, ds)
        pairs = v9.hungarian_pairs(pred, f["gt"], 3.6)
        for i, j, c in pairs:
            if c > 3.25:
                continue
            gid = int(f["gt"][j]["id"])
            d = ds[i]
            feat[gid].append(d["feat"])
            kit[gid].append(d["kit_feat"])
            conf[gid].append(float(d["conf"]))
            gtxy = np.asarray([f["gt"][j]["x"], f["gt"][j]["y"]], float)
            rr = gtxy - pred[i]
            residual[gid].append(rr)
            all_res.append(rr)
            matches[gid] += 1

    global_bias = robust_median(all_res)
    if global_bias is None:
        global_bias = np.zeros(2, float)

    protos = {}
    for gid in TARGET_IDS:
        per_bias = robust_median(residual[gid])
        bias = per_bias if per_bias is not None and matches[gid] >= 6 else global_bias
        protos[gid] = {
            "feat": robust_median(feat[gid]),
            "kit": robust_median(kit[gid]),
            "bias": np.asarray(bias, float),
            "matches": int(matches[gid]),
            "median_conf": float(np.median(conf[gid])) if conf[gid] else 0.0,
        }
    return protos, {
        "total_identity_matches": int(sum(matches.values())),
        "matches_per_id": {str(g): int(matches[g]) for g in TARGET_IDS},
        "global_bias": global_bias.tolist(),
    }


def camera_validation_identity(frames, model, protos):
    errs = []
    matched = 0
    for f in frames:
        if not (TRAIN_END < f["t"] <= CAL_END):
            continue
        ds = f["det"]
        if not ds:
            continue
        pred = project_detections(model, ds)
        for i, p in enumerate(pred):
            gt = f["gt"]
            if not gt:
                continue
            G = np.asarray([[g["x"], g["y"]] for g in gt], float)
            k = int(np.argmin(np.linalg.norm(G - p[None, :], axis=1)))
            gid = int(gt[k]["id"])
            corr = p + protos.get(gid, {}).get("bias", np.zeros(2))
            e = float(np.linalg.norm(corr - G[k]))
            if e <= 3.5:
                errs.append(e)
                matched += 1
    if not errs:
        return {"samples": 0, "mae_m": 99.0, "p95_m": 99.0, "weight": 0.02}
    a = np.asarray(errs, float)
    mae = float(a.mean())
    return {
        "samples": matched,
        "mae_m": mae,
        "p95_m": float(np.percentile(a, 95)),
        "weight": float(1.0 / (0.22 + mae * mae)),
    }


@dataclass
class PlayerState:
    gid: int
    pos: np.ndarray
    vel: np.ndarray
    t: float
    miss_s: float = 0.0
    history: list = field(default_factory=list)

    def predict(self, t):
        dt = max(0.0, float(t) - self.t)
        return self.pos + self.vel * dt

    def update(self, t, z):
        t = float(t)
        z = np.asarray(z, float)
        dt = max(0.04, t - self.t)
        pred = self.predict(t)
        residual = z - pred
        alpha = 0.72
        beta = 0.10
        self.pos = pred + alpha * residual
        self.vel = cap_velocity(self.vel + beta * residual / dt)
        self.t = t
        self.miss_s = 0.0
        self.history.append({"t": t, "xy": self.pos.copy(), "observed": True})
        return self.pos.copy()

    def coast(self, t):
        t = float(t)
        dt = max(0.0, t - self.t)
        self.pos = self.predict(t)
        self.t = t
        self.miss_s += dt
        self.history.append({"t": t, "xy": self.pos.copy(), "observed": False})
        return self.pos.copy()


def initialize_states(truth_by, times):
    cal_times = [float(t) for t in times if t <= CAL_END]
    if len(cal_times) < 2:
        raise RuntimeError("Need at least two calibration samples")
    t1, t2 = cal_times[-2], cal_times[-1]
    g1 = {g["id"]: g for g in truth_at(truth_by, t1)}
    g2 = {g["id"]: g for g in truth_at(truth_by, t2)}
    states = {}
    for gid in TARGET_IDS:
        if gid not in g2:
            continue
        p2 = np.asarray([g2[gid]["x"], g2[gid]["y"]], float)
        if gid in g1:
            p1 = np.asarray([g1[gid]["x"], g1[gid]["y"]], float)
            vel = cap_velocity((p2 - p1) / max(0.04, t2 - t1))
        else:
            vel = np.zeros(2, float)
        states[gid] = PlayerState(gid, p2, vel, t2)
    return states, {"state_time": t2, "velocity_time": t1, "initialized_ids": sorted(states)}


def candidate_cost(state, pred_xy, d, proto, gate):
    geom = float(np.linalg.norm(state - pred_xy))
    if geom > gate:
        return None
    app = cosine_distance(proto.get("feat"), d["feat"]) if proto else 0.0
    kit = cosine_distance(proto.get("kit"), d["kit_feat"]) if proto else 0.0
    if proto and proto.get("feat") is not None and app > 0.72:
        return None
    return geom + 0.34 * max(0.0, app) + 0.18 * max(0.0, kit) - 0.04 * float(d["conf"])


def assign_camera(states, t, frame, model, protos):
    ids = sorted(states)
    ds = frame["det"]
    if not ids or not ds:
        return {}
    raw_xy = project_detections(model, ds)
    C = np.full((len(ids), len(ds)), 1e6, float)
    corrected = {}
    for i, gid in enumerate(ids):
        st = states[gid]
        state_pred = st.predict(t)
        gate = min(4.2, 2.05 + 1.65 * st.miss_s)
        proto = protos.get(gid, {})
        bias = np.asarray(proto.get("bias", np.zeros(2)), float)
        for j, (p, d) in enumerate(zip(raw_xy, ds)):
            q = p + bias
            c = candidate_cost(state_pred, q, d, proto, gate)
            if c is None:
                continue
            C[i, j] = c
            corrected[(gid, j)] = q
    ri, ci = linear_sum_assignment(C)
    out = {}
    for i, j in zip(ri, ci):
        if C[i, j] >= 1e5:
            continue
        gid = ids[i]
        out[gid] = {
            "xy": np.asarray(corrected[(gid, j)], float),
            "cost": float(C[i, j]),
            "conf": float(ds[j]["conf"]),
            "det_index": int(j),
        }
    return out


def fuse_assignments(assignments, camera_quality):
    by_gid = {}
    for cam, amap in assignments.items():
        for gid, o in amap.items():
            by_gid.setdefault(gid, []).append((cam, o))
    out = {}
    for gid, items in by_gid.items():
        pts = np.asarray([o["xy"] for _, o in items], float)
        ws = np.asarray([
            max(0.015, camera_quality[cam]["weight"]) *
            max(0.08, o["conf"]) *
            (1.0 / (0.35 + o["cost"]))
            for cam, o in items
        ], float)
        if len(pts) >= 2:
            med = np.median(pts, axis=0)
            d = np.linalg.norm(pts - med[None, :], axis=1)
            good = d <= max(1.8, float(np.median(d)) + 1.0)
            if np.any(good):
                pts = pts[good]
                ws = ws[good]
                items = [it for it, k in zip(items, good) if k]
        ws = ws / max(1e-9, ws.sum())
        xy = np.sum(pts * ws[:, None], axis=0)
        out[gid] = {
            "xy": np.asarray(xy, float),
            "cams": sorted(cam for cam, _ in items),
            "camera_count": len(items),
        }
    return out


def run_holdout(states, cams, models, protos, camera_quality, times):
    outputs = []
    for idx, t0 in enumerate(times):
        t = float(t0)
        if t <= CAL_END:
            continue
        assignments = {}
        for cam in range(3):
            if idx >= len(cams[cam]):
                continue
            assignments[cam] = assign_camera(
                states, t, cams[cam][idx], models[cam], protos[cam]
            )
        fused = fuse_assignments(assignments, camera_quality)
        for gid, st in states.items():
            if gid in fused:
                xy = st.update(t, fused[gid]["xy"])
                outputs.append({
                    "t": t, "gt_id": gid, "xy": xy,
                    "observed": True, "cams": fused[gid]["cams"],
                    "camera_count": fused[gid]["camera_count"],
                })
            else:
                xy = st.coast(t)
                if st.miss_s <= 0.25:
                    outputs.append({
                        "t": t, "gt_id": gid, "xy": xy,
                        "observed": False, "cams": [],
                        "camera_count": 0,
                    })
    return outputs


def evaluate(outputs, truth_by, times):
    rows = []
    total_gt = sum(len(truth_at(truth_by, float(t))) for t in times if t > CAL_END)
    for o in outputs:
        gt = {g["id"]: g for g in truth_at(truth_by, o["t"])}
        gid = o["gt_id"]
        if gid not in gt:
            continue
        g = gt[gid]
        q = np.asarray([g["x"], g["y"]], float)
        err = float(np.linalg.norm(o["xy"] - q))
        rows.append({
            "t": o["t"], "track_id": gid, "gt_id": gid,
            "pred_x": float(o["xy"][0]), "pred_y": float(o["xy"][1]),
            "truth_x": float(g["x"]), "truth_y": float(g["y"]),
            "position_error_m": err,
            "truth_speed": g.get("speed", 0.0),
            "truth_total_distance": g.get("total_distance", 0.0),
            "observed": bool(o["observed"]),
            "camera_count": int(o["camera_count"]),
            "cams": ",".join(map(str, o["cams"])),
        })
    metrics = v10.summarize_physical(rows, total_gt, len(outputs))
    ids = sorted(set(r["gt_id"] for r in rows))
    observed = [r for r in rows if r["observed"]]
    if observed:
        a = np.asarray([r["position_error_m"] for r in observed], float)
        observed_metrics = {
            "samples": len(observed),
            "mae_m": float(a.mean()),
            "rmse_m": float(np.sqrt(np.mean(a * a))),
            "p95_m": float(np.percentile(a, 95)),
        }
    else:
        observed_metrics = {"samples": 0}
    metrics.update({
        "identity_frozen_holdout": True,
        "post_holdout_gt_relinking": False,
        "identity_id_coverage": len(ids) / len(TARGET_IDS),
        "mapped_gt_ids": ids,
        "observed_position": observed_metrics,
        "reported_outputs": len(outputs),
        "observed_outputs": len(observed),
    })
    return metrics, rows


def main():
    ap = argparse.ArgumentParser()
    for i in range(3):
        ap.add_argument(f"--cam{i}", required=True)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sample-fps", type=float, default=8.0)
    ap.add_argument("--calibration-seconds", type=float, default=4.0)
    ap.add_argument("--model", default="yolo11n.pt")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    from ultralytics import YOLO

    detector = YOLO(args.model)
    truth_by = load_truth(args.truth, video_start=NATIVE_START)
    caps = {i: cv2.VideoCapture(getattr(args, f"cam{i}")) for i in range(3)}
    dur = min(
        cap.get(cv2.CAP_PROP_FRAME_COUNT) / float(cap.get(cv2.CAP_PROP_FPS) or 30)
        for cap in caps.values()
    )
    times = np.arange(0.4, max(0.41, dur - 0.2), 1.0 / args.sample_fps)
    cams = {i: [] for i in range(3)}

    for ti, t in enumerate(times):
        gt = truth_at(truth_by, float(t))
        for cam, cap in caps.items():
            cap.set(cv2.CAP_PROP_POS_MSEC, float(t * 1000))
            ok, frame = cap.read()
            if not ok:
                continue
            raw = v9.detect_native(detector, frame)
            for d in raw:
                d["kit_feat"] = v11.kit_feature(frame, d["box"])
            det = v10.on_pitch(cam, raw)
            cams[cam].append({"t": float(t), "det": det, "gt": gt})
        if ti % 8 == 0:
            print(
                f"t={t:.2f}s pitch_det=" +
                ",".join(f"c{c}:{len(cams[c][-1]['det'])}" for c in range(3)),
                flush=True,
            )
    for cap in caps.values():
        cap.release()

    models = {}
    protos = {}
    camera_quality = {}
    diagnostics = {}
    for cam in range(3):
        model, geom = fit_geometry(cam, cams[cam])
        p, pdiag = collect_identity_prototypes(cams[cam], model, CAL_END)
        q = camera_validation_identity(cams[cam], model, p)
        models[cam] = model
        protos[cam] = p
        camera_quality[cam] = q
        diagnostics[str(cam)] = {
            "geometry": geom,
            "identity_prototypes": pdiag,
            "validation_quality": q,
        }
        np.save(out / f"cam{cam}_H.npy", model.H)
        print("cam", cam, json.dumps(diagnostics[str(cam)], indent=2), flush=True)

    states, state_diag = initialize_states(truth_by, times)
    outputs = run_holdout(
        states, cams, models, protos, camera_quality, times
    )
    metrics, rows = evaluate(outputs, truth_by, times)
    metrics.update({
        "version": "v14-global-10-id-alpha-beta",
        "video_duration_s": dur,
        "sample_fps": args.sample_fps,
        "calibration_seconds": CAL_END,
        "camera_diagnostics": diagnostics,
        "state_initialization": state_diag,
        "truth_source": "20Hz sensor XY",
        "tracking_method": (
            "10 frozen identities initialized only from calibration; "
            "holdout uses camera geometry + frozen appearance + global one-to-one assignment"
        ),
    })
    pd.DataFrame(rows).to_csv(out / "matched_observations.csv", index=False)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2), flush=True)


if __name__ == "__main__":
    main()
