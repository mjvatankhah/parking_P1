"""Replay current crop retention/preparation/OCR on archived lossless raw/context."""
import json,sys,time
from pathlib import Path
from collections import Counter
import cv2,torch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from computer_vision_v2.ocr_worker.plate_candidates import PlateCandidates,Candidate,TrackEvidence
from computer_vision_v2.inference.plate_ocr import PlateReader,DEFAULT_LABELS,MODEL_DIR
from computer_vision_v2.inference.plate_geometry import prepare_plate
from computer_vision_v2.inference.hezar_ocr import HezarOCR
OUT=Path(__file__).resolve().parent;torch.set_num_threads(2)
reader=PlateReader.__new__(PlateReader);reader.labels=json.loads(DEFAULT_LABELS.read_text());reader.ocr=HezarOCR(MODEL_DIR)
results=[]
for audit in json.loads((OUT/'all_ocr.json').read_text()):
 d=json.loads(Path(audit['manifest']).read_text());root=Path(audit['manifest']).parent
 pool=PlateCandidates(reader);state=TrackEvidence(0,(),event=d['event']);start=time.monotonic()
 for s in d['samples']:
  if not s.get('raw'):continue
  raw=cv2.imread(str(root/s['raw']));context=cv2.imread(str(root/s['context'])) if s.get('context') else raw
  h,w=raw.shape[:2];prepared=prepare_plate(context) if 1.15<=w/h<=8 else None
  c=Candidate(raw,s['ts'],s['frame_idx'],s['confidence'],s['quality'],context,prepared)
  pool._store_candidate(state,c)
 pool.tracks['replay']=state;candidates=pool._retire('replay',0).candidates
 result=reader.recognize_candidates(candidates)
 if result['image'] is not None:cv2.imwrite(str(OUT/f"fixed-{audit['event']}.png"),result['image'])
 result.pop('image',None);result.update(event=audit['event'],retained=len(candidates),seconds=time.monotonic()-start);results.append(result)
 print(audit['event'],result['recognition_status'],result['plate_text'],'readings',len(result['readings']),Counter(r['text'] for r in result['readings'] if r['valid'] and r['confidence']>=.8),'seconds',round(result['seconds'],2),flush=True)
 (OUT/'live_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))

if "--require-read" in sys.argv:
 assert len(results)==8 and all(r["recognition_status"]=="read" for r in results), "Unresolved archived passages"
