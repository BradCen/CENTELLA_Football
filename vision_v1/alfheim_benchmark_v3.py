from __future__ import annotations
import argparse, itertools, json
from pathlib import Path
import cv2
import numpy as np
import pandas as pd
from scipy.cluster.vq import kmeans2, vq
from scipy.signal import savgol_filter

from alfheim_benchmark import detect_tiled, rough_project, load_truth, truth_at, assign
from alfheim_benchmark_v2 import jersey_red_score


def appearance_feature(frame, box):
    h,w=frame.shape[:2]; x1,y1,x2,y2=map(float,box)
    bw=max(2.,x2-x1); bh=max(2.,y2-y1)
    xa=max(0,int(x1+.10*bw)); xb=min(w,int(x2-.10*bw))
    ya=max(0,int(y1+.02*bh)); yb=min(h,int(y1+.62*bh))
    crop=frame[ya:yb,xa:xb]
    if crop.size==0: return np.zeros(20,np.float32)
    crop=cv2.resize(crop,(28,48),interpolation=cv2.INTER_AREA)
    hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV); H,S,V=cv2.split(hsv)
    sat=S.astype(float)/255.; valid=V>35
    hist,_=np.histogram(H[valid],bins=12,range=(0,180),weights=sat[valid])
    hist=hist/(hist.sum()+1e-6)
    B,G,R=[crop[:,:,i].astype(float) for i in range(3)]
    total=R+G+B+1e-6
    chrom=np.array([(R/total).mean(),(G/total).mean(),(B/total).mean()],float)
    white=float(((S<55)&(V>135)).mean()); dark=float((V<90).mean())
    red=jersey_red_score(frame,box)
    brightness=float(V.mean()/255.)
    return np.r_[hist,chrom,white,dark,red,brightness].astype(np.float32)


def cluster_appearance(frames, calibration_seconds, k=4):
    feats=[]; refs=[]
    for fi,f in enumerate(frames):
        if f['t']>calibration_seconds: continue
        for di,d in enumerate(f['all_persons']):
            feats.append(d['feat']); refs.append((fi,di))
    X=np.asarray(feats,float); mean=X.mean(0); std=X.std(0)+1e-5; Z=(X-mean)/std
    rng=np.random.default_rng(42)
    # deterministic-ish seed points spread through calibration detections
    seeds=Z[rng.choice(len(Z),size=k,replace=False)]
    centers,labels=kmeans2(Z,seeds,minit='matrix',iter=60)
    for (fi,di),lab in zip(refs,labels): frames[fi]['all_persons'][di]['cluster']=int(lab)
    # Assign every holdout detection to calibration-fitted centers.
    for f in frames:
        for d in f['all_persons']:
            if 'cluster' not in d:
                z=(d['feat']-mean)/std; d['cluster']=int(vq(np.asarray([z]),centers)[0][0])
    return centers,mean,std


def choose_cluster_subset(frames, calibration_seconds, k=4):
    table=[]
    clusters=range(k)
    for r in range(1,k+1):
        for subset in itertools.combinations(clusters,r):
            subset=set(subset); nd=ng=nm=0; costs=[]
            for f in frames:
                if f['t']>calibration_seconds: continue
                p=[d for d in f['all_persons'] if d['cluster'] in subset]
                pix=np.asarray([d['foot'] for d in p],float) if p else np.empty((0,2))
                pred=rough_project(pix) if len(pix) else np.empty((0,2)); m=assign(pred,f['gt'],12.)
                nd+=len(p); ng+=len(f['gt']); nm+=len(m); costs += [c for _,_,c in m]
            precision=nm/max(1,nd); recall=nm/max(1,ng); f1=2*precision*recall/max(1e-9,precision+recall)
            mae=float(np.mean(costs)) if costs else 99.; score=f1-.008*mae
            table.append({'clusters':sorted(subset),'detections':nd,'gt':ng,'matches':nm,'precision_proxy':precision,'recall':recall,'f1':f1,'rough_mae_m':mae,'score':score})
    best=max(table,key=lambda x:x['score'])
    return set(best['clusters']),table


def geom_features(points,w=4450.,h=2000.):
    p=np.asarray(points,float); u=(p[:,0]-w/2)/(w/2); v=(p[:,1]-h/2)/(h/2)
    return np.column_stack([np.ones(len(p)),u,v,u*u,u*v,v*v])


def fit_geometry(pixel,world):
    X=geom_features(pixel); Y=np.asarray(world,float); mask=np.ones(len(X),bool)
    coef=None
    for _ in range(6):
        coef=np.linalg.lstsq(X[mask],Y[mask],rcond=None)[0]
        res=np.linalg.norm(X@coef-Y,axis=1); med=np.median(res[mask]); mad=np.median(np.abs(res[mask]-med))+1e-6
        lim=max(1.2,min(5.0,med+2.8*1.4826*mad)); new=res<lim
        if new.sum()<12 or np.array_equal(new,mask): break
        mask=new
    return coef,mask


def project_geometry(pixel,coef): return geom_features(pixel)@coef


def iterative_calibration(frames, calibration_seconds, selected):
    coef=None; history=[]
    for iteration,maxcost in enumerate([12.,8.,6.,5.]):
        pix_all=[]; world_all=[]; costs=[]
        for f in frames:
            if f['t']>calibration_seconds: continue
            p=[d for d in f['all_persons'] if d['cluster'] in selected]
            pix=np.asarray([d['foot'] for d in p],float) if p else np.empty((0,2))
            pred=rough_project(pix) if coef is None else project_geometry(pix,coef)
            m=assign(pred,f['gt'],maxcost)
            for i,j,c in m:
                pix_all.append(pix[i]); world_all.append([f['gt'][j]['x'],f['gt'][j]['y']]); costs.append(c)
        if len(pix_all)<12: break
        coef,mask=fit_geometry(np.asarray(pix_all),np.asarray(world_all))
        residual=np.linalg.norm(project_geometry(np.asarray(pix_all),coef)-np.asarray(world_all),axis=1)
        history.append({'iteration':iteration,'max_assignment_m':maxcost,'pairs':len(pix_all),'inliers':int(mask.sum()),'fit_mae_m':float(np.mean(residual[mask])),'assignment_mae_m':float(np.mean(costs))})
    if coef is None: raise RuntimeError('Geometry calibration failed')
    return coef,history


def summarize(rows,total_gt,total_det):
    if not rows:return {'matched':0,'gt_points':total_gt,'detections':total_det,'recall':0.}
    e=pd.DataFrame(rows).sort_values(['gt_id','t']); pos=e.position_error_m.to_numpy(float)
    out={'matched':len(e),'gt_points':total_gt,'detections':total_det,'recall':len(e)/max(1,total_gt),'precision_proxy':len(e)/max(1,total_det),'position_mae_m':float(np.mean(pos)),'position_rmse_m':float(np.sqrt(np.mean(pos**2))),'position_p95_m':float(np.percentile(pos,95))}
    raw_speed=[]; smooth_speed=[]; raw_pred_dist=raw_true_dist=smooth_pred_dist=smooth_true_dist=0.
    for pid,g in e.groupby('gt_id'):
        g=g.drop_duplicates('t').sort_values('t'); t=g.t.to_numpy(float); xy=g[['pred_x','pred_y']].to_numpy(float); td=g.truth_total_distance.to_numpy(float)
        if len(g)<2: continue
        dt=np.diff(t); ds=np.linalg.norm(np.diff(xy,axis=0),axis=1); good=(dt>.2)&(dt<=.75)&(ds/dt<15)
        truth_delta=np.maximum(0,np.diff(td)); truth_v=truth_delta/np.maximum(dt,1e-6)
        raw_speed += (ds[good]/dt[good]-truth_v[good]).tolist(); raw_pred_dist+=float(ds[good].sum()); raw_true_dist+=float(truth_delta[good].sum())
        # Only smooth reasonably contiguous trajectories; this is the same low-pass step used by real EPTS pipelines.
        xs=xy.copy()
        if len(xs)>=5:
            win=min(7,len(xs) if len(xs)%2==1 else len(xs)-1)
            if win>=5:
                xs[:,0]=savgol_filter(xs[:,0],win,2,mode='interp'); xs[:,1]=savgol_filter(xs[:,1],win,2,mode='interp')
        ds2=np.linalg.norm(np.diff(xs,axis=0),axis=1); good2=(dt>.2)&(dt<=.75)&(ds2/dt<15)
        smooth_speed += (ds2[good2]/dt[good2]-truth_v[good2]).tolist(); smooth_pred_dist+=float(ds2[good2].sum()); smooth_true_dist+=float(truth_delta[good2].sum())
    if raw_speed:
        a=np.asarray(raw_speed); out.update(raw_speed_mae_mps=float(np.mean(np.abs(a))),raw_speed_rmse_mps=float(np.sqrt(np.mean(a*a))),raw_distance_error_pct=float(100*(raw_pred_dist-raw_true_dist)/max(raw_true_dist,1e-6)))
    if smooth_speed:
        a=np.asarray(smooth_speed); out.update(speed_mae_mps=float(np.mean(np.abs(a))),speed_rmse_mps=float(np.sqrt(np.mean(a*a))),speed_bias_mps=float(np.mean(a)),speed_samples=len(a),distance_pred_m=smooth_pred_dist,distance_truth_m=smooth_true_dist,distance_error_pct=float(100*(smooth_pred_dist-smooth_true_dist)/max(smooth_true_dist,1e-6)))
    return out


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--video',required=True); ap.add_argument('--truth',required=True); ap.add_argument('--out',required=True); ap.add_argument('--sample-fps',type=float,default=2.0); ap.add_argument('--calibration-seconds',type=float,default=3.0); ap.add_argument('--model',default='yolo11n.pt'); args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    from ultralytics import YOLO
    model=YOLO(args.model); truth_by=load_truth(args.truth)
    cap=cv2.VideoCapture(args.video); fps=float(cap.get(cv2.CAP_PROP_FPS) or 25); dur=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))/fps
    times=np.arange(.5,max(.51,dur-.25),1/args.sample_fps); frames=[]
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC,float(t*1000)); ok,frame=cap.read()
        if not ok: continue
        persons=[d for d in detect_tiled(model,frame) if d['cls']=='person']
        for d in persons: d['feat']=appearance_feature(frame,d['box'])
        frames.append({'t':float(t),'frame':frame,'all_persons':persons,'gt':truth_at(truth_by,float(t))})
        print(f't={t:.2f}s people={len(persons)}',flush=True)
    cap.release()
    k=4; cluster_appearance(frames,args.calibration_seconds,k); selected,tuning=choose_cluster_subset(frames,args.calibration_seconds,k)
    print('selected_clusters=',sorted(selected),flush=True); print('best_cluster_config=',max(tuning,key=lambda x:x['score']),flush=True)
    (out/'cluster_tuning.json').write_text(json.dumps(tuning,indent=2),encoding='utf-8')
    coef,calhist=iterative_calibration(frames,args.calibration_seconds,selected); np.save(out/'pixel_to_world_poly2.npy',coef); (out/'calibration_history.json').write_text(json.dumps(calhist,indent=2),encoding='utf-8'); print('calibration_history=',calhist,flush=True)
    rows=[]; total_gt=total_det=0; annotated=None
    for f in frames:
        if f['t']<=args.calibration_seconds: continue
        persons=[d for d in f['all_persons'] if d['cluster'] in selected]; pix=np.asarray([d['foot'] for d in persons],float) if persons else np.empty((0,2)); pred=project_geometry(pix,coef) if len(pix) else np.empty((0,2)); m=assign(pred,f['gt'],7.5); total_gt+=len(f['gt']); total_det+=len(pred)
        for i,j,c in m:
            g=f['gt'][j]; rows.append({'t':f['t'],'gt_id':g['id'],'pred_x':pred[i,0],'pred_y':pred[i,1],'truth_x':g['x'],'truth_y':g['y'],'position_error_m':c,'truth_speed':g['speed'],'truth_total_distance':g['total_distance'],'pixel_x':pix[i,0],'pixel_y':pix[i,1],'cluster':persons[i]['cluster']})
        if annotated is None:
            annotated=f['frame'].copy()
            for d in f['all_persons']:
                x1,y1,x2,y2=map(int,d['box']); sel=d['cluster'] in selected; col=(0,255,0) if sel else (255,160,0); cv2.rectangle(annotated,(x1,y1),(x2,y2),col,2); cv2.putText(annotated,f"C{d['cluster']}",(x1,y1-4),0,.5,col,1)
            for i,j,c in m:
                x,y=map(int,pix[i]); cv2.circle(annotated,(x,y),10,(0,0,255),3); cv2.putText(annotated,f"GT{f['gt'][j]['id']} {c:.1f}m",(x+6,y-6),0,.6,(0,0,255),2)
    pd.DataFrame(rows).to_csv(out/'matched_observations.csv',index=False); metrics=summarize(rows,total_gt,total_det); metrics.update({'version':'v3-cluster-iterative','video_duration_s':dur,'sample_fps':args.sample_fps,'calibration_seconds':args.calibration_seconds,'model':args.model,'selected_clusters':sorted(selected),'calibration_history':calhist}); (out/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8');
    if annotated is not None: cv2.imwrite(str(out/'annotated_eval_frame.jpg'),annotated)
    print(json.dumps(metrics,indent=2),flush=True)

if __name__=='__main__': main()
