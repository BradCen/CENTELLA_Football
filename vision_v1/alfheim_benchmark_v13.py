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
CAL_SPLIT = 3.0


def cosine_distance(a, b):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    den = float(np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9
    return 1.0 - float(np.dot(a, b) / den)


@dataclass
class CameraTrack:
    tid: int
    cam: int
    obs: list = field(default_factory=list)
    miss_s: float = 0.0

    def pred_seed(self, t):
        if len(self.obs) < 2:
            return self.obs[-1]["seed_xy"]
        a, b = self.obs[-2], self.obs[-1]
        dt = max(0.04, b["t"] - a["t"])
        vel = (b["seed_xy"] - a["seed_xy"]) / dt
        speed = float(np.linalg.norm(vel))
        if speed > 11.0:
            vel *= 11.0 / speed
        return b["seed_xy"] + vel * max(0.0, t - b["t"])

    def proto(self):
        if not self.obs:
            return None
        return np.median(np.asarray([o["feat"] for o in self.obs[-16:]], float), axis=0)

    def cal_obs(self, end_t=4.0):
        return [o for o in self.obs if o["t"] <= end_t]

    def hold_obs(self, start_t=4.0):
        return [o for o in self.obs if o["t"] > start_t]


def track_camera(frames, cam):
    tracks = []
    active = []
    next_id = 0
    prev_t = None
    for f in frames:
        t = float(f["t"])
        det = f["det"]
        dt = 0.125 if prev_t is None else max(0.04, t - prev_t)
        prev_t = t
        used_t, used_d = set(), set()
        if active and det:
            C = np.full((len(active), len(det)), 1e6, float)
            for i, tr in enumerate(active):
                pred = tr.pred_seed(t)
                proto = tr.proto()
                for j, d in enumerate(det):
                    dist = float(np.linalg.norm(pred - d["seed_xy"]))
                    gate = min(4.2, 1.65 + 2.4 * tr.miss_s + 2.0 * max(0.0, dt - 0.125))
                    if dist > gate:
                        continue
                    app = cosine_distance(proto, d["feat"]) if proto is not None else 0.0
                    C[i, j] = dist + 0.42 * max(0.0, app)
            ri, ci = linear_sum_assignment(C)
            for i, j in zip(ri, ci):
                if C[i, j] >= 1e5:
                    continue
                tr = active[i]
                d = det[j]
                tr.obs.append({
                    "t": t, "foot": np.asarray(d["foot"], float),
                    "seed_xy": np.asarray(d["seed_xy"], float),
                    "feat": np.asarray(d["feat"], float),
                    "kit_feat": np.asarray(d["kit_feat"], float),
                    "conf": float(d["conf"]),
                })
                tr.miss_s = 0.0
                used_t.add(i)
                used_d.add(j)
        for i, tr in enumerate(active):
            if i not in used_t:
                tr.miss_s += dt
        for j, d in enumerate(det):
            if j in used_d:
                continue
            o = {
                "t": t, "foot": np.asarray(d["foot"], float),
                "seed_xy": np.asarray(d["seed_xy"], float),
                "feat": np.asarray(d["feat"], float),
                "kit_feat": np.asarray(d["kit_feat"], float),
                "conf": float(d["conf"]),
            }
            tr = CameraTrack(next_id, cam, [o], 0.0)
            next_id += 1
            tracks.append(tr)
            active.append(tr)
        active = [tr for tr in active if tr.miss_s <= 0.90]
    return tracks


def track_gid_cost(tr, gid, truth_by, end_t=4.0):
    errs = []
    for o in tr.obs:
        if o["t"] > end_t:
            continue
        gt = {g["id"]: g for g in truth_at(truth_by, o["t"])}
        if gid not in gt:
            continue
        q = np.asarray([gt[gid]["x"], gt[gid]["y"]], float)
        errs.append(float(np.linalg.norm(o["seed_xy"] - q)))
    if len(errs) < 5:
        return 99.0, len(errs)
    return float(np.median(errs)), len(errs)


def map_calibration_tracks(tracks, truth_by, calibration_seconds=4.0):
    candidates = []
    rows = []
    for tr in tracks:
        cal = tr.cal_obs(calibration_seconds)
        if len(cal) < 5:
            continue
        vals = []
        for gid in TARGET_IDS:
            c, _ = track_gid_cost(tr, gid, truth_by, calibration_seconds)
            vals.append(c)
        candidates.append(tr)
        rows.append(vals)
    if not rows:
        return {}, []
    C = np.asarray(rows, float)
    ri, ci = linear_sum_assignment(C)
    mapping = {}
    diag = []
    for r, c in zip(ri, ci):
        med = float(C[r, c])
        sorted_row = np.sort(C[r])
        margin = float(sorted_row[1] - sorted_row[0]) if len(sorted_row) > 1 else 99.0
        tr = candidates[r]
        cal_n = len(tr.cal_obs(calibration_seconds))
        hold_n = len(tr.hold_obs(calibration_seconds))
        if med <= 3.15 and margin >= 0.45 and cal_n >= 5:
            gid = TARGET_IDS[c]
            mapping[tr.tid] = gid
            diag.append({
                "track_id": tr.tid, "gt_id": gid,
                "calibration_median_seed_m": med,
                "identity_margin_m": margin,
                "calibration_samples": cal_n,
                "holdout_samples_before_stitch": hold_n,
            })
    return mapping, diag


def fit_camera_from_mapped(cam, tracks, mapping, truth_by):
    seed = v10.seed_model(cam)
    P, W = [], []
    for tr in tracks:
        gid = mapping.get(tr.tid)
        if gid is None:
            continue
        for o in tr.obs:
            if o["t"] > CAL_SPLIT:
                continue
            gt = {g["id"]: g for g in truth_at(truth_by, o["t"])}
            if gid not in gt:
                continue
            P.append(o["foot"])
            W.append([gt[gid]["x"], gt[gid]["y"]])
    candidates = [("seed", seed)]
    if len(P) >= 10:
        P = np.asarray(P, float)
        W = np.asarray(W, float)
        for ransac in (1.6, 1.25):
            candidates.append((f"mapped_h_{ransac}", v10.fit_pure_h(P, W, cam, ransac)))

    def validation(model):
        errs = []
        count = 0
        for tr in tracks:
            gid = mapping.get(tr.tid)
            if gid is None:
                continue
            for o in tr.obs:
                if not (CAL_SPLIT < o["t"] <= 4.0):
                    continue
                gt = {g["id"]: g for g in truth_at(truth_by, o["t"])}
                if gid not in gt:
                    continue
                q = model.project(np.asarray([o["foot"]], float))[0]
                g = np.asarray([gt[gid]["x"], gt[gid]["y"]], float)
                errs.append(float(np.linalg.norm(q - g)))
                count += 1
        if not errs:
            return {"samples": 0, "mae_m": 99.0, "p95_m": 99.0}
        a = np.asarray(errs, float)
        return {"samples": count, "mae_m": float(a.mean()), "p95_m": float(np.percentile(a, 95))}

    scored = []
    for name, model in candidates:
        q = validation(model)
        score = q["mae_m"] + 0.20 * q["p95_m"]
        scored.append((score, name, model, q))
    scored.sort(key=lambda x: x[0])
    _, name, model, q = scored[0]
    return model, {
        "chosen": name,
        "validation": q,
        "candidates": [
            {"name": n, "score": float(s), "validation": qq}
            for s, n, _, qq in scored
        ],
        "mapped_pairs_train": len(P) if isinstance(P, np.ndarray) else len(P),
    }


def assign_projected_xy(tracks, model):
    for tr in tracks:
        if not tr.obs:
            continue
        pix = np.asarray([o["foot"] for o in tr.obs], float)
        xy = model.project(pix)
        for o, p in zip(tr.obs, xy):
            o["xy"] = np.asarray(p, float)


def track_proto(tr):
    return np.median(np.asarray([o["feat"] for o in tr.obs], float), axis=0)


def stitch_post_calibration(tracks, mapping, calibration_seconds=4.0):
    by_id = {tr.tid: tr for tr in tracks}
    mapped = dict(mapping)
    audit = []
    changed = True
    while changed:
        changed = False
        for base_tid, gid in list(mapped.items()):
            base = by_id[base_tid]
            if not base.obs:
                continue
            last = base.obs[-1]
            proto = track_proto(base)
            best = None
            for cand in tracks:
                if cand.tid in mapped or not cand.obs:
                    continue
                first = cand.obs[0]
                if first["t"] <= calibration_seconds:
                    continue
                gap = first["t"] - last["t"]
                if gap <= 0.0 or gap > 1.05:
                    continue
                pred = base.pred_seed(first["t"])
                dist = float(np.linalg.norm(pred - first["seed_xy"]))
                if dist > 2.55:
                    continue
                app = cosine_distance(proto, track_proto(cand))
                if app > 0.38:
                    continue
                score = dist + 0.75 * app + 0.18 * gap
                if best is None or score < best[0]:
                    best = (score, cand, dist, app, gap)
            if best is not None:
                _, cand, dist, app, gap = best
                mapped[cand.tid] = gid
                audit.append({
                    "from_track": base_tid, "to_track": cand.tid, "gt_id": gid,
                    "gap_s": float(gap), "pred_distance_m": float(dist),
                    "appearance_distance": float(app),
                })
                changed = True
    return mapped, audit


def camera_identity_quality(tracks, mapping, truth_by):
    errs = []
    by_gid = {}
    for tr in tracks:
        gid = mapping.get(tr.tid)
        if gid is None:
            continue
        for o in tr.obs:
            if not (CAL_SPLIT < o["t"] <= 4.0):
                continue
            gt = {g["id"]: g for g in truth_at(truth_by, o["t"])}
            if gid not in gt:
                continue
            e = float(np.linalg.norm(o["xy"] - np.asarray([gt[gid]["x"], gt[gid]["y"]], float)))
            errs.append(e)
            by_gid.setdefault(gid, []).append(e)
    if not errs:
        return {"samples": 0, "mae_m": 99.0, "weight": 0.05}
    a = np.asarray(errs, float)
    mae = float(a.mean())
    return {
        "samples": len(a), "mae_m": mae, "p95_m": float(np.percentile(a, 95)),
        "ids": sorted(by_gid), "weight": float(1.0 / (0.35 + mae * mae)),
    }


def fuse_by_identity(times, camera_tracks, camera_maps, camera_quality):
    index = {}
    for cam, tracks in camera_tracks.items():
        for tr in tracks:
            gid = camera_maps[cam].get(tr.tid)
            if gid is None:
                continue
            for o in tr.obs:
                key = (round(float(o["t"]), 6), gid)
                index.setdefault(key, []).append((cam, o))
    fused = {}
    for t in times:
        tk = round(float(t), 6)
        for gid in TARGET_IDS:
            items = index.get((tk, gid), [])
            if not items:
                continue
            per_cam = {}
            for cam, o in items:
                if cam not in per_cam or o["conf"] > per_cam[cam]["conf"]:
                    per_cam[cam] = o
            items = [(cam, o) for cam, o in per_cam.items()]
            pts = np.asarray([o["xy"] for _, o in items], float)
            ws = np.asarray([
                max(0.03, camera_quality[cam]["weight"]) * max(0.08, o["conf"])
                for cam, o in items
            ], float)
            ws /= ws.sum()
            center = np.sum(pts * ws[:, None], axis=0)
            if len(pts) >= 2:
                med = np.median(pts, axis=0)
                dd = np.linalg.norm(pts - med[None, :], axis=1)
                if float(np.max(dd)) > 2.8:
                    k = int(np.argmin(dd / np.maximum(ws, 1e-6)))
                    center = pts[k]
            fused[(tk, gid)] = {
                "t": float(t), "gt_id": gid, "xy": np.asarray(center, float),
                "cams": sorted(per_cam), "camera_count": len(per_cam),
            }
    return fused


def evaluate(fused, truth_by, times, calibration_seconds=4.0):
    rows = []
    output_count = 0
    total_gt = 0
    seen_ids = set()
    for t in times:
        if t <= calibration_seconds:
            continue
        gt_list = truth_at(truth_by, float(t))
        total_gt += len(gt_list)
        gt = {g["id"]: g for g in gt_list}
        tk = round(float(t), 6)
        for gid in TARGET_IDS:
            q = fused.get((tk, gid))
            if q is None:
                continue
            output_count += 1
            if gid not in gt:
                continue
            g = gt[gid]
            truth_xy = np.asarray([g["x"], g["y"]], float)
            err = float(np.linalg.norm(q["xy"] - truth_xy))
            seen_ids.add(gid)
            rows.append({
                "t": float(t), "track_id": gid, "gt_id": gid,
                "pred_x": float(q["xy"][0]), "pred_y": float(q["xy"][1]),
                "truth_x": float(g["x"]), "truth_y": float(g["y"]),
                "position_error_m": err, "truth_speed": g.get("speed", 0.0),
                "truth_total_distance": g.get("total_distance", 0.0),
                "camera_count": q["camera_count"], "cams": ",".join(map(str, q["cams"])),
            })
    metrics = v10.summarize_physical(rows, total_gt, output_count)
    metrics.update({
        "identity_frozen_holdout": True,
        "post_holdout_gt_relinking": False,
        "mapped_gt_ids": sorted(seen_ids),
        "identity_id_coverage": len(seen_ids) / len(TARGET_IDS),
        "output_count": output_count,
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

    camera_tracks = {}
    camera_maps = {}
    camera_quality = {}
    diagnostics = {}

    for cam in range(3):
        tracks = track_camera(cams[cam], cam)
        base_map, map_diag = map_calibration_tracks(tracks, truth_by, args.calibration_seconds)
        model, geom_diag = fit_camera_from_mapped(cam, tracks, base_map, truth_by)
        assign_projected_xy(tracks, model)
        final_map, stitches = stitch_post_calibration(tracks, base_map, args.calibration_seconds)
        quality = camera_identity_quality(tracks, base_map, truth_by)
        camera_tracks[cam] = tracks
        camera_maps[cam] = final_map
        camera_quality[cam] = quality
        diagnostics[str(cam)] = {
            "raw_tracks": len(tracks),
            "calibration_mapped_tracks": len(base_map),
            "calibration_mapped_ids": sorted(set(base_map.values())),
            "mapping": map_diag,
            "geometry": geom_diag,
            "post_calibration_stitches": stitches,
            "final_mapped_track_fragments": len(final_map),
            "identity_validation": quality,
        }
        np.save(out / f"cam{cam}_H.npy", model.H)
        print("cam", cam, json.dumps(diagnostics[str(cam)], indent=2), flush=True)

    fused = fuse_by_identity(times, camera_tracks, camera_maps, camera_quality)
    metrics, rows = evaluate(fused, truth_by, times, args.calibration_seconds)
    metrics.update({
        "version": "v13-track-first-frozen-identity",
        "video_duration_s": dur,
        "sample_fps": args.sample_fps,
        "calibration_seconds": args.calibration_seconds,
        "camera_diagnostics": diagnostics,
        "truth_source": "20Hz sensor XY",
        "identity_method": "per-camera temporal tracklets mapped only in calibration; post-calibration stitching uses trajectory+appearance without GT",
    })
    pd.DataFrame(rows).to_csv(out / "matched_observations.csv", index=False)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (out / "camera_maps.json").write_text(
        json.dumps({str(c): {str(k): int(v) for k, v in m.items()} for c, m in camera_maps.items()}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(metrics, indent=2), flush=True)


if __name__ == "__main__":
    main()
