import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import cv2
import numpy as np

from computer_vision_v2.inference.plate_ocr import PlateReader
from computer_vision_v2.inference.plate_geometry import _rectify_plate, _prepare_deskew, prepare_plate

MODULE = 'computer_vision_v2.inference.plate_ocr'


def detector(hit=False, name='images'):
    output = np.zeros((1, 5, 8), np.float32)
    if hit:
        output[0, :, 0] = [320, 320, 320, 80, .9]
    model = Mock()
    model.get_inputs.return_value = [SimpleNamespace(name=name, shape=[1, 3, 640, 640])]
    model.run.return_value = [output]
    return model


class FallbackTests(unittest.TestCase):
    def reader(self, primary, fallback):
        session = patch(MODULE+'._session', side_effect=[primary, fallback]).start()
        self.addCleanup(patch.stopall)
        with patch(MODULE+'.HezarOCR'), patch.object(PlateReader, '_load_labels', return_value=[]):
            reader = PlateReader()
        return reader, session

    def test_primary_hit_does_not_load_or_run_fallback(self):
        reader, session = self.reader(detector(True), detector(True))
        result = reader.detect_plate(np.zeros((100, 200, 3), np.uint8))
        self.assertEqual(result[0].shape, (25, 100, 3))
        self.assertEqual(session.call_count, 1)

    def test_miss_loads_once_and_uses_fallback_input_name(self):
        fallback = detector(True, 'fallback_input')
        reader, session = self.reader(detector(), fallback)
        for _ in range(2):
            self.assertIsNotNone(reader.detect_plate(np.zeros((100, 200, 3), np.uint8)))
        self.assertEqual(session.call_count, 2)
        self.assertIn('fallback_input', fallback.run.call_args.args[1])

    def test_both_miss(self):
        reader, _ = self.reader(detector(), detector())
        self.assertIsNone(reader.detect_plate(np.zeros((100, 200, 3), np.uint8)))

    def test_optional_model_missing_does_not_retry_or_stop_primary(self):
        reader, session = self.reader(detector(), RuntimeError('missing'))
        with self.assertLogs(MODULE, level='WARNING'):
            self.assertIsNone(reader.detect_plate(np.zeros((100, 200, 3), np.uint8)))
        self.assertIsNone(reader.detect_plate(np.zeros((100, 200, 3), np.uint8)))
        self.assertEqual(session.call_count, 2)

    def test_load_failure_promotes_fallback_without_running_twice(self):
        fallback = detector()
        with patch(MODULE+'._session', side_effect=[RuntimeError('primary'), fallback]) as session:
            with patch(MODULE+'.HezarOCR'), patch.object(PlateReader, '_load_labels', return_value=[]):
                reader = PlateReader()
            self.assertIsNone(reader.detect_plate(np.zeros((100, 200, 3), np.uint8)))
        self.assertEqual(session.call_count, 2)
        self.assertEqual(fallback.run.call_count, 1)


class CornerTests(unittest.TestCase):
    @staticmethod
    def plate(text=True):
        plate = np.full((40, 160, 3), 220, np.uint8)
        if text:
            cv2.putText(plate, '12345678', (7, 29), cv2.FONT_HERSHEY_SIMPLEX, .65, (20, 20, 20), 2)
        source = np.float32([[0, 0], [159, 0], [159, 39], [0, 39]])
        target = np.float32([[25, 20], [185, 30], [178, 70], [30, 60]])
        return cv2.warpPerspective(plate, cv2.getPerspectiveTransform(source, target), (210, 90), borderValue=(25, 25, 25))

    def test_visible_plate_rectified_and_used(self):
        roi = self.plate()
        result = _rectify_plate(roi)
        self.assertIsNotNone(result)
        self.assertGreater(result.shape[1]/result.shape[0], 3)
        self.assertIsNotNone(prepare_plate(roi))
        old = _prepare_deskew(roi)
        self.assertTrue(old is None or not np.array_equal(prepare_plate(roi).image, old.image))

    def test_blank_rectangle_is_not_a_plate(self):
        self.assertIsNone(_rectify_plate(self.plate(False)))

    def test_clipped_border_is_not_invented(self):
        self.assertIsNone(_rectify_plate(self.plate()[25:65]))

    def test_no_evidence_preserves_old_preparation(self):
        roi = np.full((40, 120, 3), 100, np.uint8)
        self.assertIsNone(_rectify_plate(roi))
        self.assertIsNone(prepare_plate(roi))


if __name__ == '__main__':
    unittest.main()
