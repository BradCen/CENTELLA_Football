from __future__ import annotations

import math
import numpy as np
from scipy.optimize import linear_sum_assignment

import alfheim_benchmark_v5 as v5


def build_tracks_pixel_strict(frames, selected, max_age=1.25):
    """V6: conservative image-space association.

    The V5 gate was deliberately permissive and admitted a measured 188 px
    identity jump in 0.17 s. V6 makes motion continuity the primary identity
    cue and only widens the gate after genuine detector misses.
    """
    tracks=[]; next_id=1
    for fi,f in enumerate(frames):
        t=float(f['t'])
        dets=[d for d in f['all_persons'] if d['cluster'] in selected]
        active=[tr for tr in tracks if t-tr.last_seen_t<=max_age]
        for tr in active:
            dt=max(0.0,t-tr.state_t)
            if dt>0:
                tr.state,tr.cov=v5.kf_predict(tr.state,tr.cov,dt)
                tr.state_t=t
        matched_dets=set(); matched_tracks=set()
        if active and dets:
            C=np.full((len(active),len(dets)),1e6,float)
            for i,tr in enumerate(active):
                pred=tr.state[:2]
                age=max(0.0,t-tr.last_seen_t)
                ph=v5.box_height(tr.last_box)
                for j,d in enumerate(dets):
                    z=np.asarray(d['foot'],float); dh=v5.box_height(d['box'])
                    spatial=float(np.linalg.norm(z-pred))
                    scale=.5*(ph+dh)
                    # ~0.17 s normal step: typically tens, not hundreds, of px.
                    gate=max(38.0,1.05*scale)+48.0*min(age,1.25)
                    app=v5.cosine_distance(tr.feat,d['feat'])
                    size_pen=abs(math.log(max(1e-3,dh/ph)))
                    same_cluster=int(d['cluster'])==tr.cluster
                    # Reject physically/visually implausible identity swaps.
                    if spatial>gate or app>0.62 or size_pen>0.85:
                        continue
                    C[i,j]=2.9*(spatial/gate)+1.25*app+.28*size_pen+(0.22 if not same_cluster else 0.0)
            ri,ci=linear_sum_assignment(C)
            for i,j in zip(ri,ci):
                if C[i,j]>2.65: continue
                tr=active[int(i)]; d=dets[int(j)]
                z=np.asarray(d['foot'],float); h=v5.box_height(d['box'])
                sigma=max(3.5,min(10.0,.11*h))
                tr.state,tr.cov=v5.kf_update(tr.state,tr.cov,z,sigma)
                tr.last_seen_t=t; tr.last_box=tuple(d['box']); tr.hits+=1; tr.misses=0
                tr.feat=.94*tr.feat+.06*np.asarray(d['feat'],float)
                tr.obs.append({'fi':fi,'t':t,'pix':z.copy(),'box':tuple(d['box']),
                               'conf':float(d.get('conf',0.0)),'cluster':int(d['cluster'])})
                matched_dets.add(int(j)); matched_tracks.add(tr.tid)
        for tr in active:
            if tr.tid not in matched_tracks: tr.misses+=1
        for j,d in enumerate(dets):
            if j in matched_dets or float(d.get('conf',0.0))<0.085: continue
            tracks.append(v5.make_track(next_id,fi,t,d)); next_id+=1
    return tracks


def candidate_motion_stats(tr, gid, frames, calibration_seconds):
    obs=[o for o in tr.obs if o['t']<=calibration_seconds]
    errs=[]; velerrs=[]
    prev=None
    for o in obs:
        gt={g['id']:g for g in frames[o['fi']]['gt']}
        if gid not in gt: continue
        g=gt[gid]; truth=np.array([g['x'],g['y']],float)
        errs.append(float(np.linalg.norm(o['xy']-truth)))
        if prev is not None:
            po,ptruth=prev; dt=o['t']-po['t']
            if 0.10<=dt<=0.75:
                pv=(o['xy']-po['xy'])/dt
                tv=(truth-ptruth)/dt
                # Vector error distinguishes nearby players moving apart.
                velerrs.append(float(np.linalg.norm(pv-tv)))
        prev=(o,truth)
    if len(errs)<4: return None
    med=float(np.median(errs)); p90=float(np.percentile(errs,90))
    vmed=float(np.median(velerrs)) if velerrs else 99.0
    return med,p90,vmed,len(errs)


def map_tracks_to_truth_motion(tracks,frames,calibration_seconds,max_median=2.8):
    cal_tracks=[tr for tr in tracks
                if sum(o['t']<=calibration_seconds for o in tr.obs)>=4
                and any(o['t']>calibration_seconds for o in tr.obs)]
    gt_ids=sorted({g['id'] for f in frames if f['t']<=calibration_seconds for g in f['gt']})
    if not cal_tracks or not gt_ids: return {},[]
    C=np.full((len(cal_tracks),len(gt_ids)),1e5,float); detail={}
    for i,tr in enumerate(cal_tracks):
        for j,gid in enumerate(gt_ids):
            s=candidate_motion_stats(tr,gid,frames,calibration_seconds)
            if s is None: continue
            med,p90,vmed,n=s
            # Position remains dominant; velocity resolves close/ambiguous players.
            score=med+.22*p90+.32*min(vmed,8.0)+.45/n
            C[i,j]=score; detail[(i,j)]=(med,p90,vmed,n,score)
    ri,ci=linear_sum_assignment(C)
    mapping={}; rows=[]
    for i,j in zip(ri,ci):
        info=detail.get((int(i),int(j)))
        if info is None: continue
        med,p90,vmed,n,score=info
        # Only identities that are actually established in calibration enter
        # the frozen holdout. Ambiguous IDs are reported, not guessed.
        if med>max_median or p90>4.5 or vmed>4.5: continue
        # Require a margin over the next plausible identity for this track.
        vals=np.sort(C[int(i)][C[int(i)]<1e4])
        margin=float(vals[1]-vals[0]) if len(vals)>1 else 99.0
        if margin<0.35: continue
        tr=cal_tracks[int(i)]; gid=gt_ids[int(j)]
        mapping[tr.tid]=gid
        rows.append({'track_id':tr.tid,'gt_id':gid,'calibration_median_m':med,
                     'calibration_p90_m':p90,'calibration_velocity_median_error_mps':vmed,
                     'calibration_samples':n,'assignment_score':score,'identity_margin':margin,
                     'track_total_samples':len(tr.obs),
                     'track_holdout_samples':sum(o['t']>calibration_seconds for o in tr.obs)})
    return mapping,rows


# Patch V5's main so the exact same detector, geometry and evaluator are used.
v5.build_tracks_pixel=build_tracks_pixel_strict
v5.map_tracks_to_truth=map_tracks_to_truth_motion

if __name__=='__main__':
    v5.main()
