"""Local camera paths must work regardless of the UI launch directory."""

import os
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from computer_vision_v2.streaming.Source_Base import VideoSource


class VideoSourcePathTests(unittest.TestCase):
    def test_project_relative_video_opens_from_another_directory(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=root) as folder:
            path = Path(folder) / 'sample.avi'
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 25, (64, 48))
            self.assertTrue(writer.isOpened())
            writer.write(np.zeros((48, 64, 3), dtype=np.uint8))
            writer.release()
            previous = Path.cwd()
            with tempfile.TemporaryDirectory() as elsewhere:
                try:
                    os.chdir(elsewhere)
                    for source_path in (str(path.relative_to(root)), str(path)):
                        with self.subTest(path=source_path):
                            source = VideoSource(source_path)
                            try:
                                source.connect()
                                ok, frame = source.get_frame()
                                self.assertTrue(ok)
                                self.assertEqual(frame.shape, (48, 64, 3))
                            finally:
                                source.disconnect()
                finally:
                    os.chdir(previous)
