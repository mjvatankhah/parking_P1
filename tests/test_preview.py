import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np

from computer_vision_v2.preview import (
    MAX_FRAME_AGE, PreviewPublisher, annotate_frame, preview_path, read_preview,
)
from computer_vision_v2.tracking.frame_info import Detection, TrackedFrame


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.frame = TrackedFrame('camera', 1, 0, np.zeros((120, 220, 3), dtype=np.uint8), [
            Detection(1, (10, 25, 70, 100), 0, .9),
            Detection(2, (100, 25, 200, 100), 2, .8),
        ])

    def test_annotation_preserves_original_and_draws_both_classes(self):
        output = annotate_frame(self.frame)
        self.assertFalse(self.frame.image.any())
        self.assertTrue(output[25, 10].any())
        self.assertTrue(output[25, 100].any())
        self.assertFalse(np.array_equal(output[25, 10], output[25, 100]))

    def test_empty_detections_still_show_image(self):
        self.frame.detections = []
        np.testing.assert_array_equal(annotate_frame(self.frame), self.frame.image)

    def test_round_trip_versions_staleness_and_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'preview.jpg'
            self.assertEqual(read_preview(path), (None, None))
            PreviewPublisher._write(path, self.frame, time.time())
            image, version = read_preview(path)
            self.assertEqual(image.shape, self.frame.image.shape)
            self.assertTrue(image.any())
            self.assertEqual(read_preview(path, version), (None, version))
            old = time.time() - MAX_FRAME_AGE - 1
            os.utime(path, (old, old))
            self.assertEqual(read_preview(path), (None, None))

    def test_source_and_camera_isolation(self):
        self.assertNotEqual(preview_path('one', 'a'), preview_path('one', 'b'))
        self.assertNotEqual(preview_path('one', 'a'), preview_path('two', 'a'))

    def test_worker_latest_frame_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'preview.jpg'
            with patch('computer_vision_v2.preview.preview_path', return_value=path):
                publisher = PreviewPublisher([{'id': 'camera', 'source': 'unused'}])
            for _ in range(100):
                publisher.publish(self.frame)
            self.assertEqual(len(publisher._pending), 1)
            publisher.start()
            try:
                deadline = time.monotonic() + 3
                while not path.exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertIsNotNone(read_preview(path)[0])
            finally:
                publisher.stop()
            self.assertFalse(path.exists())
            self.assertFalse(publisher._thread.is_alive())


if __name__ == '__main__':
    unittest.main()
