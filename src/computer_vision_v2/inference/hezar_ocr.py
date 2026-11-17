"""Local Hezar OCR boundary: BGR crops in, canonical text/confidence out.

Hezar owns resizing, mirroring, normalization and text decoding. Confidence
is the mean probability of emitted CTC characters, excluding blanks and
collapsed repeats, rather than Hezar's mean over all time steps.
"""
from pathlib import Path
import logging

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

    def recognize(self, images: list[np.ndarray], *, input_observer=None) -> list[tuple[str, float]]:
        if not images:
            return []
        # OpenCV uses BGR; Hezar's image processor expects RGB input.
        rgb_images = [cv2.cvtColor(image, cv2.COLOR_BGR2RGB) for image in images]
        with torch.inference_mode():
            inputs = self._model.preprocess(rgb_images)
            if input_observer is not None:
                try:
                    config = self._model.preprocessor.image_processor.config
                    values = inputs['pixel_values'].detach().cpu().numpy().copy()
                    # Undo only numeric normalization for a viewable PNG. The
                    # actual resized/mirrored pixels come from this inference.
                    if config.mean is not None and config.std is not None:
                        values = values * np.asarray(config.std)[None, :, None, None] + np.asarray(config.mean)[None, :, None, None]
                    if config.rescale is not None:
                        values = values / config.rescale
                    values = np.rint(values).clip(0, 255).astype(np.uint8)
                    previews = [v[0] if v.shape[0] == 1 else cv2.cvtColor(v.transpose(1, 2, 0), cv2.COLOR_RGB2BGR)
                                for v in values]
                    input_observer(previews)
                except Exception:
                    logging.getLogger(__name__).exception('Could not record OCR model inputs; recognition continues')
            logits = self._model(**inputs)['logits']
            blank_id = self._model.config.blank_id
            predictions = self._model.post_process({
                'generated_ids': self._decode(logits, blank=blank_id),
                'scores': character_confidences(logits, blank_id),
            }, return_scores=True)
        if len(predictions) != len(images):
            raise ValueError('Hezar OCR returned a different number of readings than input crops')
        return [(canonical_plate_text(item.text), float(item.score)) for item in predictions]
