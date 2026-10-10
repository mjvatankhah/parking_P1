import queue
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from computer_vision_v2.ocr_worker import ocr_worker_v2 as worker
from computer_vision_v2.database.database_worker import _save_event


class PersonCropTests(unittest.TestCase):
    def dispatch(self, crop):
        input_queue, db_queue = queue.Queue(), queue.Queue()
        input_queue.put({
            'event': dict(camera_id='cam', track_id=7, class_id=0,
                          direction='entry', confidence=.9),
            'crop': None if crop is None else {'crop': crop},
        })
        input_queue.put(None)
        reader = Mock()
        worker.ocr_worker(input_queue, db_queue, reader, lambda: True)
        reader.read.assert_not_called()
        self.assertEqual(input_queue.unfinished_tasks, 0)
        return db_queue.get_nowait()

    def test_person_image_saved_and_path_persisted_without_vehicle_session(self):
        crop = np.full((24, 12, 3), 100, dtype=np.uint8)
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(worker, 'PERSON_IMAGE_DIR', Path(directory) / 'persons'):
                item = self.dispatch(crop)
                other = self.dispatch(crop)
            self.assertNotEqual(item['image_path'], other['image_path'])
            np.testing.assert_array_equal(cv2.imread(item['image_path']), crop)
            self.assertIsNone(item['plate_text'])
            cursor = Mock()
            cursor.fetchone.return_value = (42,)
            self.assertEqual(_save_event(cursor, item), 42)
            self.assertEqual(cursor.execute.call_count, 1)
            self.assertEqual(cursor.execute.call_args.args[1][:-1],
                             ('cam', None, 'entry', 0, .9, item['image_path']))

    def test_missing_crop_preserves_person_event(self):
        item = self.dispatch(None)
        self.assertIsNone(item['image_path'])
        self.assertEqual(item['class_id'], 0)

    def test_failed_image_write_preserves_event_without_invalid_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(worker, 'PERSON_IMAGE_DIR', Path(directory)):
                with patch.object(worker.cv2, 'imwrite', return_value=False):
                    with self.assertLogs(worker.logger, level='ERROR'):
                        item = self.dispatch(np.zeros((10, 10, 3), dtype=np.uint8))
        self.assertIsNone(item['image_path'])
        self.assertEqual(item['class_id'], 0)
