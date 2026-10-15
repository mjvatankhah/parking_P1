"""Replay cached real crops through production OCR; no detector or DB required."""
import argparse,json
from pathlib import Path
import cv2
from computer_vision_v2.inference.plate_ocr import PlateReader, _session, DEFAULT_OCR, DEFAULT_LABELS
from computer_vision_v2.inference.plate_geometry import PreparedPlate
from computer_vision_v2.ocr_worker.plate_candidates import Candidate
p=argparse.ArgumentParser();p.add_argument('--assert-read',action='store_true');p.add_argument('--raw',action='store_true');p.add_argument('--minimal',action='store_true');args=p.parse_args()
out=Path(__file__).resolve().parent
reader=PlateReader.__new__(PlateReader);reader.ocr=_session(DEFAULT_OCR)
reader.ocr_input=reader.ocr.get_inputs()[0].name
reader.ocr_c,reader.ocr_h,reader.ocr_w=reader.ocr.get_inputs()[0].shape[1:]
reader.labels=reader._load_labels(DEFAULT_LABELS)
def decode(image):
 text,confidence=reader._ctc_decode(reader.ocr.run(None,{reader.ocr_input:reader._prep_ocr(image)})[0])
 return dict(text=text,confidence=confidence,size=list(image.shape[1::-1]))
rows=[]
for number,event in enumerate(json.loads((out/'events.json').read_text()),1):
 if number>2 or (args.minimal and number!=2):continue
 candidates=[];raw_candidates=[];comparisons=[]
 for i,c in enumerate(event['candidates']):
  if args.minimal and c['frame'] not in (10,20):continue
  raw=cv2.imread(str(out/f'event_{number}_candidate_{i}_raw.png'))
  prepared_path=out/f'event_{number}_candidate_{i}_prepared.png'
  prepared=cv2.imread(str(prepared_path)) if prepared_path.exists() else None
  raw_candidates.append(Candidate(raw,c['ts'],c['frame'],c['confidence'],c['quality'],prepared=PreparedPlate(raw,1.)))
  comparisons.append(dict(frame=c['frame'],raw=decode(raw),prepared=decode(prepared) if prepared is not None else None))
  if prepared is not None:
   candidates.append(Candidate(raw,c['ts'],c['frame'],c['confidence'],c['quality'],prepared=PreparedPlate(prepared,1.)))
 result=reader.recognize_candidates(candidates);result.pop('image')
 raw_result=reader.recognize_candidates(raw_candidates);raw_result.pop('image')
 row=dict(raw_result=raw_result,event=number,track=event['event']['track_id'],captured_status=event['result']['recognition_status'],cached_result=result,comparisons=comparisons);rows.append(row)
 print(json.dumps(row,ensure_ascii=False),flush=True)
(out/('minimal_ocr_comparison.json' if args.minimal else 'cached_ocr_comparison.json')).write_text(json.dumps(rows,ensure_ascii=False,indent=2))
if args.assert_read:
 event=next(r for r in rows if r['event']==2)
 result=event['raw_result'] if args.raw else event['cached_result']
 assert result['recognition_status']=='read' and result['plate_text']=='93ب52733', 'Real event 2 remains uncertain despite readable raw plate crops'
