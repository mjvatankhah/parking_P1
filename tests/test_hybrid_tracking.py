import unittest
import queue
import json
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

import cv2
import numpy as np

from computer_vision_v2.tracking.frame_info import Detection
from computer_vision_v2.tracking.tracker import CameraTracker
from computer_vision_v2.Line_Manager.line_detector import LineDetector
from computer_vision_v2.ocr_worker.plate_candidates import PlateCandidates
from computer_vision_v2.inference.plate_geometry import PreparedPlate
from computer_vision_v2.workers.workers import observation_worker
from computer_vision_v2.ocr_worker.ocr_worker_v2 import ocr_worker
from computer_vision_v2.tracking.optical_flow import OpticalFlow


def scene(dx=0, dy=0):
    image = np.zeros((180, 240, 3), dtype=np.uint8)
    texture = np.random.default_rng(42).integers(0, 256, (60, 70, 3), dtype=np.uint8)
    image[40 + dy:100 + dy, 50 + dx:120 + dx] = texture
    return image


class HybridTrackingTests(unittest.TestCase):
    def make_tracker(self, interval=3):
        with patch('computer_vision_v2.tracking.tracker.YOLO'):
            # These motion fixtures run at 25 FPS; refresh after 120 ms.
            tracker = CameraTracker('cam', 'unused', interval,
                                    detection_period=interval / 25)
        return tracker

    def test_schedule_motion_and_same_id_across_detector_refresh(self):
        tracker = self.make_tracker()
        boxes = [Detection(7, (50 + dx, 40, 120 + dx, 100), 2, .9) for dx in (0, 9, 18)]
        with patch.object(tracker, '_detect', side_effect=[[box] for box in boxes]) as detect:
            frames = [tracker.process(i + 1, i / 25, scene(dx=i * 3)) for i in range(7)]
        self.assertEqual(detect.call_count, 3)
        self.assertEqual([f.detections[0].is_predicted for f in frames],
                         [False, True, True, False, True, True, False])
        for i, frame in enumerate(frames):
            det = frame.detections[0]
            self.assertEqual(det.track_id, 7)
            self.assertEqual(det.confidence, .9)
            self.assertEqual(frame.frame_idx, i + 1)
            self.assertAlmostEqual(det.bbox[0], 50 + i * 3, delta=1)
        self.assertGreater(frames[1].detections[0].tracking_quality, .5)

    def test_crossing_on_flow_frame_reaches_crop_and_is_not_duplicated(self):
        tracker = self.make_tracker()
        line = LineDetector('cam', line=((0, 105), (240, 105)), direction='entry')
        reader = Mock()
        reader.detect_plate.return_value = (scene()[40:60,50:120], .9, scene()[30:80,40:130])
        selector = PlateCandidates(reader)
        events = []
        boxes = [Detection(7, (50, 40 + dy, 120, 100 + dy), 2, .9) for dy in (0, 24)]
        with patch.object(tracker, '_detect', side_effect=[[box] for box in boxes]), \
             patch('computer_vision_v2.ocr_worker.plate_candidates.prepare_plate',
                   return_value=PreparedPlate(scene()[40:60,50:120],1.)):
            for i in range(4):
                frame = tracker.process(i + 1, i / 25, scene(dy=i * 8))
                crossings = line.update(frame)
                selector.observe(frame, crossings)
                events.extend(crossings)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['frame_idx'], 2)
        self.assertEqual(events[0]['track_id'], 7)
        self.assertEqual(events[0]['direction'], 'entry')
        self.assertEqual(selector.observe(frame), [])
        self.assertTrue(selector.tracks[('cam',7)].candidates)

    def test_crossing_on_detector_frame_still_works(self):
        tracker = self.make_tracker()
        line = LineDetector('cam', line=((0, 120), (240, 120)), direction='exit')
        boxes = [Detection(7, (50, 40 + dy, 120, 100 + dy), 2, .9) for dy in (0, 24)]
        events = []
        with patch.object(tracker, '_detect', side_effect=[[box] for box in boxes]):
            for i in range(4):
                events.extend(line.update(tracker.process(i + 1, i / 25, scene(dy=i * 8))))
        self.assertEqual([(e['frame_idx'], e['direction']) for e in events], [(4, 'exit')])

    def test_both_crossing_sources_reach_ocr_and_database_queue_once(self):
        for line_y in (105, 120):
            with self.subTest(line_y=line_y):
                tracker = self.make_tracker()
                boxes = [Detection(7, (50, 40 + dy, 120, 100 + dy), 2, .9) for dy in (0, 24)]
                with patch.object(tracker, '_detect', side_effect=[[box] for box in boxes]):
                    frames = [tracker.process(i + 1, i / 25, scene(dy=i * 8)) for i in range(4)]
                frame_q, ocr_q, db_q = [queue.Queue() for _ in range(3)]
                for frame in frames:
                    frame_q.put(frame)
                last = frames[-1]
                frame_q.put(type(last)(last.camera_id, last.frame_idx+30, last.ts+1,
                                       last.image, []))
                frame_q.put(None)
                detector = LineDetector('cam', line=((0, line_y), (240, line_y)), direction='entry')
                reader = Mock()
                reader.detect_plate.return_value = None
                observation_worker(frame_q, ocr_q, detector, PlateCandidates(reader), lambda: True)
                reader.recognize_candidates.return_value = dict(plate_text='TEST-PLATE',confidence=.95,
                    recognition_status='read',readings=[],image=None)
                ocr_q.put(None)
                ocr_worker(ocr_q, db_q, reader, lambda: True)
                self.assertEqual(db_q.qsize(), 1)
                record = db_q.get_nowait()
                self.assertEqual(record['track_id'], 7)
                self.assertEqual(record['direction'], 'entry')
                self.assertEqual(record['plate_text'], 'TEST-PLATE')
                reader.recognize_candidates.assert_called_once()

    def test_untrackable_image_falls_back_to_detector(self):
        tracker = self.make_tracker()
        with patch.object(tracker, '_detect', return_value=[Detection(7, (50, 40, 120, 100), 2, .9)]) as detect:
            tracker.process(1, 0, scene())
            result = tracker.process(2, .04, np.zeros_like(scene()))
        self.assertEqual(detect.call_count, 2)
        self.assertFalse(result.detections[0].is_predicted)
        self.assertEqual(tracker.flow_fallbacks, 1)

    def test_gap_and_resolution_change_force_detection(self):
        for index, ts, image in [(1, .04, scene()), (2, 0, scene()), (2, 2, scene()),
                                 (2, .04, cv2.resize(scene(), (120, 90)))]:
            with self.subTest(index=index, ts=ts, shape=image.shape):
                tracker = self.make_tracker()
                with patch.object(tracker, '_detect', return_value=[]) as detect:
                    tracker.process(1, 0, scene())
                    tracker.process(index, ts, image)
                self.assertEqual(detect.call_count, 2)

    def test_forward_frame_skip_uses_flow_before_time_deadline(self):
        tracker = self.make_tracker()
        with patch.object(tracker, '_detect', return_value=[Detection(7, (50,40,120,100),2,.9)]) as detect:
            tracker.process(1, 0, scene())
            frame = tracker.process(4, .04, scene(dx=3))
        self.assertEqual(detect.call_count, 1)
        self.assertTrue(frame.detections[0].is_predicted)

    def test_default_refresh_is_time_based(self):
        with patch('computer_vision_v2.tracking.tracker.YOLO'):
            tracker = CameraTracker('cam', 'unused')
        with patch.object(tracker, '_detect', return_value=[]) as detect:
            for index, ts in [(1,0.), (4,.04), (10,.1), (16,.15), (20,.199)]:
                tracker.process(index, ts, scene())
            self.assertEqual(detect.call_count, 1)
            tracker.process(21,.2,scene())
            self.assertEqual(detect.call_count, 2)

    def test_fast_motion_still_emits_entry(self):
        tracker = self.make_tracker()
        line = LineDetector('cam', line=((0,120),(240,120)), direction='entry')
        boxes = [[Detection(7,(50,40,120,100),2,.9)],
                 [Detection(7,(50,90,120,150),2,.9)]]
        with patch.object(tracker, '_detect', side_effect=boxes) as detect:
            self.assertEqual(line.update(tracker.process(1,0,scene())), [])
            events = line.update(tracker.process(2,.04,scene(dy=50)))
        self.assertEqual([e['direction'] for e in events], ['entry'])

    def test_empty_scene_keeps_periodic_detection_for_new_arrivals(self):
        tracker = self.make_tracker()
        with patch.object(tracker, '_detect', return_value=[]) as detect:
            for i in range(7):
                self.assertEqual(tracker.process(i + 1, i / 25, scene()).detections, [])
        self.assertEqual(detect.call_count, 3)

    def test_interval_one_is_detector_only(self):
        tracker = self.make_tracker(1)
        with patch.object(tracker, '_detect', return_value=[]) as detect, patch.object(tracker.flow, 'seed') as seed:
            for i in range(4):
                tracker.process(i + 1, i / 25, scene())
        self.assertEqual(detect.call_count, 4)
        seed.assert_not_called()

    def test_default_fields_are_backwards_compatible(self):
        det = Detection(1, (1, 2, 3, 4), 2, .9)
        self.assertFalse(det.is_predicted)
        self.assertIsNone(det.tracking_quality)

    def test_invalid_intervals(self):
        for value in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                self.make_tracker(value)

    def test_small_rotation_does_not_inflate_bbox(self):
        flow = OpticalFlow()
        flow.seed(scene(), [Detection(7, (50, 40, 120, 100), 2, .9)])
        matrix = cv2.getRotationMatrix2D((85, 70), 5, 1)
        rotated = cv2.warpAffine(scene(), matrix, (240, 180))
        detections = flow.advance(rotated)
        self.assertIsNotNone(detections)
        x1, y1, x2, y2 = detections[0].bbox
        self.assertAlmostEqual(x2 - x1, 70, delta=2)
        self.assertAlmostEqual(y2 - y1, 60, delta=2)

    def test_ui_save_preserves_detection_interval(self):
        from reno.services.camera_service import CameraService
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cameras.json'
            path.write_text(json.dumps({'model_path': 'test.pt', 'detection_interval': 1, 'cameras': []}))
            service = CameraService()
            service._store_path = str(path)
            service._cameras = service._load()
            service._save()
            self.assertEqual(json.loads(path.read_text())['detection_interval'], 1)


if __name__ == '__main__':
    unittest.main()
