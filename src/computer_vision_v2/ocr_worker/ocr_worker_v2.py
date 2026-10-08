import logging
from pathlib import Path
from uuid import uuid4

import cv2

from computer_vision_v2.workers.queueing import offer_event

CAR_CLASS_ID = 2
PERSON_CLASS_ID = 0
PERSON_IMAGE_DIR = Path(__file__).resolve().parents[2] / "captured_persons"
logger = logging.getLogger(__name__)


def _save_person_crop(crop):
    PERSON_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    path = PERSON_IMAGE_DIR / f"person_{uuid4().hex}.jpg"
    if not cv2.imwrite(str(path), crop):
        raise OSError(f"Could not write person crop to {path}")
    return str(path)

def ocr_worker(ocr_queue, db_queue, plate_reader, running_flag):
    while True:
        item = ocr_queue.get()
        if item is None:  # سیگنال خاموش‌شدن
            ocr_queue.task_done()
            break

        event = item["event"]
        best_crop = item['crop']
        camera_id = event['camera_id']
        track_id = event['track_id']
        class_id = event['class_id']

        plate_txt = None
        confidence = float(event.get('confidence', 0.0))
        image_path = None

        if class_id == PERSON_CLASS_ID and best_crop is not None:
            try:
                image_path = _save_person_crop(best_crop['crop'])
            except Exception:
                logger.exception("Could not save person crop %s/%s", camera_id, track_id)

        if class_id == CAR_CLASS_ID and best_crop is not None:
            
            try:
                text, conf, path = plate_reader.read(best_crop['crop'])
            except Exception as e:
                print(f"[ocr_worker] OCR failed {camera_id}/{track_id}: {e}")

            else:
                if path is not None:
                    image_path = path
                if text:
                    plate_txt = text
                    confidence = conf



        offer_event(db_queue,
            {
                "camera_id": camera_id,
                "track_id": track_id,
                "class_id": class_id,
                "direction":event['direction'],
                "plate_text": plate_txt,
                "confidence": confidence,
                "image_path": image_path,
            }, "database", stopping=not running_flag(),
        )
        ocr_queue.task_done()
