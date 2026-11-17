"""Slow artifact writes must not execute on the OCR thread."""
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from computer_vision_v2.ocr_worker.ocr_worker_v2 import ocr_worker
from computer_vision_v2.storage.storage_worker import storage_worker


class StorageWorkerTests(unittest.TestCase):
    def test_ocr_finishes_next_passage_while_image_write_is_blocked(self):
        incoming, storage, database = queue.Queue(), queue.Queue(maxsize=16), queue.Queue()
        entered, release = threading.Event(), threading.Event()
        image = np.zeros((20, 60, 3), dtype=np.uint8)
        reader = Mock()
        reader.recognize_candidates.side_effect = lambda _: dict(
            plate_text='12ب34567', recognition_status='read', confidence=.95,
            readings=[], image=image)
        for track in (1, 2):
            incoming.put({'event': dict(camera_id='cam', track_id=track, class_id=2),
                          'candidates': []})
        incoming.put(None)

        def slow_write(*_):
            entered.set()
            if not release.wait(5):
                raise TimeoutError('Test storage was not released')
            return True

        with tempfile.TemporaryDirectory() as directory, \
             patch('computer_vision_v2.storage.storage_worker.PLATE_IMAGE_DIR', Path(directory)), \
             patch('computer_vision_v2.storage.storage_worker.cv2.imwrite', side_effect=slow_write):
            writer = threading.Thread(target=storage_worker, args=(storage, database, lambda: True))
            recognizer = threading.Thread(target=ocr_worker, args=(incoming, storage, reader, lambda: True))
            writer.start()
            recognizer.start()
            try:
                self.assertTrue(entered.wait(2))
                recognizer.join(2)
                self.assertFalse(recognizer.is_alive(), 'OCR waited for the blocked disk write')
                self.assertEqual(reader.recognize_candidates.call_count, 2)
                self.assertTrue(database.empty(), 'Database received a path before storage completed')
            finally:
                release.set()
                recognizer.join(3)
                storage.put(None)
                writer.join(3)
            self.assertFalse(writer.is_alive())
            self.assertEqual(storage.unfinished_tasks, 0)
            self.assertEqual([database.get_nowait()['track_id'] for _ in range(2)], [1, 2])
