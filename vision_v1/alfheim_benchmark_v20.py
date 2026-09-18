from __future__ import annotations

import json
import sys
from pathlib import Path

import alfheim_benchmark_v19 as v19


def no_detector_correction(states, dets, gray, model, bias, t):
    # Ablation: once identity has been assigned in the legal calibration window,
    # never allow a detector to overwrite the optical lock in the holdout.
    return 0


def main():
    v19.detector_correct = no_detector_correction
    v19.main()
    out=None
    for i,a in enumerate(sys.argv[:-1]):
        if a=='--out':out=Path(sys.argv[i+1]);break
    if out:
        p=out/'metrics.json'
        if p.exists():
            m=json.loads(p.read_text(encoding='utf-8'))
            m['version']='v20-pure-optical-lock-ablation'
            m['tracking_method']='calibration-locked per-player Lucas-Kanade optical flow; detector cannot modify identity or bbox after t=4s'
            m['holdout_detector_corrections']=0
            p.write_text(json.dumps(m,indent=2),encoding='utf-8')

if __name__=='__main__':main()
