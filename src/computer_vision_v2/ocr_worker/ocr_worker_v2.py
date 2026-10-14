"""Recognize crossing evidence and persist only the final preview image."""
import logging
from pathlib import Path
from uuid import uuid4
import cv2
from computer_vision_v2.workers.queueing import offer_event

logger = logging.getLogger(__name__)
PERSON_IMAGE_DIR = Path(__file__).resolve().parents[2] / 'captured_persons'
PLATE_IMAGE_DIR = Path(__file__).resolve().parents[2] / 'captured_plates'


def ocr_worker(ocr_queue, db_queue, plate_reader, running_flag):
    while True:
        item = ocr_queue.get()
        try:
            if item is None:
                return
            event = item['event']
            result = {'plate_text':None, 'confidence':float(event.get('confidence',0.)) if event['class_id']==0 else 0., 'recognition_status':'unread',
                      'readings':[], 'image':item.get('person')}
            if event['class_id'] == 2:
                try:
                    result = plate_reader.recognize_candidates(item['candidates'])
                except Exception:
                    logger.exception('OCR failed for %s/%s', event['camera_id'], event['track_id'])
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
            offer_event(db_queue, {**event, **result}, 'database', stopping=not running_flag())
        finally:
            ocr_queue.task_done()
