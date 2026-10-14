import queue
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np

from computer_vision_v2.Line_Manager.line_detector import LineDetector
from computer_vision_v2.ocr_worker.plate_candidates import CompletedPassage, PlateCandidates
from computer_vision_v2.workers.workers import observation_worker
from computer_vision_v2.ocr_worker.ocr_worker_v2 import ocr_worker
from computer_vision_v2.database.database_worker import _save_event


class CrossingRetentionTests(unittest.TestCase):
    def frame(self, x, y, track_id=1):
        detection = SimpleNamespace(track_id=track_id, bbox=(x-1, y-2, x+1, y),
                                    class_id=2, confidence=.9)
        return SimpleNamespace(detections=[detection], image=None, frame_idx=1, ts=1)

    def detector(self):
        return LineDetector('cam', [(0, 10), (10, 10), (10, 20)], 'entry')

    def test_each_edge_crosses_and_shared_track_is_counted_once(self):
        detector = self.detector()
        self.assertEqual(detector.update(self.frame(5, 8)), [])
        self.assertEqual(len(detector.update(self.frame(5, 12))), 1)
        self.assertEqual(detector.update(self.frame(12, 15)), [])
        detector = self.detector()
        self.assertEqual(detector.update(self.frame(8, 15)), [])
        self.assertEqual(len(detector.update(self.frame(12, 15))), 1)

    def test_extension_does_not_count(self):
        detector = self.detector()
        detector.update(self.frame(20, 8))
        self.assertEqual(detector.update(self.frame(20, 12)), [])

    def test_vehicle_reaches_database_only_after_it_leaves(self):
        crop_q, ocr_q, db_q = [queue.Queue() for _ in range(3)]
        event = dict(camera_id='cam', track_id=1, class_id=2,
                     confidence=.9, direction='entry', ts=1)
        crop_q.put(SimpleNamespace(camera_id='cam'))
        crop_q.put(SimpleNamespace(camera_id='cam'))
        crop_q.put(None)
        selector = Mock()
        selector.observe.side_effect = [[], [CompletedPassage(event, [])]]
        lines = Mock()
        lines.update.side_effect = [[event], []]
        observation_worker(crop_q, ocr_q, lines, selector, lambda: True)
        self.assertEqual(ocr_q.qsize(), 1)
        ocr_q.put(None)
        reader = Mock()
        reader.recognize_candidates.return_value = dict(plate_text=None,confidence=0.,
            recognition_status='unread',readings=[],image=None)
        ocr_worker(ocr_q, db_q, reader, lambda: True)
        reader.read.assert_not_called()
        item = db_q.get_nowait()
        self.assertIsNone(item['plate_text'])
        self.assertIsNone(item['image_path'])
        cursor = Mock()
        cursor.fetchone.return_value = (42,)
        self.assertEqual(_save_event(cursor, item), 42)
        self.assertEqual(cursor.execute.call_count, 1)

    def test_crossing_does_not_enter_ocr_queue_while_vehicle_is_visible(self):
        frame_q, ocr_q = queue.Queue(), queue.Queue()
        image = np.zeros((100, 150, 3), np.uint8)
        car = SimpleNamespace(track_id=1, bbox=(10, 10, 100, 90), class_id=2)
        event = dict(camera_id='cam', track_id=1, class_id=2,
                     confidence=.9, direction='entry', ts=0)
        lines = Mock()
        lines.update.side_effect = [[event], [], []]
        reader = Mock()
        reader.detect_plate.return_value = None
        worker = threading.Thread(target=observation_worker,
            args=(frame_q, ocr_q, lines, PlateCandidates(reader), lambda: True))
        worker.start()
        try:
            frame_q.put(SimpleNamespace(camera_id='cam', ts=0, frame_idx=1,
                                        image=image, detections=[car]))
            frame_q.join()
            self.assertTrue(ocr_q.empty())
            frame_q.put(SimpleNamespace(camera_id='cam', ts=.4, frame_idx=13,
                                        image=image, detections=[car]))
            frame_q.join()
            self.assertTrue(ocr_q.empty())
            frame_q.put(SimpleNamespace(camera_id='cam', ts=1.2, frame_idx=37,
                                        image=image, detections=[]))
            frame_q.join()
            self.assertEqual(ocr_q.qsize(), 1)
            self.assertEqual(ocr_q.get_nowait()['event'], event)
        finally:
            frame_q.put(None)
            worker.join(timeout=3)
        self.assertFalse(worker.is_alive())

    def test_stopping_while_car_is_visible_does_not_finalize_it(self):
        frame_q, ocr_q = queue.Queue(), queue.Queue()
        image = np.zeros((100, 150, 3), np.uint8)
        detection = SimpleNamespace(track_id=1, bbox=(10, 10, 100, 90), class_id=2)
        frame_q.put(SimpleNamespace(camera_id='cam', ts=0, frame_idx=1,
                                    image=image, detections=[detection]))
        frame_q.put(None)
        lines = Mock()
        lines.update.return_value = [dict(camera_id='cam', track_id=1,
                                          class_id=2, direction='entry', ts=0)]
        reader = Mock()
        reader.detect_plate.return_value = None
        observation_worker(frame_q, ocr_q, lines, PlateCandidates(reader), lambda: False)
        self.assertTrue(ocr_q.empty())
