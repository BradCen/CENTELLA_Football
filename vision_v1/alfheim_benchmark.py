from __future__ import annotations
import argparse, json, math
from pathlib import Path
from collections import defaultdict
import cv2
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

PLAYER_IDS = [1,2,5,7,8,9,10,13,14,15]
VIDEO_START = pd.Timestamp('2013-11-03 18:01:12.794293')
WORLD_CORNERS = np.array([[0,0],[105,0],[105,68],[0,68]], np.float32)
PIXEL_CORNERS = np.array([[260,1050],[4050,1070],[3450,610],[1180,610]], np.float32)
PITCH_POLY = PIXEL_CORNERS.astype(np.int32)

def iou(a,b):
    x1=max(a[0],b[0]); y1=max(a[1],b[1]); x2=min(a[2],b[2]); y2=min(a[3],b[3])
    inter=max(0,x2-x1)*max(0,y2-y1)
    aa=max(0,a[2]-a[0])*max(0,a[3]-a[1]); bb=max(0,b[2]-b[0])*max(0,b[3]-b[1])
    return inter/(aa+bb-inter+1e-9)

def nms(dets, thr=.45):
    dets=sorted(dets,key=lambda d:d['conf'],reverse=True); keep=[]
    while dets:
        d=dets.pop(0); keep.append(d)
        dets=[x for x in dets if x['cls']!=d['cls'] or iou(x['box'],d['box'])<thr]
    return keep

def detect_tiled(model, frame, conf=.08, imgsz=960):
    h,w=frame.shape[:2]
    y0,y1=470,min(h,1160); tile_w=1280; stride=1020
    starts=list(range(0,max(1,w-tile_w+1),stride))
    if not starts or starts[-1]+tile_w<w: starts.append(max(0,w-tile_w))
    out=[]
    for x0 in starts:
        crop=frame[y0:y1,x0:x0+tile_w]
        r=model.predict(crop, imgsz=imgsz, conf=conf, iou=.55, classes=[0,32], verbose=False, device='cpu')[0]
        names=r.names
        if r.boxes is None: continue
        for b in r.boxes:
            cls=int(b.cls.item()); score=float(b.conf.item()); name=names[cls]
            xy=b.xyxy[0].cpu().numpy().astype(float)
            box=(xy[0]+x0,xy[1]+y0,xy[2]+x0,xy[3]+y0)
            foot=((box[0]+box[2])/2,box[3])
            if name=='person':
                if cv2.pointPolygonTest(PITCH_POLY,(float(foot[0]),float(foot[1])),False)<0: continue
                label='person'
            elif name=='sports ball': label='ball'
            else: continue
            out.append({'box':box,'conf':score,'cls':label,'foot':foot})
    return nms(out)

def homography_pixel_to_world():
    H,_=cv2.findHomography(PIXEL_CORNERS,WORLD_CORNERS)
    return H

def rough_project(points):
    H=homography_pixel_to_world()
    arr=np.asarray(points,np.float32).reshape(-1,1,2)
    return cv2.perspectiveTransform(arr,H).reshape(-1,2)

def features(points, w=4450., h=2000.):
    p=np.asarray(points,float)
    u=(p[:,0]-w/2)/(w/2); v=(p[:,1]-h/2)/(h/2)
    return np.column_stack([np.ones(len(p)),u,v,u*u,u*v,v*v,u**3,(u*u)*v,u*(v*v),v**3])

def fit_poly(pixel_pts, world_pts):
    X=features(pixel_pts); Y=np.asarray(world_pts,float); mask=np.ones(len(X),bool)
    coef=None
    for _ in range(4):
        coef=np.linalg.lstsq(X[mask],Y[mask],rcond=None)[0]
        pred=X@coef; res=np.linalg.norm(pred-Y,axis=1)
        med=np.median(res[mask]); mad=np.median(np.abs(res[mask]-med))+1e-6
        new=(res < min(8.0, med+3.5*1.4826*mad))
        if new.sum()<12: break
        if np.array_equal(new,mask): break
        mask=new
    return coef,mask

def poly_project(pixel_pts, coef): return features(pixel_pts)@coef

def load_truth(csv_path, video_start=VIDEO_START):
    cols=['time','id','x','y','heading','direction','energy','speed','total_distance']
    df=pd.read_csv(csv_path,header=None,names=cols)
    df=df[df.id.isin(PLAYER_IDS)].copy(); df['dt']=pd.to_datetime(df.time,format='mixed')
    df['t']=(df.dt-video_start).dt.total_seconds()
    by={}
    for pid,g in df.groupby('id'):
        g=g.sort_values('t'); by[int(pid)]={k:g[k].to_numpy(float) for k in ['t','x','y','speed','total_distance']}
    return by

def truth_at(by,t):
    rows=[]
    for pid,d in by.items():
        if t<d['t'][0] or t>d['t'][-1]: continue
        rows.append({'id':pid,'x':float(np.interp(t,d['t'],d['x'])),'y':float(np.interp(t,d['t'],d['y'])),'speed':float(np.interp(t,d['t'],d['speed'])),'total_distance':float(np.interp(t,d['t'],d['total_distance']))})
    return rows

def assign(det_world, truth, max_cost=14.):
    if len(det_world)==0 or len(truth)==0:return []
    gt=np.array([[x['x'],x['y']] for x in truth],float)
    cost=np.linalg.norm(det_world[:,None,:]-gt[None,:,:],axis=2)
    ii,jj=linear_sum_assignment(cost)
    return [(int(i),int(j),float(cost[i,j])) for i,j in zip(ii,jj) if cost[i,j]<=max_cost]

def summarize(eval_rows, total_gt, total_detections):
    if not eval_rows:return {'matched':0,'gt_points':total_gt,'detections':total_detections,'recall':0}
    e=pd.DataFrame(eval_rows)
    pos=e.position_error_m.to_numpy(float)
    result={'matched':int(len(e)),'gt_points':int(total_gt),'detections':int(total_detections),'recall':float(len(e)/max(1,total_gt)),'precision_proxy':float(len(e)/max(1,total_detections)),'position_mae_m':float(np.mean(pos)),'position_rmse_m':float(np.sqrt(np.mean(pos**2))),'position_p95_m':float(np.percentile(pos,95))}
    speed_errors=[]; distance=[]
    for pid,g in e.sort_values('t').groupby('gt_id'):
        g=g.drop_duplicates('t').sort_values('t')
        if len(g)<2: continue
        dt=np.diff(g.t.to_numpy(float)); xy=g[['pred_x','pred_y']].to_numpy(float)
        ds=np.linalg.norm(np.diff(xy,axis=0),axis=1); v=ds/np.maximum(dt,1e-6)
        truth_v=g.truth_speed.to_numpy(float)[1:]; good=(dt<=1.1)&(v<15)
        speed_errors.extend((v[good]-truth_v[good]).tolist())
        pred_dist=float(ds[good].sum()); td=g.truth_total_distance.to_numpy(float); truth_dist=float(np.maximum(0,np.diff(td)[good]).sum())
        distance.append((int(pid),pred_dist,truth_dist))
    if speed_errors:
        se=np.asarray(speed_errors,float); result.update(speed_mae_mps=float(np.mean(np.abs(se))),speed_rmse_mps=float(np.sqrt(np.mean(se**2))),speed_bias_mps=float(np.mean(se)),speed_samples=int(len(se)))
    if distance:
        pred=sum(x[1] for x in distance); tru=sum(x[2] for x in distance); result.update(distance_pred_m=pred,distance_truth_m=tru,distance_error_pct=float(100*(pred-tru)/max(tru,1e-6)),per_player_distance=[{'id':a,'pred_m':b,'truth_m':c} for a,b,c in distance])
    return result

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--video',required=True); ap.add_argument('--truth',required=True); ap.add_argument('--out',required=True); ap.add_argument('--sample-fps',type=float,default=2.0); ap.add_argument('--calibration-seconds',type=float,default=3.0); ap.add_argument('--model',default='yolo11n.pt')
    args=ap.parse_args(); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    from ultralytics import YOLO
    model=YOLO(args.model); truth_by=load_truth(args.truth)
    cap=cv2.VideoCapture(args.video); fps=float(cap.get(cv2.CAP_PROP_FPS) or 25); n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); dur=n/fps
    times=np.arange(.5,max(.51,dur-.25),1/args.sample_fps); frames=[]; cal_pix=[]; cal_world=[]
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC,float(t*1000)); ok,frame=cap.read()
        if not ok: continue
        dets=detect_tiled(model,frame); persons=[d for d in dets if d['cls']=='person']; pix=np.array([d['foot'] for d in persons],float) if persons else np.empty((0,2)); rough=rough_project(pix) if len(pix) else np.empty((0,2)); gt=truth_at(truth_by,float(t)); matches=assign(rough,gt,14)
        if t<=args.calibration_seconds:
            for i,j,c in matches: cal_pix.append(pix[i]); cal_world.append([gt[j]['x'],gt[j]['y']])
        frames.append({'t':float(t),'frame':frame,'persons':persons,'pix':pix,'rough':rough,'gt':gt}); print(f't={t:.2f}s persons={len(persons)} rough_matches={len(matches)}',flush=True)
    cap.release()
    if len(cal_pix)<12: raise RuntimeError(f'Insufficient calibration pairs: {len(cal_pix)}')
    coef,mask=fit_poly(np.asarray(cal_pix),np.asarray(cal_world)); print('calibration pairs',len(cal_pix),'inliers',int(mask.sum()),flush=True); np.save(out/'pixel_to_world_poly.npy',coef)
    eval_rows=[]; total_gt=0; total_det=0; annotated=None
    for f in frames:
        if f['t']<=args.calibration_seconds: continue
        pred=poly_project(f['pix'],coef) if len(f['pix']) else np.empty((0,2)); gt=f['gt']; matches=assign(pred,gt,7.5); total_gt+=len(gt); total_det+=len(pred)
        for i,j,c in matches:
            g=gt[j]; eval_rows.append({'t':f['t'],'det_index':i,'gt_id':g['id'],'pred_x':pred[i,0],'pred_y':pred[i,1],'truth_x':g['x'],'truth_y':g['y'],'position_error_m':c,'truth_speed':g['speed'],'truth_total_distance':g['total_distance'],'pixel_x':f['pix'][i,0],'pixel_y':f['pix'][i,1]})
        if annotated is None:
            annotated=f['frame'].copy()
            for d in f['persons']:
                x1,y1,x2,y2=map(int,d['box']); cv2.rectangle(annotated,(x1,y1),(x2,y2),(255,180,0),2)
            for i,j,c in matches:
                x,y=map(int,f['pix'][i]); pid=gt[j]['id']; cv2.circle(annotated,(x,y),12,(0,0,255),3); cv2.putText(annotated,f'GT{pid} e={c:.1f}m',(x+8,y-8),0,.7,(0,0,255),2)
    pd.DataFrame(eval_rows).to_csv(out/'matched_observations.csv',index=False); metrics=summarize(eval_rows,total_gt,total_det); metrics.update({'video_duration_s':dur,'sample_fps':args.sample_fps,'calibration_seconds':args.calibration_seconds,'calibration_pairs':len(cal_pix),'calibration_inliers':int(mask.sum()),'model':args.model}); (out/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    if annotated is not None: cv2.imwrite(str(out/'annotated_eval_frame.jpg'),annotated)
    print(json.dumps(metrics,indent=2),flush=True)

if __name__=='__main__': main()
