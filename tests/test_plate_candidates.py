import unittest
from unittest.mock import Mock, patch
import numpy as np
from computer_vision_v2.ocr_worker.plate_candidates import PlateCandidates, Candidate
from computer_vision_v2.tracking.frame_info import Detection, TrackedFrame
from computer_vision_v2.inference.plate_ocr import PlateReader
from computer_vision_v2.inference.plate_geometry import PreparedPlate


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.crop = np.random.default_rng(7).integers(20,230,(25,100,3),dtype=np.uint8)
        self.reader = Mock()
        self.reader.detect_plate.return_value = (self.crop,.9,self.crop)
        self.pool = PlateCandidates(self.reader)
        geometry = patch('computer_vision_v2.ocr_worker.plate_candidates.prepare_plate',
                         return_value=PreparedPlate(self.crop,1.))
        self.geometry = geometry.start()
        self.addCleanup(geometry.stop)

    def frame(self, ts, camera='cam', track=1, bbox=(1,1,140,90)):
        return TrackedFrame(camera,round(ts*30),ts,np.zeros((100,150,3),np.uint8),
                            [Detection(track,bbox,2,.9)] if track is not None else [])

    @staticmethod
    def crossing(track=1, ts=.6):
        return dict(camera_id='cam',track_id=track,ts=ts,class_id=2,direction='entry')

    def test_bounded_diverse_and_closed_after_leaving(self):
        for i in range(100):
            self.pool.observe(self.frame(i*.1))
        state = self.pool.tracks[('cam',1)]
        self.assertLessEqual(len(state.candidates),12)
        for a in state.candidates:
            for b in state.candidates:
                if a is not b:
                    self.assertGreaterEqual(abs(a.ts-b.ts),.09)
        self.assertEqual(self.pool.observe(self.frame(9.9), [self.crossing(ts=9.9)]), [])
        self.pool.observe(self.frame(10.))
        result = self.pool.observe(self.frame(10.8,track=None))
        self.assertEqual(len(result),1)
        self.assertTrue(result[0].candidates)
        self.assertNotIn(('cam',1),self.pool.tracks)

    def test_camera_and_track_isolation_expiry(self):
        self.pool.observe(self.frame(0))
        self.pool.observe(self.frame(0,'other'))
        self.pool.observe(self.frame(6,track=2))
        self.assertNotIn(('cam',1),self.pool.tracks)
        self.assertIn(('other',1),self.pool.tracks)

    def test_wheel_is_only_fallback(self):
        self.reader.detect_plate.return_value=(np.tile(self.crop[:,:40],(2,1,1)),.95,None)
        self.pool.observe(self.frame(0))
        state=self.pool.tracks[('cam',1)]
        self.assertEqual(state.candidates,[])
        self.assertIsNotNone(state.fallback)

    def test_valid_geometry_replaces_failed_nearby_crop(self):
        self.geometry.side_effect=[None,PreparedPlate(self.crop,1.)]
        self.pool.observe(self.frame(0))
        self.pool.observe(self.frame(.1))
        state=self.pool.tracks[('cam',1)]
        self.assertEqual([c.frame_idx for c in state.candidates],[3])
        self.assertEqual(state.fallback.frame_idx,0)

    def test_vote_states_include_nearby_frames_and_limit_to_five(self):
        reader=PlateReader.__new__(PlateReader)
        reader.labels=['م'];reader.ocr=Mock();reader.ocr_input='input'
        reader.ocr.run.return_value=[None]
        reader._prep_ocr=Mock(return_value=None)
        candidates=[Candidate(self.crop,t,i,.9,1.) for i,t in enumerate([0,.1,.2,.3,.4,.5])]
        for outputs,status in [([('58م87245',.95)]*5,'read'),
                               ([('58م87245',.95),('58م87246',.95),('',0),('',0),('',0)],'uncertain'),
                               ([('',0)]*5,'unread')]:
            reader._ctc_decode=Mock(side_effect=outputs)
            with patch('computer_vision_v2.inference.plate_ocr.prepare_plate',return_value=PreparedPlate(self.crop,1.)):
                result=reader.recognize_candidates(candidates)
            self.assertEqual(result['recognition_status'],status)
            self.assertEqual([r['frame_idx'] for r in result['readings']],[0,1,2,3,4])
            if status!='read':self.assertIsNone(result['plate_text'])

    def test_failed_geometry_reads_raw_and_keeps_review_image(self):
        reader=PlateReader.__new__(PlateReader)
        reader.labels=['X'];reader.ocr=Mock();reader.ocr_input='input'
        reader.ocr.run.return_value=[None];reader._prep_ocr=Mock(return_value=None)
        reader._ctc_decode=Mock(return_value=('12X34567',.99))
        with patch('computer_vision_v2.inference.plate_ocr.prepare_plate',return_value=None):
            result=reader.recognize_candidates([Candidate(self.crop,0.,1,.9,1.)])
        reader.ocr.run.assert_called_once()
        self.assertEqual(result['recognition_status'],'uncertain')
        self.assertIs(result['image'],self.crop)

    def test_one_clear_ocr_reading_is_still_uncertain(self):
        reader=PlateReader.__new__(PlateReader)
        reader.labels=['م'];reader.ocr=Mock();reader.ocr_input='input'
        reader.ocr.run.return_value=[None]
        reader._prep_ocr=Mock(return_value=None)
        reader._ctc_decode=Mock(return_value=('58م87245',.99))
        with patch('computer_vision_v2.inference.plate_ocr.prepare_plate',
                   return_value=PreparedPlate(self.crop,1.)):
            result=reader.recognize_candidates([Candidate(self.crop,0.,1,.9,1.)])
        self.assertEqual(result['recognition_status'],'uncertain')
        self.assertEqual(result['readings'][0]['text'],'58م87245')
        self.assertIsNone(result['plate_text'])

    def test_crossing_collects_later_frames_until_vehicle_leaves(self):
        self.pool.observe(self.frame(0))
        self.assertEqual(self.pool.observe(self.frame(.6), [self.crossing()]), [])
        self.pool.observe(self.frame(1.2))
        self.assertEqual(self.pool.observe(self.frame(1.5,track=None)), [])
        completed=self.pool.observe(self.frame(2.,track=None))
        self.assertEqual(len(completed),1)
        self.assertIn(round(1.2*30), [c.frame_idx for c in completed[0].candidates])
        self.assertEqual(self.pool.observe(self.frame(2.1)), [])

    def test_new_id_after_crossing_keeps_one_event_and_later_plate(self):
        self.pool.observe(self.frame(0))
        self.assertEqual(self.pool.observe(self.frame(.6), [self.crossing()]), [])
        self.assertEqual(self.pool.observe(self.frame(.8,track=2,bbox=(30,20,100,93))), [])
        self.assertEqual(self.pool.aliases[('cam',2)], ('cam',1))
        self.pool.observe(self.frame(1.2,track=2,bbox=(30,20,100,93)), [self.crossing(2,1.2)])
        completed=self.pool.observe(self.frame(2.,track=None))
        self.assertEqual(len(completed),1)
        self.assertEqual(completed[0].event['track_id'],1)
        self.assertTrue(any(c.ts>0.6 for c in completed[0].candidates))
        self.assertEqual(self.pool.observe(self.frame(2.1,track=2)), [])

    def test_simultaneous_cars_do_not_share_plate_candidates(self):
        image=np.zeros((100,150,3),np.uint8)
        frame=lambda t, dets:TrackedFrame('cam',round(t*30),t,image,dets)
        both=[Detection(1,(0,0,50,80),2,.9),Detection(2,(90,0,140,80),2,.9)]
        self.pool.observe(frame(0,both))
        self.pool.observe(frame(.6,both),[self.crossing(1,.6),self.crossing(2,.6)])
        self.pool.observe(frame(.9,[both[1]]))
        completed=self.pool.observe(frame(1.4,[both[1]]))
        self.assertEqual([p.event['track_id'] for p in completed],[1])
        self.assertIn(('cam',2),self.pool.tracks)
        completed=self.pool.observe(frame(2.2,[]))
        self.assertEqual([p.event['track_id'] for p in completed],[2])

    def test_ambiguous_new_id_is_not_assigned_to_either_car(self):
        image=np.zeros((100,150,3),np.uint8)
        frame=lambda t, dets:TrackedFrame('cam',round(t*30),t,image,dets)
        first=Detection(1,(0,0,80,80),2,.9)
        second=Detection(2,(40,0,120,80),2,.9)
        replacement=Detection(3,(20,0,100,80),2,.9)
        self.pool.observe(frame(0,[first,second]))
        self.pool.observe(frame(.2,[replacement]))
        self.assertEqual(self.pool.aliases[('cam',3)],('cam',3))

    def test_slightly_over_thirty_fps_keeps_detector_frame_sampling(self):
        sampled=[]
        def detect(vehicle):
            sampled.append(int(vehicle[0,0,0]))
            return self.crop,.9,self.crop
        self.reader.detect_plate.side_effect=detect
        for idx in range(2136,2144):
            image=np.full((100,150,3),idx%256,np.uint8)
            det=Detection(1,(1,1,140,90),2,.9,is_predicted=(idx%3!=0))
            frame=TrackedFrame('cam',idx,idx/30.01544071471942,image,[det])
            self.pool.observe(frame)
        self.assertEqual(sampled,[2136%256,2139%256,2142%256])
