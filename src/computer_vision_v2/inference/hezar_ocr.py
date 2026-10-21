"""Local Hezar OCR boundary: BGR crops in, canonical text/confidence out.

Hezar owns resizing, mirroring, normalization and text decoding. Confidence
is the mean probability of emitted CTC characters, excluding blanks and
collapsed repeats, rather than Hezar's mean over all time steps.
"""
from pathlib import Path

import cv2
import numpy as np
import torch


_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def canonical_plate_text(text: str) -> str:
    text = text.translate(_DIGITS).replace('ي', 'ی').replace('ك', 'ک').strip()
    if text[2:-5] in ('ا', 'آ'):
        text = text[:2] + 'الف' + text[-5:]
    return text


def character_confidences(logits: torch.Tensor, blank_id: int) -> torch.Tensor:
    """One score per image for Hezar's [time, batch, classes] logits."""
    probabilities, ids = logits.softmax(dim=2).max(dim=2)
    emitted = ids != blank_id
    emitted[1:] &= ids[1:] != ids[:-1]
    counts = emitted.sum(dim=0)
    return (probabilities * emitted).sum(dim=0) / counts.clamp_min(1)


class HezarOCR:
    def __init__(self, model_directory: Path):
        directory = Path(model_directory).resolve()
        for filename in ('model.pt', 'model_config.yaml',
                         'preprocessor/image_processor_config.yaml'):
            if not (directory / filename).is_file():
                raise FileNotFoundError(f'Missing local Hezar OCR file: {directory / filename}')

        from hezar.models import Model
        from hezar.models.image2text.crnn.crnn_decode_utils import ctc_decode

        self._decode = ctc_decode
        self._model = Model.load(str(directory), load_locally=True, device='cpu')
        self._model.eval()

    def recognize(self, images: list[np.ndarray]) -> list[tuple[str, float]]:
        if not images:
            return []
        # OpenCV uses BGR; Hezar's image processor expects RGB input.
        rgb_images = [cv2.cvtColor(image, cv2.COLOR_BGR2RGB) for image in images]
        with torch.inference_mode():
            inputs = self._model.preprocess(rgb_images)
            logits = self._model(**inputs)['logits']
            blank_id = self._model.config.blank_id
            predictions = self._model.post_process({
                'generated_ids': self._decode(logits, blank=blank_id),
                'scores': character_confidences(logits, blank_id),
            }, return_scores=True)
        if len(predictions) != len(images):
            raise ValueError('Hezar OCR returned a different number of readings than input crops')
        return [(canonical_plate_text(item.text), float(item.score)) for item in predictions]
