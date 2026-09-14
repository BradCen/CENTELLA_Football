from __future__ import annotations

"""V58 helper: globally assign detections to anonymous tracks with hard one-to-one gating.

This module contains no dataset/GT access; it is safe to import from an inference path.
"""

from dataclasses import dataclass
from math import hypot

@dataclass(frozen=True)
class Point:
    t: float
    x: float
    y: float

@dataclass
class TrackState:
    track_id: int
    points: list[Point]

    def prediction(self, t: float) -> Point:
        if len(self.points) < 2:
            p = self.points[-1]
            return Point(t, p.x, p.y)
        a, b = self.points[-2], self.points[-1]
        dt = b.t - a.t
        if dt <= 0:
            return Point(t, b.x, b.y)
        f = (t - b.t) / dt
        return Point(t, b.x + f * (b.x-a.x), b.y + f * (b.y-a.y))


def candidate_cost(track: TrackState, p: Point, gate_m: float = 6.0) -> float | None:
    q = track.prediction(p.t)
    d = hypot(p.x-q.x, p.y-q.y)
    if d > gate_m:
        return None
    return d


def global_one_to_one(tracks: list[TrackState], detections: list[Point], gate_m: float = 6.0) -> list[tuple[int,int,float]]:
    pairs=[]
    for ti,tr in enumerate(tracks):
        for di,p in enumerate(detections):
            c=candidate_cost(tr,p,gate_m)
            if c is not None:
                pairs.append((c,ti,di))
    pairs.sort(key=lambda z:(z[0],z[1],z[2]))
    used_t=set(); used_d=set(); out=[]
    for c,ti,di in pairs:
        if ti in used_t or di in used_d:
            continue
        used_t.add(ti); used_d.add(di); out.append((ti,di,c))
    return out
