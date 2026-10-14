import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
import cv2,json,numpy as np,onnxruntime as ort
from pathlib import Path
from geometry import rectify,rectify_text_band
from computer_vision_v2.inference.plate_ocr import PlateReader,DEFAULT_OCR,DEFAULT_LABELS
P=Path(__file__).resolve().parent
r=PlateReader.__new__(PlateReader);options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
r.ocr=ort.InferenceSession(str(DEFAULT_OCR),sess_options=options,providers=['CPUExecutionProvider']);i=r.ocr.get_inputs()[0];r.ocr_input=i.name;r.ocr_c,r.ocr_h,r.ocr_w=[v if isinstance(v,int) else d for v,d in zip(i.shape[1:],[1,32,128])];r.labels=r._load_labels(DEFAULT_LABELS)
results=[]
for b in json.loads((P/'baseline.json').read_text()):
 n=b['frame'];v=cv2.imread(str(P/f'vehicle_{n}.png'))
 for k,d in enumerate(b['detections']):
  x1,y1,x2,y2=d['bbox'];pad=12;roi=v[max(0,y1-pad):y2+pad,max(0,x1-pad):x2+pad]
  if (x2-x1)/(y2-y1)<1.15:
   results.append({'frame':n,'baseline':d,'status':'reject_aspect'});continue
  crop,meta=rectify(roi)
  if crop is None:crop,meta=rectify_text_band(roi)
  result={'frame':n,'baseline':d,'geometry':meta,'status':'no_geometry'}
  if crop is not None:
   logits=r.ocr.run(None,{r.ocr_input:r._prep_ocr(crop)})[0];text,conf=r._ctc_decode(logits)
   result.update(status='ocr',text=text,ocr_confidence=conf,size=[crop.shape[1],crop.shape[0]])
   cv2.imwrite(str(P/f'corrected_{n}_{k}.png'),crop)
  results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
(P/'geometry_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print('DONE',flush=True)
