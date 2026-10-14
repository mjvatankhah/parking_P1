import json,pickle
from pathlib import Path
from computer_vision_v2.inference.plate_ocr import PlateReader
out=Path(__file__).resolve().parent; r=PlateReader(); rows=[]
for n in (1,2):
    file=out/f'event_{n}.pkl'
    if not file.exists(): continue
    p=pickle.loads(file.read_bytes())
    for c in p.candidates:
        result=r.recognize_candidates([c]); result.pop('image')
        rows.append(dict(car=n,frame=c.frame_idx,ts=c.ts,sampling_quality=c.quality,plate_confidence=c.confidence,geometry_quality=c.prepared.quality if c.prepared else None,**result))
(out/'all_readings.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
for row in rows: print(row['car'],row['frame'],row['readings'])
