"""Diagnostic flow must use the same passage and OCR decisions as production."""
import unittest
from unittest.mock import Mock

import numpy as np

from computer_vision_v2.debug_plate import choose_camera, inspect_passage, process_frame
from computer_vision_v2.ocr_worker.plate_candidates import CompletedPassage
from computer_vision_v2.tracking.frame_info import TrackedFrame


class DebugPlateTests(unittest.TestCase):
    def test_completed_passage_uses_candidate_voting_once(self):
        reader = Mock()
        reader.recognize_candidates.return_value = {
            'plate_text': '12ب34567', 'recognition_status': 'read',
            'confidence': .9, 'readings': [{'text': '12ب34567'}], 'image': None,
        }
        event = {'frame_idx': 8, 'track_id': 4, 'camera_id': 'cam', 'direction': 'entry'}
        passage = CompletedPassage(event, ['sample-1', 'sample-2'])
        row, image = inspect_passage(passage, reader)
        reader.recognize_candidates.assert_called_once_with(passage.candidates)
        self.assertEqual((row['status'], row['candidate_count'], image), ('read', 2, None))

    def test_frame_runs_crossing_before_sampling_and_only_ocr_on_completion(self):
        calls = []
        tracked = TrackedFrame('cam', 1, .1, np.zeros((4, 4, 3), np.uint8), [])
        lines = Mock()
        lines.update.side_effect = lambda frame: calls.append('cross') or ['event']
        candidates = Mock()
        candidates.observe.side_effect = lambda frame, crossings: calls.append('sample') or []
        reader = Mock()
        self.assertEqual(process_frame(tracked, lines, candidates, reader), [])
        self.assertEqual(calls, ['cross', 'sample'])
        reader.recognize_candidates.assert_not_called()
        candidates.observe.assert_called_once_with(tracked, ['event'])

    def test_camera_selection_uses_configured_source(self):
        cameras = [{'id': 'a', 'source': 'a.mp4'}, {'id': 'b', 'source': 'b.mp4'}]
        self.assertEqual(choose_camera({'cameras': cameras}, 'b')['source'], 'b.mp4')
        with self.assertRaises(ValueError):
            choose_camera({'cameras': cameras}, 'missing')


if __name__ == '__main__':
    unittest.main()
