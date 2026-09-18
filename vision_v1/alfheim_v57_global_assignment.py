from __future__ import annotations

"""V57: anonymous global assignment over per-frame world-space detections.

No ground truth is used in inference. Tracks are built as anonymous trajectories;
GT is only consumed by the evaluation stage after predictions are complete.
"""

from dataclasses import dataclass, field
from math import hypot
from typing import Iterable

@dataclass
class Detection:
    t: float
    x: float
    y: float
    score: float = 1.0
    cam: int = -1

@dataclass
class Track:
    tid: int
    points: list[Detection] = field(default_factory=list)
    missed: float = 0.0

    @property
    def last(self):
        return self.points[-1]

    def predicted(self, dt: float) -> tuple[float, float]:
        if len(self.points) < 2:
            return self.last.x, self.last.y
        a, b = self.points[-2], self.points[-1]
        if b.t <= a.t:
            return b.x, b.y
        vx = (b.x - a.x) / (b.t - a.t)
        vy = (b.y - a.y) / (b.t - a.t)
        return b.x + vx * dt, b.y + vy * dt


def _cost(track: Track, det: Detection, max_speed: float = 11.5) -> float:
    dt = max(0.0, det.t - track.last.t)
    px, py = track.predicted(dt)
    d = hypot(det.x - px, det.y - py)
    speed = d / max(dt, 1e-3)
    if speed > max_speed:
        return float("inf")
    return d + 0.75 * abs(speed - min(speed, max_speed)) + 0.25 * (1.0 - det.score)


def assign_frame(tracks: list[Track], detections: list[Detection], gate_m: float = 5.5) -> set[int]:
    # Greedy global ordering: lowest-cost pairs first, with one detection and one
    # track consumed at most once. This is intentionally anonymous and causal.
    pairs: list[tuple[float, int, int]] = []
    for ti, tr in enumerate(tracks):
        for di, det in enumerate(detections):
            c = _cost(tr, det)
            if c <= gate_m:
                pairs.append((c, ti, di))
    pairs.sort()
    used_t: set[int] = set()
    used_d: set[int] = set()
    matched: set[int] = set()
    for _, ti, di in pairs:
        if ti in used_t or di in used_d:
            continue
        tracks[ti].points.append(detections[di])
        tracks[ti].missed = 0.0
        used_t.add(ti); used_d.add(di); matched.add(di)
    return matched


def build_tracks(frames: Iterable[tuple[float, list[Detection]]], gate_m: float = 5.5,
                 max_miss_s: float = 0.75, min_confirm: int = 3) -> list[Track]:
    tracks: list[Track] = []
    next_id = 0
    prev_t: float | None = None
    for t, dets in frames:
        dt = 0.0 if prev_t is None else max(0.0, t - prev_t)
        for tr in tracks:
            if tr.last.t < t:
                tr.missed += dt
        active = [tr for tr in tracks if tr.missed <= max_miss_s]
        matched = assign_frame(active, dets, gate_m=gate_m)
        for di, det in enumerate(dets):
            if di not in matched:
                tracks.append(Track(next_id, [det]))
                next_id += 1
        prev_t = t
    return [tr for tr in tracks if len(tr.points) >= min_confirm]
