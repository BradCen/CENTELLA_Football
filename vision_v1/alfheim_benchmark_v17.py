from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

import alfheim_benchmark_v13 as v13
import alfheim_benchmark_v9 as v9


TARGET_IDS = v13.TARGET_IDS


def _box_h_from_det(d):
    b = np.asarray(d.get('box', [0, 0, 0, 24]), float)
    return max(8.0, float(b[3] - b[1]))


def _obs_from_det(t, d):
    return {
        't': float(t),
        'foot': np.asarray(d['foot'], float),
        'seed_xy': np.asarray(d['seed_xy'], float),
        'feat': np.asarray(d['feat'], float),
        'kit_feat': np.asarray(d['kit_feat'], float),
        'conf': float(d['conf']),
        'box_h': _box_h_from_det(d),
    }


def _pix_velocity(tr):
    obs = tr.obs[-5:]
    if len(obs) < 2:
        return np.zeros(2, float)
    vals = []
    for a, b in zip(obs[:-1], obs[1:]):
        dt = float(b['t'] - a['t'])
        if 0.04 <= dt <= 0.40:
            v = (np.asarray(b['foot']) - np.asarray(a['foot'])) / dt
            n = float(np.linalg.norm(v))
            if n <= 900:
                vals.append(v)
    if not vals:
        return np.zeros(2, float)
    return np.median(np.asarray(vals, float), axis=0)


def _pix_predict(tr, t):
    last = tr.obs[-1]
    dt = max(0.0, float(t) - float(last['t']))
    return np.asarray(last['foot'], float) + _pix_velocity(tr) * dt


def _track_proto(tr, n=14):
    if not tr.obs:
        return None
    return np.median(np.asarray([o['feat'] for o in tr.obs[-n:]], float), axis=0)


def _cos(a, b):
    return v13.cosine_distance(a, b)


def track_camera(frames, cam):
    """Build conservative camera-space tracklets.

    The key rule is: ambiguous crossings fragment a track instead of allowing
    a silent identity switch. Post-processing can stitch fragments later.
    """
    tracks = []
    active = []
    next_id = 0
    prev_t = None

    for f in frames:
        t = float(f['t'])
        det = f['det']
        dt_frame = 0.125 if prev_t is None else max(0.04, t - prev_t)
        prev_t = t
        used_t, used_d = set(), set()

        if active and det:
            C = np.full((len(active), len(det)), 1e6, float)
            second_margin = np.full(len(active), 99.0, float)
            for i, tr in enumerate(active):
                last = tr.obs[-1]
                gap = max(0.0, t - float(last['t']))
                pp = _pix_predict(tr, t)
                proto = _track_proto(tr)
                h0 = float(last.get('box_h', 28.0))
                row = []
                for j, d in enumerate(det):
                    foot = np.asarray(d['foot'], float)
                    dp = float(np.linalg.norm(foot - pp))
                    scale = max(18.0, 0.78 * h0 + 52.0 * gap)
                    pn = dp / scale
                    if pn > 1.55:
                        continue
                    app = _cos(proto, np.asarray(d['feat'], float)) if proto is not None else 0.0
                    if app > 0.52 and pn > 0.45:
                        continue
                    h1 = _box_h_from_det(d)
                    size = abs(np.log(max(8.0, h1) / max(8.0, h0)))
                    # Seed/world geometry is weak and only used as a tie-breaker.
                    seed_pred = tr.pred_seed(t)
                    sw = float(np.linalg.norm(np.asarray(d['seed_xy'], float) - seed_pred))
                    if sw > 6.0 and pn > 0.65:
                        continue
                    cost = 1.55 * pn + 0.48 * max(0.0, app) + 0.25 * size + 0.045 * sw
                    C[i, j] = cost
                    row.append(cost)
                if len(row) >= 2:
                    rr = np.sort(np.asarray(row, float))
                    second_margin[i] = float(rr[1] - rr[0])

            ri, ci = linear_sum_assignment(C)
            for i, j in zip(ri, ci):
                if C[i, j] >= 1e5:
                    continue
                tr = active[i]
                # Ambiguous close alternatives at a crossing => fragment.
                if second_margin[i] < 0.10 and tr.miss_s < 0.20:
                    continue
                tr.obs.append(_obs_from_det(t, det[j]))
                tr.miss_s = 0.0
                used_t.add(i)
                used_d.add(j)

        for i, tr in enumerate(active):
            if i not in used_t:
                tr.miss_s += dt_frame

        for j, d in enumerate(det):
            if j in used_d:
                continue
            tr = v13.CameraTrack(next_id, cam, [_obs_from_det(t, d)], 0.0)
            next_id += 1
            tracks.append(tr)
            active.append(tr)

        # Short life deliberately prevents a stale track from jumping players.
        active = [tr for tr in active if tr.miss_s <= 0.55]

    return tracks


def track_gid_cost(tr, gid, truth_by, end_t=4.0):
    errs = []
    for o in tr.obs:
        if o['t'] > end_t:
            continue
        gt = {g['id']: g for g in v13.truth_at(truth_by, o['t'])}
        if gid not in gt:
            continue
        q = np.asarray([gt[gid]['x'], gt[gid]['y']], float)
        errs.append(float(np.linalg.norm(np.asarray(o['seed_xy']) - q)))
    if len(errs) < 2:
        return 99.0, len(errs)
    return float(np.median(errs)), len(errs)


def map_calibration_tracks(tracks, truth_by, calibration_seconds=4.0):
    """Map every strong calibration tracklet; allow fragments of one identity.

    We do not force one physical player to be represented by only one tracklet
    during calibration. Fragmentation is expected and safer than an ID switch.
    """
    mapping = {}
    diag = []
    claimed = {}
    candidates = []
    for tr in tracks:
        cal = [o for o in tr.obs if o['t'] <= calibration_seconds]
        if len(cal) < 2:
            continue
        vals = []
        for gid in TARGET_IDS:
            c, n = track_gid_cost(tr, gid, truth_by, calibration_seconds)
            vals.append((c, gid, n))
        vals.sort(key=lambda x: x[0])
        best, gid, n = vals[0]
        margin = vals[1][0] - vals[0][0] if len(vals) > 1 else 99.0
        latest = max(o['t'] for o in cal)
        if best <= 2.20 and margin >= 0.38 and n >= 2:
            candidates.append((latest, -best, n, tr, gid, best, margin))

    # A tracklet can map to only one ID, but an ID may have multiple non-overlap
    # fragments. They will be stitched later by temporal continuity.
    for latest, negbest, n, tr, gid, best, margin in sorted(candidates, reverse=True, key=lambda x:(x[0],x[1],x[2])):
        overlap = False
        for tid in claimed.get(gid, []):
            other = next(x for x in tracks if x.tid == tid)
            a0,a1=min(o['t'] for o in tr.obs),max(o['t'] for o in tr.obs)
            b0,b1=min(o['t'] for o in other.obs),max(o['t'] for o in other.obs)
            if min(a1,b1)-max(a0,b0) > 0.20:
                overlap=True; break
        if overlap:
            continue
        mapping[tr.tid]=gid
        claimed.setdefault(gid,[]).append(tr.tid)
        diag.append({'track_id':tr.tid,'gt_id':gid,'calibration_median_seed_m':float(best),'identity_margin_m':float(margin),'calibration_samples':int(n),'holdout_samples_before_stitch':len(tr.hold_obs(calibration_seconds))})
    return mapping, diag


def _endpoint_score(base, cand):
    last = base.obs[-1]
    first = cand.obs[0]
    gap = float(first['t'] - last['t'])
    if gap <= 0 or gap > 1.20:
        return None
    pp = _pix_predict(base, first['t'])
    h = max(18.0, 0.80 * float(last.get('box_h', 28.0)) + 48.0 * gap)
    pn = float(np.linalg.norm(np.asarray(first['foot']) - pp)) / h
    if pn > 1.55:
        return None
    app = _cos(_track_proto(base), _track_proto(cand))
    if app > 0.42:
        return None
    # World/seed continuity rejects a nearby rival with similar kit.
    sp = base.pred_seed(first['t'])
    sw = float(np.linalg.norm(np.asarray(first['seed_xy']) - sp))
    if sw > 4.4:
        return None
    size = abs(np.log(max(8.0,float(first.get('box_h',28.0)))/max(8.0,float(last.get('box_h',28.0)))))
    score = 1.45*pn + 0.75*max(0.0,app) + 0.10*sw + 0.22*size + 0.12*gap
    return score,pn,app,sw,gap


def stitch_post_calibration(tracks, mapping, calibration_seconds=4.0):
    """Offline fragment stitching without holdout ground truth."""
    by_id={tr.tid:tr for tr in tracks}
    mapped=dict(mapping)
    audit=[]

    # Work independently per identity, always extending the temporally latest
    # already-mapped fragment. Never re-use one candidate for two identities.
    used=set(mapped)
    for _ in range(12):
        proposals=[]
        for gid in TARGET_IDS:
            bases=[by_id[tid] for tid,g in mapped.items() if g==gid]
            if not bases:
                continue
            base=max(bases,key=lambda tr: tr.obs[-1]['t'])
            best=None
            for cand in tracks:
                if cand.tid in used or not cand.obs:
                    continue
                if cand.obs[0]['t'] <= base.obs[-1]['t']:
                    continue
                q=_endpoint_score(base,cand)
                if q is None:
                    continue
                score,pn,app,sw,gap=q
                if best is None or score<best[0]:
                    best=(score,cand,pn,app,sw,gap,base)
            if best is not None:
                proposals.append((best[0],gid,*best[1:]))
        if not proposals:
            break
        proposals.sort(key=lambda x:x[0])
        added=False
        taken=set()
        for score,gid,cand,pn,app,sw,gap,base in proposals:
            if cand.tid in taken or cand.tid in used:
                continue
            # Require a modest exclusivity margin vs other identities' latest
            # fragments before accepting a stitch.
            competitors=[]
            for ogid in TARGET_IDS:
                if ogid==gid: continue
                obases=[by_id[tid] for tid,g in mapped.items() if g==ogid]
                if not obases: continue
                ob=max(obases,key=lambda tr:tr.obs[-1]['t'])
                qq=_endpoint_score(ob,cand)
                if qq is not None: competitors.append(qq[0])
            if competitors and min(competitors) < score + 0.16:
                continue
            mapped[cand.tid]=gid;used.add(cand.tid);taken.add(cand.tid);added=True
            audit.append({'from_track':base.tid,'to_track':cand.tid,'gt_id':gid,'gap_s':float(gap),'pixel_norm':float(pn),'appearance_distance':float(app),'pred_distance_m':float(sw),'stitch_score':float(score)})
        if not added:
            break
    return mapped,audit


def main():
    v13.track_camera=track_camera
    v13.track_gid_cost=track_gid_cost
    v13.map_calibration_tracks=map_calibration_tracks
    v13.stitch_post_calibration=stitch_post_calibration
    v13.main()

    out=None
    for i,arg in enumerate(sys.argv[:-1]):
        if arg=='--out': out=Path(sys.argv[i+1]);break
    if out is not None:
        p=out/'metrics.json'
        if p.exists():
            m=json.loads(p.read_text(encoding='utf-8'))
            m['version']='v17-conservative-pixel-tracklet-stitching'
            m['tracking_method']='conservative camera-pixel tracklets; ambiguous crossings fragment; offline stitching uses pixel motion + appearance + world continuity; no holdout GT'
            p.write_text(json.dumps(m,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
