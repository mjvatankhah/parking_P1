"""Keep crossing evidence until its vehicle leaves the camera ROI."""
import logging
from computer_vision_v2.workers.queueing import offer_event

logger = logging.getLogger(__name__)


def _offer_passages(passages, ocr_queue, is_running):
    for passage in passages:
        event = passage.event
        logger.info('Vehicle evidence complete camera=%s track=%s candidates=%s',
                    event['camera_id'], event['track_id'], len(passage.candidates))
        offer_event(ocr_queue, {'event':event, 'candidates':passage.candidates, 'person':None},
                    'ocr', stopping=not is_running())


def plate_detection_worker(candidates, ocr_queue, is_running):
    while is_running():
        _offer_passages(candidates.process_pending(timeout=.05), ocr_queue, is_running)


def observation_worker(frame_queue, ocr_queue, lines, candidates, is_running):
    while True:
        frame = frame_queue.get()
        try:
            if frame is None:
                return
            crossings = lines.update(frame)
            completed = candidates.observe(frame, crossings)
            for event in crossings:
                if event['class_id'] != 0:
                    continue
                x1,y1,x2,y2 = map(int, event['bbox'])
                person = frame.image[max(0,y1):max(0,y2), max(0,x1):max(0,x2)].copy()
                offer_event(ocr_queue, {'event':event, 'candidates':[], 'person':person},
                            'ocr', stopping=not is_running())
            _offer_passages(completed, ocr_queue, is_running)
        except Exception:
            logger.exception('Observation failed')
        finally:
            frame_queue.task_done()
