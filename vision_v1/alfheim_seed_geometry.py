from __future__ import annotations

import cv2
import numpy as np


# Image-only calibration anchors for the three Alfheim cameras.
# These are fixed geometry seeds; this module intentionally has no tracker,
# ground-truth, ZXY, or evaluation dependencies.
SEED = {
    0: (
        np.float32([[315, 247], [620, 176], [474, 295], [817, 212]]),
        np.float32([[0, 13.84], [0, 54.16], [16.5, 13.84], [16.5, 54.16]]),
    ),
    1: (
        np.float32([[646, 96], [876, 778], [489, 200], [861, 200]]),
        np.float32([[52.5, 68], [52.5, 0], [43.35, 34], [61.65, 34]]),
    ),
    2: (
        np.float32([[405, 900], [0, 390], [1255, 273], [878, 280]]),
        np.float32([[52.5, 0], [52.5, 34], [105, 0], [88.5, 13.84]]),
    ),
}


class SeedCameraModel:
    def __init__(self, H):
        self.H = np.asarray(H, dtype=float)


def seed_model(cam: int) -> SeedCameraModel:
    if cam not in SEED:
        raise ValueError(f"unsupported camera: {cam}")
    pix, world = SEED[cam]
    H, _ = cv2.findHomography(pix, world, 0)
    if H is None:
        raise RuntimeError(f"could not construct seed homography for camera {cam}")
    return SeedCameraModel(H / H[2, 2])
