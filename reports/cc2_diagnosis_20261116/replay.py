"""Replay archived cc2 OCR inputs through the real voting path; no DB writes."""
import json,sys
from pathlib import Path
from unittest.mock import patch
import cv2
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from computer_vision_v2.inference.plate_ocr import PlateReader,DEFAULT_LABELS
from computer_vision_v2.inference.plate_geometry import PreparedPlate
from computer_vision_v2.ocr_worker.plate_candidates import Candidate,PassageCandidates
p=ROOT/'reports/crop_diagnostics/ea65aeaf4b84465dbd587345211e5b9e'
d=json.loads((p/'manifest.json').read_text())
reader=PlateReader.__new__(PlateReader)
reader.labels=json.loads(DEFAULT_LABELS.read_text())
answers={};candidates=[];groups={s:{'quality':[],'recent':[]} for s in ('raw','geometry')}
for r in d['ocr_inputs']:
 im=cv2.imread(str(p/r['image']));answers[im.tobytes()]=(r['text'],r['confidence'])
 candidates.append(Candidate(im,r['frame_idx']/25,r['frame_idx'],1,1,prepared=PreparedPlate(im,1) if r['source']=='geometry' else None))
 groups[r['source']]['quality'].append(r['frame_idx'])
reader._recognize_batch=lambda ims:[answers[im.tobytes()] for im in ims]
with patch('computer_vision_v2.inference.plate_ocr.prepare_plate',return_value=None):
 result=reader.recognize_candidates(PassageCandidates(candidates,groups))
print('event=457 expected moving=97ن32977 actual=',result['plate_text'],result['recognition_status'])
assert result['plate_text']==d['result']['plate_text'], 'Replay differs from archive'
if '--require-moving' in sys.argv:
 assert result['plate_text']=='97ن32977','Parked vehicle plate assigned to moving vehicle passage'
