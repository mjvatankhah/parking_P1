"""Replay corrected tracking through actual line and passage logic, without OCR."""
import sys,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from computer_vision_v2.Line_Manager.line_detector import LineDetectorManager
from computer_vision_v2.ocr_worker.plate_candidates import PlateCandidates
from computer_vision_v2.tracking.frame_info import Detection,TrackedFrame
p=Path(__file__).resolve().parent;cfg=json.loads((p/'cc2_config.json').read_text());lines=LineDetectorManager(cfg);pool=PlateCandidates(None);pool._sample=lambda *a:None
crossings=[];finished=[];image=np.zeros((1080,1920,3),np.uint8)
for r in map(json.loads,(p/'fixed/frames.jsonl').read_text().splitlines()):
 frame=TrackedFrame('cc2',r['frame'],r['ts'],image,[Detection(**d) for d in r['detections']]);events=lines.update(frame);crossings.extend(events);finished.extend(pool.observe(frame,events))
print('Crossings:',[(e['track_id'],e['frame_idx']) for e in crossings])
print('Finalized:',[x.event['track_id'] for x in finished])
print('Pending:',[(k,round(frame.ts-s.seen,3)) for k,s in pool.tracks.items() if s.event])
assert [x.event['track_id'] for x in finished]==[1,4]
assert any(s.event and s.event['track_id']==7 for s in pool.tracks.values())
assert not any(e['track_id']==9 for e in crossings)
