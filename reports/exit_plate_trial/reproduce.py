import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
import json,cv2,numpy as np,onnxruntime as ort
from pathlib import Path
from computer_vision_v2.inference import plate_ocr
P=Path(__file__).resolve().parent

def session(path):
 o=ort.SessionOptions();o.intra_op_num_threads=2;o.inter_op_num_threads=1
 return ort.InferenceSession(str(path),sess_options=o,providers=['CPUExecutionProvider'])
plate_ocr._session=session
class Reader(plate_ocr.PlateReader):
 def detect_plate(self,crop):
  r=super().detect_plate(crop);self.last=r;return r
 def _ctc_decode(self,out):
  r=super()._ctc_decode(out);self.ocr_conf=r[1];return r
r=Reader();logs=json.loads((P/'source_log.json').read_text());out=[]
for n in [159,210,270,330]:
 crop=cv2.imread(str(P/f'vehicle_{n}.png'));expected=next(x for x in logs if x['frame']==n and x.get('track')==1)
 txt,conf,path=r.read(crop)
 assert txt==expected['text'],(n,txt,expected['text'])
 assert abs(conf-expected['confidence'])<1e-5,(n,conf,expected['confidence'])
 row={'frame':n,'text':txt,'confidence':conf,'matched_log':True}
 if r.last:
  plate,detconf,_=r.last;cv2.imwrite(str(P/f'baseline_plate_{n}.png'),plate);row.update(det_conf=detconf,plate_size=[plate.shape[1],plate.shape[0]],ocr_conf=r.ocr_conf)
 out.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
(P/'reproduction.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
