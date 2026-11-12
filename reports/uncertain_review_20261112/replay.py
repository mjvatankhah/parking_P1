"""Replay recorded OCR through real voting; no inference or database writes."""
import json,sys
from pathlib import Path
from types import SimpleNamespace as NS
from collections import Counter
import cv2
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from computer_vision_v2.inference.plate_ocr import PlateReader
import computer_vision_v2.inference.plate_ocr as module
module.prepare_plate=lambda image:None
class Candidates(list):pass
rows=[]
for p in sorted((ROOT/'reports/crop_diagnostics').glob('*/manifest.json')):
 d=json.loads(p.read_text()); eid=d.get('database_event_id')
 if eid is None or not 416<=eid<=434:continue
 cs=Candidates(); cs.selection_groups=d['selection_groups']; answers={}
 for s in d['samples']:
  if not s.get('retained_for_recognition'):continue
  raw=cv2.imread(str(p.parent/s['raw'])); geo=None
  gr=next((r for r in d['ocr_inputs'] if r['frame_idx']==s['frame_idx'] and r['source']=='geometry'),None)
  if gr:geo=cv2.imread(str(p.parent/gr['image']))
  elif s.get('geometry'):geo=cv2.imread(str(p.parent/s['geometry']))
  cs.append(NS(frame_idx=s['frame_idx'],ts=s['ts'],crop=raw,context=raw,quality=s['quality'],confidence=s['confidence'],prepared=NS(image=geo,quality=s.get('geometry_quality') or 0) if geo is not None else None))
  for r in d['ocr_inputs']:
   if r['frame_idx']==s['frame_idx']:answers[id(raw if r['source']=='raw' else geo)]=(r['text'],r['confidence'])
 reader=object.__new__(PlateReader);reader.labels=json.loads((ROOT/'src/computer_vision_v2/ocr_worker/models/ocr_crnn.labels.json').read_text());reader._recognize_batch=lambda images:[answers[id(i)] for i in images]
 result=reader.recognize_candidates(cs)
 assert result['recognition_status']==d['result']['recognition_status'],eid
 assert [(r['text'],r['valid']) for r in result['readings']]==[(r['text'],r['valid']) for r in d['ocr_inputs']],eid
 votes=Counter(r['text'] for r in result['readings'] if r['valid'] and r['confidence']>=.8)
 rows.append(dict(event=eid,status=result['recognition_status'],votes=dict(votes),samples=len(d['samples']),accepted=sum(bool(s.get('raw')) for s in d['samples']),ocr=len(d['ocr_inputs']),dropped=d['dropped_pending'],omitted_images=d['omitted_images'],omitted_samples=d['omitted_samples']))
for r in sorted(rows,key=lambda r:r['event']):print(r)
assert len(rows)==14
print('PASS: 14 archived decisions and OCR validity results reproduced; 10 uncertain, 4 read.')
if '--require-read' in sys.argv:assert all(r['status']=='read' for r in rows),'Archived uncertain passages remain uncertain'
