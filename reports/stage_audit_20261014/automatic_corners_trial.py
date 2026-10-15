import json,time
from pathlib import Path
import cv2,numpy as np
from audit import selected_detection,ocr_reader,decode
from computer_vision_v2.inference.plate_geometry import prepare_plate,_prepare_deskew,_rectify_plate
cv2.setNumThreads(2)
reader=None
rows=[]
for entry in json.loads(Path('reports/exit_plate_trial/baseline.json').read_text()):
 n=entry['frame']; im=cv2.imread(f'reports/exit_plate_trial/vehicle_{n}.png'); d=selected_detection(entry,im)
 if d is None: continue
 context=d[2]; start=time.perf_counter(); rect=_rectify_plate(context); ms=(time.perf_counter()-start)*1000
 old=_prepare_deskew(context); new=prepare_plate(context)
 changed=new is not None and (old is None or not np.array_equal(new.image,old.image))
 row=dict(frame=n,quad=rect is not None,changed=changed,corner_ms=ms)
 if changed:
  if reader is None: reader=ocr_reader()
  row['old']=decode(reader,old.image) if old else None; row['new']=decode(reader,new.image)
  cv2.imwrite(f'/tmp/corner_{n}.png',new.image)
 rows.append(row)
Path('reports/stage_audit_20261014/automatic_corners.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
print(json.dumps(dict(samples=len(rows),quads=sum(r['quad'] for r in rows),changed=[r for r in rows if r['changed']],median_ms=float(np.median([r['corner_ms'] for r in rows]))),ensure_ascii=False),flush=True)
