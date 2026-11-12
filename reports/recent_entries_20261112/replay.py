import sys,json
from pathlib import Path
from types import SimpleNamespace as NS
from collections import Counter
import cv2
sys.path.insert(0,str(Path.cwd()/'src'))
from computer_vision_v2.inference.plate_ocr import PlateReader
import computer_vision_v2.inference.plate_ocr as module
# Replay archived geometry outcomes, without rerunning image preparation.
module.prepare_plate=lambda image: None
class Candidates(list):pass
failures=[]
for name in ['f31887064766452fa646d0412d32b94c','091b85291ac7495d8274ea730b120f82','bbb32dfc62a342c785f31ca3629a05f9','e80225b30c9d427abf4a3cef9686c71c']:
 root=Path('reports/crop_diagnostics')/name
 d=json.loads((root/'manifest.json').read_text())
 cs=Candidates();cs.selection_groups=d['selection_groups'] or None; answers={}
 for s in d['samples']:
  if not s.get('retained_for_recognition'):continue
  raw=cv2.imread(str(root/s['raw'])); geo=cv2.imread(str(root/s['geometry'])) if s.get('geometry') else None
  c=NS(frame_idx=s['frame_idx'],ts=s['ts'],crop=raw,context=raw,quality=s['quality'],confidence=s['confidence'],prepared=NS(image=geo,quality=s['geometry_quality']) if geo is not None else None)
  cs.append(c)
  for r in d['ocr_inputs']:
   if r['frame_idx']==c.frame_idx: answers[id(raw if r['source']=='raw' else geo)]=(r['text'],r['confidence'])
 reader=object.__new__(PlateReader); reader.labels=json.loads(Path('src/computer_vision_v2/ocr_worker/models/ocr_crnn.labels.json').read_text())
 reader._recognize_batch=lambda images:[answers[id(i)] for i in images]
 result=reader.recognize_candidates(cs)
 votes=Counter(r['text'] for r in result['readings'] if r['valid'] and r['confidence']>=.8)
 print(d['database_event_id'],result['recognition_status'],dict(votes),'expected read:',result['recognition_status']=='read')
 assert result['recognition_status']==d['result']['recognition_status']

 if result['recognition_status']!='read': failures.append(d['database_event_id'])
if '--require-read' in sys.argv:
 assert not failures, f'Entries without confirmed plates: {failures}'
