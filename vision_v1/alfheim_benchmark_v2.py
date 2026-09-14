from __future__ import annotations
import argparse, json
from pathlib import Path
import cv2
import numpy as np
import pandas as pd

from alfheim_benchmark import (
    detect_tiled, rough_project, fit_poly, poly_project,
    load_truth, truth_at, assign, summarize
)


def jersey_red_score(frame, box):
    """Fraction of red-dominant pixels in the torso area.

    Alfheim's sensor truth covers the red/white Tromso side, while YOLO sees
    both teams. This is deliberately image-only: no sensor IDs are used here.
    """
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = map(float, box)
    bw=max(2.0,x2-x1); bh=max(2.0,y2-y1)
    xa=max(0,int(x1+0.12*bw)); xb=min(w,int(x2-0.12*bw))
    ya=max(0,int(y1+0.02*bh)); yb=min(h,int(y1+0.60*bh))
    if xb<=xa or yb<=ya: return 0.0
    p=frame[ya:yb,xa:xb].astype(np.float32)
    B,G,R=p[:,:,0],p[:,:,1],p[:,:,2]
    red=(R>70) & (R>G*1.06+3) & (R>B*1.18+5)
    # Saturated reddish/orange pixels are useful under the stadium lighting.
    hsv=cv2.cvtColor(frame[ya:yb,xa:xb],cv2.COLOR_BGR2HSV)
    H,S,V=hsv[:,:,0],hsv[:,:,1],hsv[:,:,2]
    red_hsv=((H<14)|(H>166)) & (S>65) & (V>65)
    return float(np.maximum(red,red_hsv).mean())


def choose_team_threshold(frames, calibration_seconds):
    """Tune ONLY on calibration frames; holdout frames remain unseen."""
    candidates=[0.0,0.008,0.015,0.025,0.035,0.05,0.07,0.10,0.14]
    table=[]
    for thr in candidates:
        nd=ng=nm=0; costs=[]
        for f in frames:
            if f['t']>calibration_seconds: continue
            persons=[d for d in f['all_persons'] if d['team_score']>=thr]
            pix=np.array([d['foot'] for d in persons],float) if persons else np.empty((0,2))
            pred=rough_project(pix) if len(pix) else np.empty((0,2))
            matches=assign(pred,f['gt'],12.0)
            nd+=len(persons); ng+=len(f['gt']); nm+=len(matches)
            costs.extend(c for _,_,c in matches)
        precision=nm/max(1,nd); recall=nm/max(1,ng)
        f1=2*precision*recall/max(1e-9,precision+recall)
        mae=float(np.mean(costs)) if costs else 99.0
        score=f1-0.01*mae
        table.append({'threshold':thr,'detections':nd,'gt':ng,'matches':nm,
                      'precision_proxy':precision,'recall':recall,'f1':f1,
                      'rough_mae_m':mae,'score':score})
    best=max(table,key=lambda x:x['score'])
    return float(best['threshold']),table


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--video',required=True); ap.add_argument('--truth',required=True)
    ap.add_argument('--out',required=True); ap.add_argument('--sample-fps',type=float,default=2.0)
    ap.add_argument('--calibration-seconds',type=float,default=3.0)
    ap.add_argument('--model',default='yolo11n.pt')
    args=ap.parse_args(); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)

    from ultralytics import YOLO
    model=YOLO(args.model); truth_by=load_truth(args.truth)
    cap=cv2.VideoCapture(args.video)
    fps=float(cap.get(cv2.CAP_PROP_FPS) or 25); n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); dur=n/fps
    times=np.arange(.5,max(.51,dur-.25),1/args.sample_fps); frames=[]

    # Expensive inference is performed once. Threshold experiments reuse it.
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC,float(t*1000)); ok,frame=cap.read()
        if not ok: continue
        dets=detect_tiled(model,frame)
        persons=[d for d in dets if d['cls']=='person']
        for d in persons: d['team_score']=jersey_red_score(frame,d['box'])
        gt=truth_at(truth_by,float(t))
        frames.append({'t':float(t),'frame':frame,'all_persons':persons,'gt':gt})
        scores=sorted((d['team_score'] for d in persons),reverse=True)
        print(f't={t:.2f}s people={len(persons)} top_team_scores={[round(x,3) for x in scores[:12]]}',flush=True)
    cap.release()

    thr,tuning=choose_team_threshold(frames,args.calibration_seconds)
    (out/'team_threshold_tuning.json').write_text(json.dumps(tuning,indent=2),encoding='utf-8')
    print('selected_team_threshold=',thr,flush=True)
    for row in tuning: print('TEAM_TUNE',json.dumps(row),flush=True)

    cal_pix=[]; cal_world=[]
    for f in frames:
        persons=[d for d in f['all_persons'] if d['team_score']>=thr]
        f['persons']=persons
        pix=np.array([d['foot'] for d in persons],float) if persons else np.empty((0,2))
        f['pix']=pix
        rough=rough_project(pix) if len(pix) else np.empty((0,2)); f['rough']=rough
        if f['t']<=args.calibration_seconds:
            matches=assign(rough,f['gt'],12.0)
            for i,j,c in matches:
                cal_pix.append(pix[i]); cal_world.append([f['gt'][j]['x'],f['gt'][j]['y']])

    if len(cal_pix)<12: raise RuntimeError(f'Insufficient calibration pairs: {len(cal_pix)}')
    coef,mask=fit_poly(np.asarray(cal_pix),np.asarray(cal_world))
    np.save(out/'pixel_to_world_poly.npy',coef)
    print('calibration_pairs=',len(cal_pix),'inliers=',int(mask.sum()),flush=True)

    eval_rows=[]; total_gt=0; total_det=0; annotated=None
    for f in frames:
        if f['t']<=args.calibration_seconds: continue
        pred=poly_project(f['pix'],coef) if len(f['pix']) else np.empty((0,2))
        gt=f['gt']; matches=assign(pred,gt,7.5); total_gt+=len(gt); total_det+=len(pred)
        for i,j,c in matches:
            g=gt[j]
            eval_rows.append({'t':f['t'],'det_index':i,'gt_id':g['id'],
                'pred_x':pred[i,0],'pred_y':pred[i,1],'truth_x':g['x'],'truth_y':g['y'],
                'position_error_m':c,'truth_speed':g['speed'],'truth_total_distance':g['total_distance'],
                'pixel_x':f['pix'][i,0],'pixel_y':f['pix'][i,1],
                'team_score':f['persons'][i]['team_score']})
        if annotated is None:
            annotated=f['frame'].copy()
            for d in f['all_persons']:
                x1,y1,x2,y2=map(int,d['box'])
                selected=d['team_score']>=thr
                color=(0,255,0) if selected else (255,180,0)
                cv2.rectangle(annotated,(x1,y1),(x2,y2),color,2)
                cv2.putText(annotated,f"{d['team_score']:.2f}",(x1,y1-4),0,.45,color,1)
            for i,j,c in matches:
                x,y=map(int,f['pix'][i]); pid=gt[j]['id']
                cv2.circle(annotated,(x,y),10,(0,0,255),3)
                cv2.putText(annotated,f'GT{pid} e={c:.1f}m',(x+7,y-7),0,.65,(0,0,255),2)

    pd.DataFrame(eval_rows).to_csv(out/'matched_observations.csv',index=False)
    metrics=summarize(eval_rows,total_gt,total_det)
    metrics.update({'version':'v2-team-filter','video_duration_s':dur,'sample_fps':args.sample_fps,
        'calibration_seconds':args.calibration_seconds,'calibration_pairs':len(cal_pix),
        'calibration_inliers':int(mask.sum()),'model':args.model,'team_threshold':thr})
    (out/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    if annotated is not None: cv2.imwrite(str(out/'annotated_eval_frame.jpg'),annotated)
    print(json.dumps(metrics,indent=2),flush=True)

if __name__=='__main__': main()
