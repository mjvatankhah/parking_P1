"""Real deployed OCR on saved evidence from both videos; no detector or DB."""
import json
from pathlib import Path
import unittest
import cv2
from computer_vision_v2.inference.plate_ocr import PlateReader, _session, DEFAULT_OCR, DEFAULT_LABELS
from computer_vision_v2.inference.plate_geometry import PreparedPlate
from computer_vision_v2.ocr_worker.plate_candidates import Candidate
ROOT=Path(__file__).parent/'fixtures/plate_evidence'
class EvidenceRegressionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  r=PlateReader.__new__(PlateReader);r.ocr=_session(DEFAULT_OCR);r.ocr_input=r.ocr.get_inputs()[0].name
  r.ocr_c,r.ocr_h,r.ocr_w=r.ocr.get_inputs()[0].shape[1:];r.labels=r._load_labels(DEFAULT_LABELS);cls.reader=r
 def test_known_plates_survive_on_both_videos(self):
  for case in json.loads((ROOT/'manifest.json').read_text()):
   with self.subTest(case=case['case']):
    candidates=[]
    for c in case['candidates']:
     crop=cv2.imread(str(ROOT/c['raw_file']));prepared=PreparedPlate(cv2.imread(str(ROOT/c['prepared_file'])),c['geometry_quality']) if 'prepared_file' in c else None
     candidates.append(Candidate(crop,c['ts'],c['frame'],c['confidence'],c['quality'],prepared=prepared))
    result=self.reader.recognize_candidates(candidates)
    self.assertEqual(result['recognition_status'],'read',result['readings'])
    self.assertEqual(result['plate_text'],case['expected'])
