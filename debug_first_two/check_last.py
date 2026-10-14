import pickle,json
from pathlib import Path
from computer_vision_v2.inference.plate_ocr import PlateReader
p=Path(__file__).resolve().parent/'last_car'
r=PlateReader().recognize_candidates(pickle.loads((p/'event_1.pkl').read_bytes()).candidates)
r.pop('image');print(json.dumps(r,ensure_ascii=False),flush=True)
assert r['recognition_status']=='read', 'Last car lacks a corroborated valid plate'
