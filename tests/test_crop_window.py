"""The OCR handoff must include candidates from the full crossing window."""
import queue
import unittest
from unittest.mock import patch

import numpy as np

from computer_vision_v2.best_crop_selector import BestCropSelector
from computer_vision_v2.tracking.frame_info import Detection, TrackedFrame
from computer_vision_v2.workers.workers import crop_worker


def frame(index, ts, confidence=0.1, camera='cam', track=7):
    return TrackedFrame(camera, index, ts, np.full((30, 30, 3), 100, np.uint8),
                        [Detection(track, (2, 2, 20, 20), 2, confidence)])


class CropWindowTests(unittest.TestCase):
    def run_window(self, steps):
        clock = [0.0]
        crossing = queue.Queue()
        output = queue.Queue()
        selector = BestCropSelector()
        deadlines = {}

        class Input:
            def get(self, timeout):
                ts, image, event = steps.pop(0)
                clock[0] = ts
                if event is not None:
                    deadlines.setdefault((event['camera_id'], event['track_id']), event['ts'] + 10)
                    crossing.put(event)
                for item in output.queue:
                    key = (item['event']['camera_id'], item['event']['track_id'])
                    if ts < deadlines[key]:
                        raise AssertionError('OCR was dispatched before the ten-second deadline')
                return image

            def task_done(self):
                pass

        with patch('time.monotonic', side_effect=lambda: clock[0]):
            crop_worker(Input(), crossing, output, selector, lambda: True)
        return list(output.queue), selector

    def test_best_pre_and_post_cross_crop_waits_ten_seconds(self):
        event = {'camera_id': 'cam', 'track_id': 7, 'ts': 2.0, 'direction': 'entry'}
        steps = [(0, frame(1, 0, .4), None),
                 (2, frame(2, 2, .3), event),
                 (11, frame(3, 11, .8), None),
                 (12, frame(4, 12, 1.0), None),
                 (13, None, None)]
        output, selector = self.run_window(steps)
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]['crop']['frame_idx'], 3)
        self.assertEqual(output[0]['event'], event)
        self.assertFalse(selector.best_frames)
        self.assertFalse(selector._retained)

    def test_missing_vehicle_keeps_pre_cross_best_until_deadline(self):
        event = {'camera_id': 'cam', 'track_id': 7, 'ts': 1.0}
        empty = lambda ts: TrackedFrame('cam', 2, ts, np.zeros((30, 30, 3), np.uint8), [])
        output, _ = self.run_window([(0, frame(1, 0, .9), None),
                                     (1, empty(1), event), (7, empty(7), None),
                                     (11, empty(11), None), (12, None, None)])
        self.assertEqual(output[0]['crop']['frame_idx'], 1)

    def test_seen_vehicle_without_improvement_keeps_initial_best(self):
        selector = BestCropSelector()
        with patch('time.monotonic', return_value=0):
            selector.update('cam', frame(1, 0, .9))
        with patch('time.monotonic', return_value=7):
            selector.update('cam', frame(2, 7, .1))
        self.assertEqual(selector.get('cam', 7)['frame_idx'], 1)

    def test_no_crop_still_sends_event_at_deadline_and_deduplicates(self):
        event = {'camera_id': 'cam', 'track_id': 7, 'ts': 0.0}
        empty = TrackedFrame('cam', 1, 0, np.zeros((30, 30, 3), np.uint8), [])
        output, _ = self.run_window([(0, empty, event), (9, empty, event),
                                     (10, empty, None), (11, empty, event), (12, None, None)])
        self.assertEqual(output, [{'event': event, 'crop': None}])

    def test_same_track_id_on_other_camera_does_not_replace_candidate(self):
        event = {'camera_id': 'cam', 'track_id': 7, 'ts': 1.0}
        output, _ = self.run_window([(0, frame(1, 0, .4), None),
                                     (1, frame(2, 1, .3), event),
                                     (5, frame(3, 5, 1.0, camera='other'), None),
                                     (11, frame(4, 11, .2), None), (12, None, None)])
        self.assertEqual(output[0]['crop']['frame_idx'], 1)

    def test_shutdown_flushes_best_without_waiting(self):
        event = {'camera_id': 'cam', 'track_id': 7, 'ts': 1.0}
        output, _ = self.run_window([(0, frame(1, 0), None),
                                     (1, frame(2, 1, .8), event), (2, None, None)])
        self.assertEqual(output[0]['crop']['frame_idx'], 2)


if __name__ == '__main__':
    unittest.main()
