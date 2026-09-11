from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import alfheim_benchmark_v56_oos_globaltrack as v56

# Final causal quality gate. It uses only inference-time detector confidence and
# camera-support metadata already present on a candidate trajectory. A long path
# that is entirely single-camera and has low mean detector confidence is treated
# as an unreliable ghost track and is not allowed to consume one of the target
# track slots. No GT, IDs or evaluation signals enter this decision.
WEAK_MONO_CONF = 0.50
MIN_TRACK_SAMPLES = 6


def candidate_quality(path):
    conf = [float(d.get('conf', 0.0)) for _ti, _di, d in path]
    multi = [len(d.get('cams', ())) >= 2 for _ti, _di, d in path]
    return {
        'samples': len(path),
        'mean_conf': float(np.mean(conf)) if conf else 0.0,
        'multi_camera_fraction': float(np.mean(multi)) if multi else 0.0,
    }


def _blocked_neighbors(frames, path, blocked):
    for ti, _di, d in path:
        xy = np.asarray(d['xy'], float)
        lo = max(0, ti - 1)
        hi = min(len(frames), ti + 2)
        for tj in range(lo, hi):
            radius = 1.65 if tj == ti else 1.15
            for dj, other in enumerate(frames[tj]['fused']):
                if float(np.linalg.norm(np.asarray(other['xy'], float) - xy)) <= radius:
                    blocked.add((tj, dj))


def extract_tracks_v62(frames, n_tracks=10):
    blocked = set()
    tracks = []
    rejected = []
    for attempt in range(n_tracks * 3):
        p = v56.best_path(frames, blocked)
        if len(p) < MIN_TRACK_SAMPLES:
            break
        q = candidate_quality(p)
        weak = q['multi_camera_fraction'] < 1e-12 and q['mean_conf'] < WEAK_MONO_CONF
        if weak:
            rejected.append({'attempt': attempt, **q})
            # Remove this exact candidate so the next best causal path can be
            # searched without allowing the weak path to consume a track slot.
            for ti, di, _d in p:
                blocked.add((ti, di))
            continue

        tid = len(tracks)
        obs = []
        for ti, di, d in p:
            obs.append({
                't': float(frames[ti]['t']),
                'xy': np.asarray(d['xy'], float),
                'feat': np.asarray(d['feat'], float),
                'cams': tuple(d.get('cams', ())),
                'conf': float(d.get('conf', 0.)),
            })
        tracks.append({'track_id': tid, 'obs': obs})
        for ti, di, _d in p:
            blocked.add((ti, di))
        _blocked_neighbors(frames, p, blocked)
        if len(tracks) >= n_tracks:
            break
    return tracks, rejected


def main():
    ap = argparse.ArgumentParser(description='V62 final causal anonymous-track benchmark')
    for i in range(3):
        ap.add_argument(f'--cam{i}', required=True)
    ap.add_argument('--truth', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--geometry-dir', default=None)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    models = {}
    if args.geometry_dir:
        import alfheim_benchmark_v9 as v9
        gd = Path(args.geometry_dir)
        for cam in range(3):
            p = gd / f'cam{cam}_geometry_refinement.json'
            if p.exists():
                info = json.loads(p.read_text())
                H = info.get('chosen_h')
                if H is not None:
                    models[cam] = v9.CameraModel(np.asarray(H, float), None)

    frames, dur, diag = v56.build({0: args.cam0, 1: args.cam1, 2: args.cam2}, models=models)
    tb = v56.base.load_truth(args.truth, video_start=v56.v10.NATIVE_START)
    tracks, rejected = extract_tracks_v62(frames, 10)
    mapping, mapdiag = v56.calibration_mapping(tracks, tb)
    mm, rows = v56.mapped_eval(tracks, mapping, tb)
    anon = v56.anonymous_eval(tracks, tb)
    frame = v56.framewise_eval(frames, tb)

    r = {
        'version': 'v62-final-causal-quality-gated-track-extraction',
        'segment': '0059-0061',
        'duration_s': dur,
        'sample_fps': v56.FPS,
        'calibration_seconds': v56.CAL,
        'inference_uses_ground_truth': False,
        'truth_usage': 'ground truth is used only after anonymous trajectories are constructed for diagnostics/evaluation',
        'geometry_models_loaded': sorted(models.keys()),
        'detector_thresholds': {'red': v56.RED, 'confidence': v56.CONF, 'min_height_px': v56.MIN_H, 'top_k_per_camera': v56.TOP},
        'tracking_parameters': {
            'target_track_count': 10,
            'max_speed_m_s': v56.MAX_SPEED,
            'max_gap_s': v56.MAX_GAP_S,
            'skip_penalty': v56.SKIP_PENALTY,
            'birth_penalty': v56.BIRTH_PENALTY,
            'appearance_weight': v56.APP_WEIGHT,
            'same_frame_suppress_m': 1.65,
            'adjacent_frame_suppress_m': 1.15,
            'weak_monocular_mean_conf_cutoff': WEAK_MONO_CONF,
        },
        'rejected_candidate_diagnostics': rejected,
        'framewise_geometry_evaluation': frame,
        'anonymous_tracking_diagnostics': anon,
        'calibration_mapped_holdout_evaluation': mm,
        'track_identity_mapping': mapdiag,
        'track_count_extracted': len(tracks),
        'track_lengths': [len(t['obs']) for t in tracks],
        'detector_selection_diagnostics': diag,
    }
    (out / 'metrics.json').write_text(json.dumps(r, indent=2))
    pd.DataFrame(rows).to_csv(out / 'matched_observations.csv', index=False)
    pd.DataFrame([
        {
            'track_id': t['track_id'],
            'samples': len(t['obs']),
            'mean_conf': float(np.mean([o['conf'] for o in t['obs']])) if t['obs'] else 0.0,
            'multi_camera_fraction': float(np.mean([len(o['cams']) >= 2 for o in t['obs']])) if t['obs'] else 0.0,
        }
        for t in tracks
    ]).to_csv(out / 'tracks_summary.csv', index=False)
    print(json.dumps(r, indent=2), flush=True)


if __name__ == '__main__':
    main()
