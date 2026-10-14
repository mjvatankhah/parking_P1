import json,pickle
from pathlib import Path
from computer_vision_v2.inference.plate_ocr import PlateReader
out=Path(__file__).resolve().parent;r=PlateReader();p=pickle.loads((out/'event_1.pkl').read_bytes())
result=r.recognize_candidates([c for c in p.candidates if c.frame_idx in (301,349)])
result.pop('image')
assert result['recognition_status']=='read' and result['plate_text']=='58م87245'
(out/'pair_probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))
