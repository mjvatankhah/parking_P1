"""Replay actual retention and OCR decisions on available samples, using cached real OCR."""
import json,sys,hashlib
from pathlib import Path
from collections import Counter
from unittest.mock import patch
import cv2
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from computer_vision_v2.ocr_worker.plate_candidates import PlateCandidates,Candidate,TrackEvidence
from computer_vision_v2.inference.plate_ocr import PlateReader,DEFAULT_LABELS,_pad_ocr_crop
from computer_vision_v2.inference.plate_geometry import PreparedPlate,has_text_support
OUT=Path(__file__).resolve().parent
padding={event['event']:{r['frame']:r for r in event['rows']}
         for event in json.loads((OUT/'padding.json').read_text())}
def key(im):return im.shape,hashlib.sha256(im.tobytes()).digest()
results=[]
for audit in json.loads((OUT/'all_ocr.json').read_text()):
 d=json.loads(Path(audit['manifest']).read_text());root=Path(audit['manifest']).parent
 cache={(r['frame'],r['source']):r for r in audit['rows']}; answers={}
 reader=PlateReader.__new__(PlateReader);reader.labels=json.loads(DEFAULT_LABELS.read_text())
 reader._recognize_batch=lambda imgs:[answers[key(im)] for im in imgs]
 pool=PlateCandidates(reader);state=TrackEvidence(0,(),event=d['event'])
 for s in d['samples']:
  if not s.get('raw'):continue
  raw=cv2.imread(str(root/s['raw']));r=cache[s['frame_idx'],'raw'];answers[key(raw)]=(r['text'],r['confidence'])
  padded=padding[audit['event']][s['frame_idx']];answers[key(_pad_ocr_crop(raw))]=(padded['text'],padded['confidence'])
  geo=None
  if s.get('geometry'):
   geo=cv2.imread(str(root/s['geometry']));r=cache[s['frame_idx'],'geometry'];answers[key(geo)]=(r['text'],r['confidence'])
  if '--geometry-guard' in sys.argv and geo is not None and not has_text_support(geo):geo=None
  c=Candidate(raw,s['ts'],s['frame_idx'],s['confidence'],s['quality'],raw,PreparedPlate(geo,s['geometry_quality']) if geo is not None else None)
  pool._store_candidate(state,c)
 pool.tracks['replay']=state;candidates=pool._retire('replay',0).candidates
 with patch('computer_vision_v2.inference.plate_ocr.prepare_plate',return_value=None):result=reader.recognize_candidates(candidates)
 result.pop('image',None);result['event']=audit['event'];result['retained']=len(candidates);results.append(result)
 print(audit['event'],result['recognition_status'],result['plate_text'],'readings',len(result['readings']),Counter(r['text'] for r in result['readings'] if r['valid'] and r['confidence']>=.8))
filename=sys.argv[1] if len(sys.argv)>1 else 'selection.json';(OUT/filename).write_text(json.dumps(results,ensure_ascii=False,indent=2))

if "--require-read" in sys.argv:
 assert len(results)==8 and all(r["recognition_status"]=="read" for r in results), "Unresolved archived passages"
