from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import alfheim_benchmark_v56_oos_globaltrack as v56

# V61 keeps V56's detector, geometry, fusion and edge model intact. The only
# tracker refinement is causal multi-track spatial suppression: after a path is
# selected, nearby nodes in the same/adjacent sampled frames are made
# unavailable to subsequent paths. This targets duplicate tracklets without
# using identities or ground truth during inference.
SAME_FRAME_SUPPRESS_M = 1.65
ADJ_FRAME_SUPPRESS_M = 1.15
MAX_SUPPRESS_FRAME_DELTA = 1


def _blocked_neighbors(frames, path, blocked):
    for ti, _di, d in path:
        xy = np.asarray(d['xy'], float)
        lo = max(0, ti - MAX_SUPPRESS_FRAME_DELTA)
        hi = min(len(frames), ti + MAX_SUPPRESS_FRAME_DELTA + 1)
        for tj in range(lo, hi):
            radius = SAME_FRAME_SUPPRESS_M if tj == ti else ADJ_FRAME_SUPPRESS_M
            for dj, other in enumerate(frames[tj]['fused']):
                if float(np.linalg.norm(np.asarray(other['xy'], float) - xy)) <= radius:
                    blocked.add((tj, dj))


def extract_tracks_v61(frames, n_tracks=10):
    blocked = set()
    tracks = []
    for tid in range(n_tracks * 2):
        p = v56.best_path(frames, blocked)
        if len(p) < 6:
            break
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
        # Keep exact node blocking plus causal spatial NMS around the accepted
        # trajectory. No truth/GT, labels or future frames are consulted.
        for ti, di, _d in p:
            blocked.add((ti, di))
        _blocked_neighbors(frames, p, blocked)
        if len(tracks) >= n_tracks:
            break
    return tracks


def main():
    ap = argparse.ArgumentParser(description='V61 final causal anonymous-track refinement around V56')
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
        gd = Path(args.geometry_dir)
        for cam in range(3):
            p = gd / f'cam{cam}_geometry_refinement.json'
            if p.exists():
                info = json.loads(p.read_text())
                H = info.get('chosen_h')
                if H is not None:
                    import alfheim_benchmark_v9 as v9
                    models[cam] = v9.CameraModel(np.asarray(H, float), None)

    frames, dur, diag = v56.build({0: args.cam0, 1: args.cam1, 2: args.cam2}, models=models)
    tb = v56.base.load_truth(args.truth, video_start=v56.v10.NATIVE_START)

    tracks = extract_tracks_v61(frames, 10)
    mapping, mapdiag = v56.calibration_mapping(tracks, tb)
    mm, rows = v56.mapped_eval(tracks, mapping, tb)
    anon = v56.anonymous_eval(tracks, tb)
    frame = v56.framewise_eval(frames, tb)

    r = {
        'version': 'v61-final-causal-spatial-track-suppression',
        'segment': '0059-0061',
        'duration_s': dur,
        'sample_fps': v56.FPS,
        'calibration_seconds': v56.CAL,
        'inference_uses_ground_truth': False,
        'truth_usage': 'ground truth is used only after anonymous trajectories are constructed for diagnostics/evaluation',
        'geometry_models_loaded': sorted(models.keys()),
        'detector_thresholds': {
            'red': v56.RED,
            'confidence': v56.CONF,
            'min_height_px': v56.MIN_H,
            'top_k_per_camera': v56.TOP,
        },
        'tracking_parameters': {
            'target_track_count': 10,
            'max_speed_m_s': v56.MAX_SPEED,
            'max_gap_s': v56.MAX_GAP_S,
            'skip_penalty': v56.SKIP_PENALTY,
            'birth_penalty': v56.BIRTH_PENALTY,
            'appearance_weight': v56.APP_WEIGHT,
            'same_frame_suppress_m': SAME_FRAME_SUPPRESS_M,
            'adjacent_frame_suppress_m': ADJ_FRAME_SUPPRESS_M,
        },
        'framewise_geometry_evaluation': frame,
        'anonymous_tracking_diagnostics': anon,
        'calibration_mapped_holdout_evaluation': mm,
        'track_identity_mapping': mapdiag,
        'track_count_extracted': len(tracks),
        'track_lengths': [len(t['obs']) for t in tracks],
        'detector_selection_diagnostics': diag,
    }

    (out / 'metrics.json').write_text(json.dumps(r, indent=2))
    import pandas as pd
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
