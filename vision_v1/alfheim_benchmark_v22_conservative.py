from __future__ import annotations

import json
import sys
from pathlib import Path
import numpy as np

import alfheim_benchmark_v19 as v19

CAL_SPLIT_S = 7.0


def conservative_detector_correct(states, dets, gray, model, bias, t):
    """Correct optical-flow drift without allowing healthy tracks to jump IDs.

    V21 showed perfect holdout coverage but very large position error. The main
    risk is detector correction overwriting a healthy optical lock during
    player crossings. This version makes corrections deliberately conservative:
    healthy tracks need meaningful box overlap and a small world-space jump;
    larger corrections are allowed only after flow has actually failed.
    No holdout ground truth is consulted here.
    """
    gids = [g for g, s in states.items() if s.get('bbox') is not None and s.get('fail_frames', 0) <= 12]
    if not gids or not dets:
        return 0
    C = np.full((len(gids), len(dets)), 1e6, float)
    for ii, gid in enumerate(gids):
        s = states[gid]
        b = np.asarray(s['bbox'], float)
        h = max(12.0, b[3] - b[1])
        c0 = np.asarray([(b[0] + b[2]) / 2., (b[1] + b[3]) / 2.])
        proto = np.median(np.asarray(s['cal_feats'], float), axis=0) if s.get('cal_feats') else None
        flow_world = model.project(np.asarray([v19.foot_of(b)], float))[0] + bias
        failed = int(s.get('fail_frames', 0)) >= 2
        for j, d in enumerate(dets):
            db = np.asarray(d['box'], float)
            c1 = np.asarray([(db[0] + db[2]) / 2., (db[1] + db[3]) / 2.])
            dn = float(np.linalg.norm(c1 - c0) / h)
            iou = v19.box_iou(b, db)
            app = v19.cosdist(proto, d['feat']) if proto is not None else 0.0
            dw = model.project(np.asarray([d['foot']], float))[0] + bias
            world_gap = float(np.linalg.norm(dw - flow_world))

            # Healthy optical tracks: only small, overlapping detector updates.
            if not failed:
                if iou < 0.18 or dn > 0.30 or world_gap > 1.65 or app > 0.38:
                    continue
            # Failed tracks can recover, but still cannot teleport to another player.
            else:
                if dn > 0.65 or world_gap > 2.50 or app > 0.46:
                    continue

            C[ii, j] = 1.20 * dn + 0.75 * (1.0 - iou) + 0.70 * max(0., app) + 0.18 * world_gap

    ri, ci = v19.linear_sum_assignment(C)
    n = 0
    for ii, j in zip(ri, ci):
        if C[ii, j] >= 1e5:
            continue
        gid = gids[ii]
        s = states[gid]
        failed = int(s.get('fail_frames', 0)) >= 2
        limit = 2.25 if failed else 1.35
        if C[ii, j] > limit:
            continue
        d = dets[j]
        old = np.asarray(s['bbox'], float)
        new = np.asarray(d['box'], float)
        blend = 0.72 if failed else 0.38
        dd = dict(d)
        dd['box'] = blend * new + (1.0 - blend) * old
        v19.reset_state(s, gray, dd, t, calibration=False)
        n += 1
    return n


def main():
    v19.CAL_SPLIT = CAL_SPLIT_S
    v19.detector_correct = conservative_detector_correct
    v19.main()

    out = None
    for i, a in enumerate(sys.argv[:-1]):
        if a == '--out':
            out = Path(sys.argv[i + 1])
            break
    if out:
        p = out / 'metrics.json'
        if p.exists():
            m = json.loads(p.read_text(encoding='utf-8'))
            m['version'] = 'v22-conservative-correction'
            m['calibration_seconds'] = 10.0
            m['geometry_train_split_seconds'] = CAL_SPLIT_S
            p.write_text(json.dumps(m, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
