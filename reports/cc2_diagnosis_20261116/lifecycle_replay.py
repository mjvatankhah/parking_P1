"""Replay real passage lifetime logic; sampling bypassed to isolate retirement."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from computer_vision_v2.ocr_worker.plate_candidates import PlateCandidates
from computer_vision_v2.tracking.frame_info import Detection,TrackedFrame
out=Path(__file__).resolve().parent
rows=json.loads((out/'tracks.json').read_text());events=json.loads((out/'crossings.json').read_text())
pool=PlateCandidates(None);pool._sample=lambda *args:None
finished=[]
for row in rows:
 i=row['frame'];frame=TrackedFrame('cc2',i,i/(149/6),None,[Detection(d['id'],tuple(d['box']),2,1,d['pred']) for d in row['boxes']])
 finished.extend(pool.observe(frame,[e for e in events if e['frame_idx']==i]))
print('Finalized IDs:',[p.event['track_id'] for p in finished])
print('Pending:',[(k,s.event['frame_idx'],round(frame.ts-s.seen,3)) for k,s in pool.tracks.items() if s.event])
assert [p.event['track_id'] for p in finished]==[1,5]
assert any(s.event and s.event['track_id']==7 for s in pool.tracks.values())
