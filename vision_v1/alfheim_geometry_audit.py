from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np

from alfheim_seed_geometry import seed_model


def field_segments(n_circle: int = 96):
    """Return canonical 105x68 m pitch line segments in world coordinates."""
    s = []
    def add(a, b, tag): s.append((np.asarray(a, float), np.asarray(b, float), tag))
    add((0, 0), (105, 0), "touchline")
    add((0, 68), (105, 68), "touchline")
    add((0, 0), (0, 68), "goal_line")
    add((105, 0), (105, 68), "goal_line")
    add((52.5, 0), (52.5, 68), "halfway")
    add((0, 13.84), (16.5, 13.84), "penalty_box")
    add((0, 54.16), (16.5, 54.16), "penalty_box")
    add((16.5, 13.84), (16.5, 54.16), "penalty_box")
    add((105, 13.84), (88.5, 13.84), "penalty_box")
    add((105, 54.16), (88.5, 54.16), "penalty_box")
    add((88.5, 13.84), (88.5, 54.16), "penalty_box")
    add((0, 24.84), (5.5, 24.84), "goal_area")
    add((0, 43.16), (5.5, 43.16), "goal_area")
    add((5.5, 24.84), (5.5, 43.16), "goal_area")
    add((105, 24.84), (99.5, 24.84), "goal_area")
    add((105, 43.16), (99.5, 43.16), "goal_area")
    add((99.5, 24.84), (99.5, 43.16), "goal_area")
    r = 9.15
    pts = np.column_stack([52.5 + r*np.cos(np.linspace(0, 2*math.pi, n_circle)), 34.0 + r*np.sin(np.linspace(0, 2*math.pi, n_circle))])
    for a, b in zip(pts[:-1], pts[1:]): s.append((a, b, "center_circle"))
    return s


def project(H, pts):
    pts = np.asarray(pts, float).reshape(-1, 2)
    if not len(pts): return np.empty((0, 2), float)
    q = np.c_[pts, np.ones(len(pts))] @ np.asarray(H, float).T
    z = q[:, 2:3]
    z[np.abs(z) < 1e-9] = 1e-9
    return q[:, :2] / z


def point_segment_distance(p, a, b):
    ab = b - a; den = float(np.dot(ab, ab))
    if den < 1e-9: return float(np.linalg.norm(p-a))
    t = np.clip(float(np.dot(p-a, ab)) / den, 0.0, 1.0)
    return float(np.linalg.norm(p-(a+t*ab)))


def nearest_field_line(points, segments):
    vals=[]; tags=[]
    for p in np.asarray(points, float):
        best=999.0; best_tag=None
        for a,b,tag in segments:
            d=point_segment_distance(p,a,b)
            if d<best: best=d; best_tag=tag
        vals.append(float(best)); tags.append(best_tag)
    return np.asarray(vals), tags


def detect_lines(frame):
    gray=cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges=cv2.Canny(gray,70,160,apertureSize=3)
    lines=cv2.HoughLinesP(edges,rho=1.0,theta=np.pi/180.0,threshold=55,minLineLength=90,maxLineGap=20)
    if lines is None: return []
    result=[]
    # OpenCV 4 commonly returns (N,1,4), while newer builds may return
    # (N,4). Normalize both forms before iterating.
    for raw in np.asarray(lines).reshape(-1, 4):
        x1,y1,x2,y2=map(float,raw)
        length=math.hypot(x2-x1,y2-y1)
        if length<90: continue
        result.append(np.array([[x1,y1],[x2,y2]],float))
    result.sort(key=lambda p:-np.linalg.norm(p[1]-p[0]))
    return result[:160]


def line_diagnostics(H, lines, segments):
    rows=[]
    for seg in lines:
        world=project(H,seg)
        if not np.all(np.isfinite(world)) or np.max(np.abs(world))>400: continue
        d,tags=nearest_field_line(world,segments)
        rows.append({"world_line_length_m":float(np.linalg.norm(world[1]-world[0])),"endpoint_distance_a_m":float(d[0]),"endpoint_distance_b_m":float(d[1]),"mean_endpoint_distance_m":float(np.mean(d)),"line_tag_a":tags[0],"line_tag_b":tags[1]})
    return rows


def audit_video(path: str, cam: int, sample_seconds: float=0.5):
    cap=cv2.VideoCapture(path)
    if not cap.isOpened(): raise RuntimeError(f"cannot open video: {path}")
    fps=float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    frame_count=float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
    duration=frame_count/max(fps,1e-6)
    H=seed_model(cam).H; segments=field_segments(); all_rows=[]; t=0.0
    while t<max(0.001,duration):
        cap.set(cv2.CAP_PROP_POS_MSEC,t*1000.0); ok,frame=cap.read()
        if not ok: break
        all_rows.extend(line_diagnostics(H,detect_lines(frame),segments)); t+=max(0.1,sample_seconds)
    cap.release()
    vals=np.asarray([r["mean_endpoint_distance_m"] for r in all_rows],float)
    return {"camera":int(cam),"duration_s":float(duration),"line_observations":int(len(vals)),"seed_homography":np.asarray(H,float).tolist(),"mean_line_error_m":float(vals.mean()) if len(vals) else None,"median_line_error_m":float(np.median(vals)) if len(vals) else None,"p95_line_error_m":float(np.percentile(vals,95)) if len(vals) else None,"good_line_fraction_under_2m":float(np.mean(vals<=2.0)) if len(vals) else None,"note":"Image-only diagnostic; no ZXY/ground truth is consumed."},all_rows


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--video",required=True); ap.add_argument("--cam",type=int,required=True,choices=[0,1,2]); ap.add_argument("--out",required=True); ap.add_argument("--sample-seconds",type=float,default=0.5); args=ap.parse_args()
    summary,rows=audit_video(args.video,args.cam,args.sample_seconds); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    (out/f"cam{args.cam}_geometry.json").write_text(json.dumps(summary,indent=2)); (out/f"cam{args.cam}_line_diagnostics.json").write_text(json.dumps(rows,indent=2)); print(json.dumps(summary,indent=2),flush=True)

if __name__=="__main__": main()
