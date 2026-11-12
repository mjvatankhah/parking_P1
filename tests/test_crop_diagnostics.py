import json
import queue
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import cv2
import numpy as np

from computer_vision_v2.ocr_worker.crop_diagnostics import EvidenceTrace, link_event
from computer_vision_v2.ocr_worker.plate_candidates import PlateCandidates
from computer_vision_v2.ocr_worker.ocr_worker_v2 import ocr_worker
from computer_vision_v2.inference.plate_ocr import PlateReader
from computer_vision_v2.inference.plate_geometry import PreparedPlate
from computer_vision_v2.tracking.frame_info import Detection, TrackedFrame


class CropDiagnosticsTests(unittest.TestCase):
    def passage(self, directory, enabled=True):
        raw=np.random.default_rng(13).integers(0,255,(30,120,3),dtype=np.uint8)
        geometry=raw[2:-2,3:-3].copy()
        reader=Mock()
        reader.detect_plate.return_value=(raw,.95,raw)
        reader.last_detection_details={'attempts':[{'plate_bbox_in_vehicle':[2,2,122,32]}]}
        pool=PlateCandidates(reader, diagnostics={'enabled':enabled,'directory':directory})
        event=dict(camera_id='cam',track_id=1,class_id=2,direction='exit',bbox=(20,20,180,100))
        with patch('computer_vision_v2.ocr_worker.plate_candidates.prepare_plate',return_value=PreparedPlate(geometry,.8)):
            for i in range(5):
                frame=TrackedFrame('cam',i,i*.2,np.zeros((140,220,3),np.uint8),[Detection(1,(20,20,180,100),2,.9)])
                pool.observe(frame,[event] if i==2 else [])
            passage=pool.observe(TrackedFrame('cam',30,2.,frame.image,[]))[0]
        ocr=PlateReader.__new__(PlateReader)
        ocr.labels=['ب']
        ocr._recognize_batch=lambda images:[('12ب34567',.95) for _ in images]
        return passage,ocr,raw,geometry

    def test_exit_archive_contains_exact_ocr_images_and_database_link(self):
        with tempfile.TemporaryDirectory() as directory:
            passage,reader,raw,geometry=self.passage(directory)
            incoming,outgoing=queue.Queue(),queue.Queue()
            incoming.put({'event':passage.event,'candidates':passage.candidates,'trace':passage.trace})
            incoming.put(None)
            with patch('computer_vision_v2.ocr_worker.ocr_worker_v2.PLATE_IMAGE_DIR',Path(directory)/'previews'):
                ocr_worker(incoming,outgoing,reader,lambda:True)
            saved=outgoing.get_nowait()
            self.assertEqual(saved['recognition_status'],'read')
            report=Path(saved['diagnostics_path'])
            link_event(report,987)
            manifest=json.loads((report/'manifest.json').read_text())
            self.assertEqual(manifest['database_event_id'],987)
            self.assertEqual(manifest['event']['direction'],'exit')
            self.assertTrue(manifest['crossing']['image'])
            self.assertTrue(manifest['selection_decisions'])
            self.assertTrue(manifest['samples'][0]['vehicle_bbox'])
            self.assertEqual({r['source'] for r in manifest['ocr_inputs']},{'raw','geometry'})
            for row in manifest['ocr_inputs']:
                expected=raw if row['source']=='raw' else geometry
                np.testing.assert_array_equal(cv2.imread(str(report/row['image'])),expected)
            self.assertIn('987',(report/'index.html').read_text())
            # Instrumentation cannot affect text, status, or votes.
            other,reader2,_,_=self.passage(directory,enabled=False)
            baseline=reader2.recognize_candidates(other.candidates)
            self.assertEqual(saved['readings'],baseline['readings'])
            self.assertEqual(saved['plate_text'],baseline['plate_text'])

    def test_failed_plate_detection_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            from computer_vision_v2.ocr_worker.plate_candidates import VehicleSample
            reader=Mock();reader.detect_plate.return_value=None;reader.last_detection_details={'reason':'miss'}
            pool=PlateCandidates(reader)
            trace=EvidenceTrace(directory)
            image=np.zeros((80,150,3),np.uint8)
            pool._detect_sample(VehicleSample(image,1.,1,trace))
            path=trace.save({'direction':'exit'},{'recognition_status':'unread'},[])
            data=json.loads((Path(path)/'manifest.json').read_text())
            self.assertEqual(data['samples'][0]['reason'],'no_accepted_plate_detection')
            self.assertTrue(data['samples'][0]['vehicle'])

    def test_limits_are_explicit(self):
        from computer_vision_v2.ocr_worker.plate_candidates import VehicleSample
        trace=EvidenceTrace(max_samples=1,max_bytes=1)
        sample=VehicleSample(np.zeros((20,50,3),np.uint8),1.,1)
        trace.sample(sample,None);trace.sample(sample,None)
        self.assertEqual(trace.omitted_samples,1)
        self.assertEqual(trace.omitted_images,1)
        self.assertEqual(trace.bytes,0)

    def test_archive_failure_does_not_block_recognition(self):
        with tempfile.TemporaryDirectory() as directory:
            passage,reader,_,_=self.passage(directory)
            with patch('pathlib.Path.mkdir',side_effect=OSError('disk unavailable')):
                self.assertIsNone(passage.trace.save(passage.event,{},passage.candidates))
            self.assertEqual(reader.recognize_candidates(passage.candidates)['recognition_status'],'read')

if __name__=='__main__':
    unittest.main()
