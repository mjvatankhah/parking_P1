import json,cv2
from pathlib import Path
from computer_vision_v2.inference.plate_ocr import PlateReader
from computer_vision_v2.inference.plate_geometry import prepare_plate
out=Path(__file__).resolve().parent
rows=[json.loads(l) for l in (out/'frames.jsonl').read_text().splitlines()]
wanted={r['frame']: next(d for d in r['detections'] if d['track_id']==31) for r in rows if r['frame'] in (328,334,340) and any(d['track_id']==31 for d in r['detections'])}
reader=PlateReader();cv2.setNumThreads(2)
config=json.loads((out/'config.json').read_text());cap=cv2.VideoCapture(config['cameras'][0]['source']);results=[]
def ocr(im):
 text,conf=reader._ctc_decode(reader.ocr.run(None,{reader.ocr_input:reader._prep_ocr(im)})[0]);return dict(text=text,confidence=conf,size=list(im.shape[1::-1]))
for n in range(1,max(wanted)+1):
 ok,im=cap.read()
 if not ok:break
 if n not in wanted:continue
 x1,y1,x2,y2=wanted[n]['bbox'];w=x2-x1;h=y2-y1
 for margin in (0,.1,.2):
  vehicle=im[max(0,int(y1-margin*h)):min(im.shape[0],int(y2+margin*h)),max(0,int(x1-margin*w)):min(im.shape[1],int(x2+margin*w))]
  detection=reader.detect_plate(vehicle);row=dict(frame=n,margin=margin,detected=detection is not None)
  if detection is not None:
   raw,conf,context=detection;prepared=prepare_plate(context)
   row.update(detector_confidence=conf,raw=ocr(raw),prepared=ocr(prepared.image) if prepared else None)
   cv2.imwrite(str(out/f'margin_{n}_{margin}_raw.png'),raw)
   if prepared:cv2.imwrite(str(out/f'margin_{n}_{margin}_prepared.png'),prepared.image)
  results.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
cap.release();(out/'vehicle_margin_comparison.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
