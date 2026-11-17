"""Write passage artifacts before handing their paths to the database worker."""
import time
import logging
from pathlib import Path
from uuid import uuid4
import cv2
from computer_vision_v2.workers.queueing import offer_event

logger = logging.getLogger(__name__)
PERSON_IMAGE_DIR = Path(__file__).resolve().parents[2] / 'captured_persons'
PLATE_IMAGE_DIR = Path(__file__).resolve().parents[2] / 'captured_plates'


def storage_worker(storage_queue, db_queue, running_flag):
    while True:
        item = storage_queue.get()
        try:
            if item is None:
                return
            event, result = item['event'], dict(item['result'])
            started = time.monotonic()
            image = result.pop('image')
            result['image_path'] = None
            if image is not None and image.size:
                directory = PERSON_IMAGE_DIR if event['class_id']==0 else PLATE_IMAGE_DIR
                try:
                    directory.mkdir(parents=True, exist_ok=True)
                    path = directory / f'{uuid4().hex}.jpg'
                    if not cv2.imwrite(str(path), image):
                        raise OSError('Image write failed')
                    result['image_path'] = str(path)
                except Exception:
                    logger.exception('Could not save crossing image')
            trace = item.get('trace')
            if trace is not None:
                result['diagnostics_path'] = trace.save(event, result, item['candidates'])
                trace.discard()
            logger.info('storage completed', extra={'event': 'storage_completed',
                'camera_id': event.get('camera_id'), 'track_id': event.get('track_id'),
                'passage_id': event.get('passage_id'), 'status': result['recognition_status'],
                'duration_ms': round((time.monotonic()-started)*1000, 2),
                'candidates': len(item.get('candidates', [])), 'readings': len(result.get('readings', []))})
            offer_event(db_queue, {**event, **result}, 'database', stopping=not running_flag())
        finally:
            item = None
            storage_queue.task_done()
