import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
import cv2,json,numpy as np,onnxruntime as ort
from pathlib import Path
from computer_vision_v2.inference import plate_ocr
P=Path(__file__).resolve().parent

def session(path):
 opts=ort.SessionOptions();opts.intra_op_num_threads=2;opts.inter_op_num_threads=1
 return ort.InferenceSession(str(path),sess_options=opts,providers=['CPUExecutionProvider'])
plate_ocr._session=session
reader=plate_ocr.PlateReader();records=json.loads((P/'baseline.json').read_text()) if (P/'baseline.json').exists() else []
completed={r['frame'] for r in records}
log={r['frame']:r for r in json.loads((P/'extended_log.json').read_text()) if r.get('track')==1}
for path in sorted(P.glob('vehicle_*.png'),key=lambda p:int(p.stem.split('_')[1])):
 n=int(path.stem.split('_')[1])
 if n in completed:continue
 crop=cv2.imread(str(path));img,scale,dx,dy=plate_ocr._letterbox(crop,reader.det_size)
 cache=P/f'raw_{n}.npy'
 if cache.exists():raw=np.load(cache)
 else:
  raw=reader.detector.run(None,{reader.det_input:img[:,:,::-1].transpose(2,0,1)[None].astype(np.float32)/255})[0];np.save(cache,raw)
 pred=np.squeeze(raw)
 if pred.shape[0]<pred.shape[1]:pred=pred.T
 scores=pred[:,4:].max(axis=1);mask=scores>.35;ps=pred[mask];ss=scores[mask]
 boxes=np.empty((len(ps),4),np.float32)
 boxes[:,0]=ps[:,0]-ps[:,2]/2;boxes[:,1]=ps[:,1]-ps[:,3]/2;boxes[:,2]=ps[:,0]+ps[:,2]/2;boxes[:,3]=ps[:,1]+ps[:,3]/2
 detections=[]
 for k in plate_ocr._nms(boxes,ss):
  b=boxes[k].copy();b[[0,2]]=(b[[0,2]]-dx)/scale;b[[1,3]]=(b[[1,3]]-dy)/scale
  x1,y1,x2,y2=map(int,b);x1=max(0,x1);y1=max(0,y1);x2=min(crop.shape[1],x2);y2=min(crop.shape[0],y2)
  if x2<=x1 or y2<=y1:continue
  plate=crop[y1:y2,x1:x2];blob=reader._prep_ocr(plate);logits=reader.ocr.run(None,{reader.ocr_input:blob})[0];text,conf=reader._ctc_decode(logits)
  det={'bbox':[x1,y1,x2,y2],'score':float(ss[k]),'text':text,'ocr_conf':conf}
  cv2.imwrite(str(P/f'plate_{n}_{len(detections)}.png'),plate);detections.append(det)
 best=max(detections,key=lambda r:r['score']) if detections else None
 expected=log[n]
 assert (best['text'] if best else None)==expected['text'],(n,best,expected)
 record={'frame':n,'track':1,'vehicle_bbox':expected['bbox'],'max_score':float(scores.max()),'detections':detections,'matched_log':True}
 records.append(record)
 (P/'baseline.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
 print(n,'detections',len(detections),'text',best['text'] if best else None,flush=True)
print('DONE',len(records),flush=True)
