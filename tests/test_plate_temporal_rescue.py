"""Readable middle views survive stronger but unreadable early/late crops."""
import unittest
from unittest.mock import patch
import numpy as np
from computer_vision_v2.ocr_worker.plate_candidates import PlateCandidates,Candidate,TrackEvidence
from computer_vision_v2.inference.plate_ocr import PlateReader

class TemporalRescueTests(unittest.TestCase):
    def passage(self, answers):
        reader=PlateReader.__new__(PlateReader);reader.labels=['م']
        reader._recognize_batch=lambda images:[answers[int(im[0,0,0])] for im in images]
        pool=PlateCandidates(reader);state=TrackEvidence(0,(),event={'class_id':2})
        for i in range(len(answers)):
            crop=np.full((24,100,3),i,np.uint8)
            pool._store_candidate(state,Candidate(crop,i*.2,i,.9,1. if i<3 else .7))
        pool.tracks['test']=state
        return reader,pool._retire('test',0).candidates

    def test_readable_middle_views_rescued_without_lowering_threshold(self):
        answers=[('8م8724',.95)]*16
        answers[5:11]=[('58م87245',.91)]*6
        reader,candidates=self.passage(answers)
        with patch('computer_vision_v2.inference.plate_ocr.prepare_plate',return_value=None):
            result=reader.recognize_candidates(candidates)
        self.assertEqual(result['plate_text'],'58م87245')
        self.assertLessEqual(len(result['readings']),17)

    def test_rescue_does_not_promote_low_confidence_or_tied_reads(self):
        for middle in [ [('58م87245',.79)]*2,
                        [('58م87245',.91),('58م87345',.91)] ]:
            answers=[('8م8724',.95)]*16;answers[6],answers[8]=middle
            reader,candidates=self.passage(answers)
            with patch('computer_vision_v2.inference.plate_ocr.prepare_plate',return_value=None):
                result=reader.recognize_candidates(candidates)
            self.assertEqual(result['recognition_status'],'uncertain')

    def test_confirmed_first_pass_does_not_run_extra_ocr(self):
        reader,candidates=self.passage([('58م87245',.95)]*16)
        with patch('computer_vision_v2.inference.plate_ocr.prepare_plate',return_value=None):
            result=reader.recognize_candidates(candidates)
        self.assertEqual(len(result['readings']),5)

    def test_reserve_is_bounded_for_long_tracks(self):
        _,candidates=self.passage([('',0.)]*200)
        self.assertLessEqual(len(candidates),18)
        groups=candidates.selection_groups['raw']
        self.assertIn('temporal',groups)
        self.assertLessEqual(len(groups['temporal']),12)

class GeometryGuardTests(unittest.TestCase):
    def test_text_free_deskew_band_is_rejected(self):
        from computer_vision_v2.inference.plate_geometry import PreparedPlate,prepare_plate
        band=np.full((20,100,3),220,np.uint8);band[8:13,:]=20
        with patch('computer_vision_v2.inference.plate_geometry._prepare_deskew',return_value=PreparedPlate(band,.9)), patch('computer_vision_v2.inference.plate_geometry._rectify_plate',return_value=None):
            self.assertIsNone(prepare_plate(band))

    def test_complete_text_band_survives_guard(self):
        from computer_vision_v2.inference.plate_geometry import PreparedPlate,prepare_plate
        band=np.full((24,120,3),220,np.uint8)
        for x in range(8,112,13):band[5:20,x:x+6]=20
        prepared=PreparedPlate(band,.9)
        with patch('computer_vision_v2.inference.plate_geometry._prepare_deskew',return_value=prepared), patch('computer_vision_v2.inference.plate_geometry._rectify_plate',return_value=None):
            self.assertIs(prepare_plate(band),prepared)

class PaddingRescueTests(unittest.TestCase):
    passage = TemporalRescueTests.passage
    def test_margin_rescues_missing_digit_on_two_distinct_frames(self):
        reader,candidates=self.passage([('8م87245',.95)]*2)
        reader._recognize_batch=lambda images:[('58م87245',.95) if im.shape[1]>100 else ('8م87245',.95) for im in images]
        with patch('computer_vision_v2.inference.plate_ocr.prepare_plate',return_value=None):
            result=reader.recognize_candidates(candidates)
        self.assertEqual(result['plate_text'],'58م87245')
        self.assertEqual(sum(r['source']=='padded' for r in result['readings']),2)

    def test_one_frame_cannot_confirm_itself_by_padding(self):
        reader,candidates=self.passage([('58م87245',.95)])
        with patch('computer_vision_v2.inference.plate_ocr.prepare_plate',return_value=None):
            result=reader.recognize_candidates(candidates)
        self.assertEqual(result['recognition_status'],'uncertain')
        self.assertFalse(any(r['source']=='padded' for r in result['readings']))

    def test_diagnostics_record_exact_padded_input(self):
        import json,tempfile
        from pathlib import Path
        import cv2
        from computer_vision_v2.ocr_worker.crop_diagnostics import EvidenceTrace
        from computer_vision_v2.inference.plate_ocr import _pad_ocr_crop
        reader,candidates=self.passage([('8م87245',.95)]*2)
        reader._recognize_batch=lambda images:[('58م87245',.95) if im.shape[1]>100 else ('8م87245',.95) for im in images]
        with tempfile.TemporaryDirectory() as directory:
            candidates.trace=EvidenceTrace(directory)
            with patch('computer_vision_v2.inference.plate_ocr.prepare_plate',return_value=None):
                result=reader.recognize_candidates(candidates)
            path=Path(candidates.trace.save({'direction':'entry'},result,candidates))
            manifest=json.loads((path/'manifest.json').read_text())
            padded=[r for r in manifest['ocr_inputs'] if r['source']=='padded']
            self.assertEqual(len(padded),2)
            for r in padded:
                candidate=next(c for c in candidates if c.frame_idx==r['frame_idx'])
                np.testing.assert_array_equal(cv2.imread(str(path/r['image'])),_pad_ocr_crop(candidate.crop))
