import pickle,json
from pathlib import Path
from computer_vision_v2.inference.plate_ocr import PlateReader
p=Path(__file__).resolve().parent;r=PlateReader();event=pickle.loads((p/'last_car/event_1.pkl').read_bytes());rows=[]
for c in event.candidates:
    for kind,image in [('raw',c.crop),('prepared',c.prepared.image if c.prepared else None)]:
        if image is None:continue
        text,confidence=r._ctc_decode(r.ocr.run(None,{r.ocr_input:r._prep_ocr(image)})[0])
        rows.append(dict(frame=c.frame_idx,kind=kind,text=text,confidence=confidence))
(p/'last_comparison.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2));print(json.dumps(rows,ensure_ascii=False))
