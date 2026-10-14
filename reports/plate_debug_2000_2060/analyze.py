"""Replay logged vehicle boxes; do not infer historical pipeline dispatch timing."""
import os
os.environ['OMP_NUM_THREADS']='2'
os.environ['OPENBLAS_NUM_THREADS']='2'
import json
from pathlib import Path
from collections import Counter
import cv2
import numpy as np
import onnxruntime as ort
from computer_vision_v2.best_crop_selector import BestCropSelector
from computer_vision_v2.inference import plate_ocr

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
VIDEO=ROOT/'src/computer_vision_v2/video/Rec 0073.mp4'
LOG=ROOT/'reports/plate_debug/20261012-200343/results.jsonl'
rows=[json.loads(l) for l in LOG.read_text().splitlines() if l.strip()]
rows=[r for r in rows if r.get('track')==1 and r['frame']<=2060]
by_frame={r['frame']:r for r in rows}
# Only bound CPU worker counts; keep weights, providers and preprocessing unchanged.
def session(path):
 options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
 return ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])
plate_ocr._session=session
reader=plate_ocr.PlateReader()
selector=BestCropSelector()
cap=cv2.VideoCapture(str(VIDEO))

scored=[];crops={};frames={};best_all=None;best_range=None
for n in range(1,2061):
 ok,frame=cap.read()
 if not ok: raise RuntimeError(f'Cannot decode {n}')
 if n not in by_frame: continue
 r=by_frame[n];box=r['bbox'];x1,y1,x2,y2=box
 result=selector._score(frame,box,r['vehicle_confidence'])
 crop=frame[y1:y2,x1:x2].copy()
 entry=dict(r,score=None,sharpness=None)
 if result:
  score,_,sharpness=result
  entry.update(score=float(score),sharpness=float(sharpness))
  if best_all is None or score>best_all['score']:best_all=entry
  if n>=2000 and (best_range is None or score>best_range['score']):best_range=entry
 scored.append(entry);crops[n]=crop;frames[n]=frame
cap.release()
print('best_all',best_all,flush=True);print('best_range',best_range,flush=True)
probes=[]
probe_frames = {best_all['frame'], best_range['frame'], 2000, 2020, 2040, 2050, 2055, 2060}
for n in sorted(probe_frames):
 crop=crops[n]
 img,scale,dx,dy=plate_ocr._letterbox(crop,reader.det_size)
 blob=img[:,:,::-1].transpose(2,0,1)[None].astype(np.float32)/255
 raw=reader.detector.run(None,{reader.det_input:blob})[0]
 pred=np.squeeze(raw)
 if pred.shape[0]<pred.shape[1]:pred=pred.T
 scores=pred[:,4:].max(axis=1)
 k=int(scores.argmax());cx,cy,w,h=map(float,pred[k,:4]);box=[int((cx-w/2-dx)/scale),int((cy-h/2-dy)/scale),int((cx+w/2-dx)/scale),int((cy+h/2-dy)/scale)]
 # Call the production reader on the exact same pixels.
 actual_detector=reader.detector
 class CachedDetector:
  def run(self, *_args, **_kwargs): return [raw]
 reader.detector=CachedDetector()
 try:
  text,confidence,path=reader.read(crop)
 finally:
  reader.detector=actual_detector
 probe={'frame':n,'crop_size':[crop.shape[1],crop.shape[0]],'raw_shape':list(raw.shape),'max_detector_score':float(scores[k]),'top_box':box,'text':text,'combined_confidence':confidence,'plate_path':path}
 expected=by_frame[n]
 assert text == expected['text'], (n, text, expected['text'])
 assert abs(confidence - expected['confidence']) < 1e-5, (n, confidence, expected['confidence'])
 probes.append(probe)
 if n in (2000,2020,2040,2050,2055,2060,best_all['frame'],best_range['frame']):
  cv2.imwrite(str(OUT/f'vehicle_{n}.png'),crop)
  marked=crop.copy();a,b,c,d=box;cv2.rectangle(marked,(a,b),(c,d),(0,0,255),1);cv2.imwrite(str(OUT/f'detector_top_{n}.png'),marked)
  cv2.imwrite(str(OUT/f'frame_{n}.png'),frames[n])
  if path:
   plate=cv2.imread(path);cv2.imwrite(str(OUT/f'plate_{n}.png'),plate)
   probe['plate_size']=[plate.shape[1],plate.shape[0]]
 print(json.dumps(probe,ensure_ascii=False),flush=True)
summary={'video':str(VIDEO),'frame_numbering':'1-based inclusive','log_status_counts':dict(Counter(r['status'] for r in rows if r['frame']>=2000)), 'best_range':best_range,'best_all_logged_candidates':best_all,'scores':scored,'probes':probes,'limitation':'Logged debug boxes; best_all ranks all observed crops without historical expiry or crossing dispatch. Original main-pipeline selected crop was not logged.'}
(OUT/'analysis.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
assert {p['frame'] for p in probes}==probe_frames
print('DONE',flush=True)
