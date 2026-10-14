"""Read-only model diagnosis on sequentially extracted 1080p video frames."""
import os
os.environ['OMP_NUM_THREADS']='2'
os.environ['OPENBLAS_NUM_THREADS']='2'
os.environ['TORCH_CPP_LOG_LEVEL']='ERROR'
import json,hashlib
from types import SimpleNamespace
from pathlib import Path
import cv2
import numpy as np
import torch
import onnxruntime as ort
torch.set_num_threads(2)
from computer_vision_v2.inference import plate_ocr
from computer_vision_v2.debug_plate import InspectableReader
from computer_vision_v2.tracking.tracker import CameraTracker
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent

def session(path):
 options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
 return ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])
plate_ocr._session=session
reader=InspectableReader()
config=json.loads((ROOT/'src/computer_vision_v2/reno/data/cameras.json').read_text())
tracker=CameraTracker('sample',str(ROOT/config['model_path']),config.get('detection_interval',3))

def probe(crop,prefix):
 cv2.imwrite(str(OUT/f'{prefix}_vehicle.png'),crop)
 img,scale,dx,dy=plate_ocr._letterbox(crop,reader.det_size)
 blob=img[:,:,::-1].transpose(2,0,1)[None].astype(np.float32)/255
 original=reader.detector;raw=original.run(None,{reader.det_input:blob})[0]
 pred=np.squeeze(raw)
 if pred.shape[0]<pred.shape[1]:pred=pred.T
 scores=pred[:,4:].max(axis=1);k=int(scores.argmax());cx,cy,w,h=map(float,pred[k,:4]);box=[int((cx-w/2-dx)/scale),int((cy-h/2-dy)/scale),int((cx+w/2-dx)/scale),int((cy+h/2-dy)/scale)]
 class CachedDetector:
  def run(self,*_args,**_kwargs):return [raw]
 reader.detector=CachedDetector()
 try:text,conf,path=reader.read(crop)
 finally:reader.detector=original
 info={'vehicle_size':[crop.shape[1],crop.shape[0]],'max_plate_score':float(scores[k]),'top_box':box,'text':text,'combined_confidence':conf,'ocr_confidence':reader.ocr_conf,'plate_size':None,'artifact':prefix}
 if reader.plate_crop is not None:
  info['plate_size']=[reader.plate_crop.shape[1],reader.plate_crop.shape[0]]
  cv2.imwrite(str(OUT/f'{prefix}_plate.png'),reader.plate_crop)
  cv2.imwrite(str(OUT/f'{prefix}_ocr_input.png'),reader.ocr_input_image)
 marked=crop.copy();a,b,c,d=box;cv2.rectangle(marked,(a,b),(c,d),(0,0,255),2);cv2.imwrite(str(OUT/f'{prefix}_marked.png'),marked)
 return info

log=ROOT/'reports/plate_debug/20261012-211328/results.jsonl'
rows=[json.loads(l) for l in log.read_text().splitlines() if l.strip()]
(OUT/'source_log_snapshot.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
known=next(r for r in rows if r['frame']==33 and r['track']==2)
repro=probe(cv2.imread(str(OUT/'vehicle_33_track_2.png')),'logged_33')
assert repro['text']==known['text'],repro
assert abs(repro['combined_confidence']-known['confidence'])<1e-5,repro
print('REPRODUCED',json.dumps(repro,ensure_ascii=False),flush=True)
results=[]
for n in [33,330,390,450,510,570]:
 frame=cv2.imread(str(OUT/f'frame_{n}.png'))
 result=tracker.model.predict(frame,classes=[0,2],verbose=False,imgsz=(256,416),conf=0.1)[0]
 tracked=SimpleNamespace(detections=[SimpleNamespace(class_id=int(box.cls.item()),bbox=box.xyxy[0].cpu().tolist(),confidence=float(box.conf.item()),track_id=i) for i,box in enumerate(result.boxes)])
 entry={'frame':n,'cars':[]}
 for det in tracked.detections:
  if det.class_id!=2:continue
  x1,y1,x2,y2=map(int,det.bbox);crop=frame[max(0,y1):min(frame.shape[0],y2),max(0,x1):min(frame.shape[1],x2)]
  if not crop.size:continue
  item={'sample_track':det.track_id,'bbox':[x1,y1,x2,y2],'vehicle_confidence':float(det.confidence)}
  item.update(probe(crop,f'raw_{n}_{det.track_id}'))
  if x1<1000 and n in (330,450,510,570):
   small=cv2.resize(crop,(max(1,round(crop.shape[1]*680/1920)),max(1,round(crop.shape[0]*420/1080))),interpolation=cv2.INTER_AREA)
   item['downscaled_comparison']=probe(small,f'raw_{n}_{det.track_id}_small')
  entry['cars'].append(item)
 results.append(entry);print(json.dumps(entry,ensure_ascii=False),flush=True)
 (OUT/'analysis_raw.json').write_text(json.dumps({'reproduced':repro,'samples':results,'sampling':'Independent YOLO vehicle detections with production model, imgsz/classes and tracking default confidence 0.1; no sparse-frame tracker smoothing. sample_track is detection index, not a track ID. CPU thread counts bounded.'},ensure_ascii=False,indent=2))
print('DONE',flush=True)
