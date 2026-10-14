import json,pickle
from pathlib import Path
from computer_vision_v2.inference.plate_ocr import PlateReader
out=Path(__file__).resolve().parent
reader=PlateReader()
failed=[]
for n in (1,2):
    with (out/f'event_{n}.pkl').open('rb') as f: passage=pickle.load(f)
    result=reader.recognize_candidates(passage.candidates)
    print(n,result['recognition_status'],json.dumps(result['readings'],ensure_ascii=False),flush=True)
    if result["recognition_status"] != "read": failed.append(n)
assert not failed, f"Expected corroborated plates; uncertain cars: {failed}"
