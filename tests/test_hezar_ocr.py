"""The Hezar boundary preserves crop order, color and voting semantics."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import numpy as np
import torch

from computer_vision_v2.inference.hezar_ocr import (
    HezarOCR, canonical_plate_text, character_confidences,
)


class HezarOCRTests(unittest.TestCase):
    def test_canonical_digits_and_alef_match_existing_plate_format(self):
        self.assertEqual(canonical_plate_text('۵۸م۸۷۲۴۵'), '58م87245')
        self.assertEqual(canonical_plate_text('١٢ا٣٤٥٦٧'), '12الف34567')
        self.assertEqual(canonical_plate_text('۱۲ي۳۴۵۶۷'), '12ی34567')
        self.assertEqual(canonical_plate_text('۵۸م۸۷۲۴'), '58م8724')

    def test_blanks_and_collapsed_repeats_do_not_inflate_confidence(self):
        # Image 1 emits A, A: a blank separates the two occurrences.
        # Image 2 is all blank and must have zero confidence.
        probabilities = torch.tensor([
            [[.01, .8, .19], [.99, .005, .005]],
            [[.001, .998, .001], [.99, .005, .005]],
            [[.99, .005, .005], [.99, .005, .005]],
            [[.2, .6, .2], [.99, .005, .005]],
        ])
        scores = character_confidences(probabilities.log(), blank_id=0)
        torch.testing.assert_close(scores, torch.tensor([.7, 0.]))

    def test_missing_local_files_fail_before_loading_or_downloading(self):
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(FileNotFoundError, 'model.pt'):
                HezarOCR(Path(directory))

    def test_raw_bgr_crops_reach_official_preprocessor_once_in_order(self):
        reader = HezarOCR.__new__(HezarOCR)
        reader._model = Mock()
        reader._model.config.blank_id = 0
        logits = torch.tensor([[[0., 2.], [2., 0.]]])
        reader._model.return_value = {'logits': logits}
        reader._model.preprocess.return_value = {'pixel_values': torch.zeros(2, 1, 32, 384)}
        reader._model.post_process.return_value = [
            SimpleNamespace(text='۵۸م۸۷۲۴۵', score=.9),
            SimpleNamespace(text='', score=0.),
        ]
        reader._decode = Mock(return_value=torch.tensor([[1], [0]]))
        crops = [np.full((2, 3, 3), [10, 20, 30], dtype=np.uint8),
                 np.full((4, 5, 3), [40, 50, 60], dtype=np.uint8)]
        result = reader.recognize(crops)
        converted = reader._model.preprocess.call_args.args[0]
        np.testing.assert_array_equal(converted[0], crops[0][:, :, ::-1])
        np.testing.assert_array_equal(converted[1], crops[1][:, :, ::-1])
        self.assertEqual(result, [('58م87245', .9), ('', 0.)])
        self.assertEqual(reader._model.preprocess.call_count, 1)
        self.assertEqual(reader.recognize([]), [])
        self.assertEqual(reader._model.preprocess.call_count, 1)

    def test_mismatched_output_count_is_not_silently_used_for_votes(self):
        reader = HezarOCR.__new__(HezarOCR)
        reader._model = Mock()
        reader._model.config.blank_id = 0
        reader._model.preprocess.return_value = {'pixel_values': torch.zeros(1, 1, 32, 384)}
        reader._model.return_value = {'logits': torch.zeros(1, 1, 2)}
        reader._model.post_process.return_value = []
        reader._decode = Mock()
        with self.assertRaisesRegex(ValueError, 'number of readings'):
            reader.recognize([np.zeros((32, 128, 3), dtype=np.uint8)])


if __name__ == '__main__':
    unittest.main()
