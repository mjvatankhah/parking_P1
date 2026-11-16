import json,sys
from pathlib import Path
import cv2,torch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from computer_vision_v2.inference.hezar_ocr import HezarOCR
from computer_vision_v2.inference.plate_ocr import MODEL_DIR
from audit import decision,valid
out=Path(__file__).resolve().parent;torch.set_num_threads(2);ocr=HezarOCR(MODEL_DIR);results=[]
for event in json.loads((out/'all_ocr.json').read_text()):
 rows=[r.copy() for r in event['rows'] if r['source']=='raw']
 for i in range(0,len(rows),16):
  batch=rows[i:i+16];images=[]
  for r in batch:
   im=cv2.imread(r['image']);h,w=im.shape[:2];images.append(cv2.copyMakeBorder(im,max(2,h//10),max(2,h//10),max(3,w//10),max(3,w//10),cv2.BORDER_REPLICATE))
  for r,(text,c) in zip(batch,ocr.recognize(images)):r.update(text=text,confidence=c,valid=valid(text))
 result=dict(event=event['event'],rows=rows,decision=decision(rows));results.append(result);print(result['event'],result['decision'],flush=True)
 (out/'padding.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
