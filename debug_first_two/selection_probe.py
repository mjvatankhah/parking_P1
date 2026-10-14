import json,pickle
from pathlib import Path
from computer_vision_v2.inference.plate_ocr import PlateReader
out=Path(__file__).resolve().parent;r=PlateReader();p=pickle.loads((out/'event_1.pkl').read_bytes())
rows=[]
for name,frames in [('baseline',None),('omit_top_frame_340',{340}),('omit_frames_340_373',{340,373})]:
    result=r.recognize_candidates([c for c in p.candidates if frames is None or c.frame_idx not in frames]); result.pop('image'); rows.append({'case':name,**result})
(out/'selection_probe.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
print(json.dumps(rows,ensure_ascii=False,indent=2))
