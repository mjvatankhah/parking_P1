import queue
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from computer_vision_v2.Line_Manager.line_detector import LineDetector
from computer_vision_v2.workers.workers import crop_worker
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

    def test_independent_lines_share_deduplication_without_connecting_edge(self):
        def make():
            return LineDetector('cam', direction='entry', lines=[
                {'line': [(0, 10), (10, 10)]},
                {'line': [(20, 20), (30, 20)]}])
        detector = make()
        detector.update(self.frame(5, 8))
        self.assertEqual(len(detector.update(self.frame(5, 12))), 1)
        detector.update(self.frame(25, 18))
        self.assertEqual(detector.update(self.frame(25, 22)), [])
        # A different track can enter through the second line first.
        detector.update(self.frame(25, 18, track_id=2))
        self.assertEqual(len(detector.update(self.frame(25, 22, track_id=2))), 1)
        detector = make()
        detector.update(self.frame(15, 8))
        self.assertEqual(detector.update(self.frame(15, 25)), [])

    def test_independent_line_config_survives_camera_roundtrip(self):
        from computer_vision_v2.reno.models.camera import Camera
        definitions = [{'line': [[0, .2], [.4, .2]], 'dir': 'entry'},
                       {'line': [[.6, .8], [1, .8]], 'dir': 'entry'}]
        camera = Camera.from_dict({'id': 'cam', 'lines': definitions})
        self.assertEqual(camera.to_dict()['lines'], definitions)

    def test_five_click_selector_pairs_lines_and_shares_final_reference(self):
        from computer_vision_v2.select_line_points import selection_config
        points = [(0, 10), (10, 10), (20, 20), (30, 20), (5, 0)]
        config = selection_config(points, 100, 100, 'independent', 'entry_exit')
        self.assertEqual(config['lines'][0]['line'], [[0, .1], [.1, .1]])
        self.assertEqual(config['lines'][1]['line'], [[.2, .2], [.3, .2]])
        self.assertTrue(all(d['inside_point'] == [.05, 0] for d in config['lines']))

    def test_outside_reference_reverses_entry_exit_for_both_lines(self):
        for x, y in ((5, 10), (25, 20)):
            for reference_side, expected in (('inside', 'exit'), ('outside', 'entry')):
                detector = LineDetector('cam', direction='entry_exit',
                    reference_side=reference_side, inside_point=(5, 0), lines=[
                        {'line': [(0, 10), (10, 10)]},
                        {'line': [(20, 20), (30, 20)]}])
                detector.update(self.frame(x, y-2))
                events = detector.update(self.frame(x, y+2))
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]['direction'], expected)

    def test_no_crop_reaches_database_before_shutdown(self):
        crop_q, cross_q, ocr_q, db_q = [queue.Queue() for _ in range(4)]
        event = dict(camera_id='cam', track_id=1, class_id=2,
                     confidence=.9, direction='entry', ts=1)
        cross_q.put(event)
        crop_q.put(SimpleNamespace(camera_id='cam'))
        crop_q.put(None)
        selector = Mock()
        selector.get.return_value = None
        # Verify dispatch on the first frame, while running, before shutdown.
        selector._cleanup.side_effect = lambda now: self.assertEqual(ocr_q.qsize(), 1)
        crop_worker(crop_q, cross_q, ocr_q, selector, lambda: True, wait_after_cross=0)
        ocr_q.put(None)
        reader = Mock()
        ocr_worker(ocr_q, db_q, reader, lambda: True)
        reader.read.assert_not_called()
        item = db_q.get_nowait()
        self.assertIsNone(item['plate_text'])
        self.assertIsNone(item['image_path'])
        cursor = Mock()
        cursor.fetchone.return_value = (42,)
        self.assertEqual(_save_event(cursor, item), 42)
        self.assertEqual(cursor.execute.call_count, 1)
