from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from .events import ShotEvent
from .events_analytics import shot_xg
from .expected import LogisticXGModel


@dataclass(slots=True)
class GoalkeeperAnalytics:
    """Auditable goalkeeper report assembled from shot and distribution events."""
    goalkeeper_id: str
    saves: list[ShotEvent] = field(default_factory=list)
    conceded: list[ShotEvent] = field(default_factory=list)
    claims: int = 0
    aerial_exits: int = 0
    distribution_attempts: int = 0
    distribution_successes: int = 0
    progressive_distributions: int = 0

    def report(self, model: LogisticXGModel | None = None) -> dict:
        model = model or LogisticXGModel.heuristic()
        on_target = [s for s in self.saves if s.on_target] + [s for s in self.conceded if s.on_target and s not in self.saves]
        xg_on_target = [float(s.xgot) if s.xgot is not None else shot_xg(s, model) for s in on_target]
        goals = sum(bool(s.goal) for s in self.conceded)
        total_faced = len(on_target)
        saved = len(self.saves)
        return {
            "goalkeeper_id": self.goalkeeper_id,
            "shots_on_target_faced": total_faced,
            "saves": saved,
            "goals_conceded": int(goals),
            "save_rate": float(saved / total_faced) if total_faced else None,
            "post_shot_xg_faced": float(sum(xg_on_target)),
            "goals_prevented_proxy": float(sum(xg_on_target) - goals),
            "claims": self.claims,
            "aerial_exits": self.aerial_exits,
            "distribution_attempts": self.distribution_attempts,
            "distribution_successes": self.distribution_successes,
            "distribution_completion_rate": float(self.distribution_successes / self.distribution_attempts) if self.distribution_attempts else None,
            "progressive_distributions": self.progressive_distributions,
            "model_metadata": model.metadata(),
            "caveat": "Use xGOT from a trained post-shot model for true save difficulty; pre-shot xG is only a difficulty proxy.",
        }


def goalkeeper_positioning(frames, goalkeeper_id: str, pitch_length: float = 105.0, pitch_width: float = 68.0) -> dict:
    pts = [(p.x, p.y, f.t) for f in frames for p in f.players if p.player_id == goalkeeper_id]
    if not pts:
        return {"valid": False, "samples": 0}
    xy = np.asarray([(p[0], p[1]) for p in pts], dtype=float)
    return {
        "valid": True,
        "samples": len(pts),
        "mean_x_m": float(xy[:, 0].mean()),
        "mean_y_m": float(xy[:, 1].mean()),
        "max_advanced_x_m": float(xy[:, 0].max()),
        "pitch_coverage_pct": float(100.0 * (xy[:, 0].max()-xy[:, 0].min()) / max(1.0, pitch_length)),
    }
