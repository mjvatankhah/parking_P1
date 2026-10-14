"""Keep crossing evidence until its vehicle leaves the camera ROI."""
import logging
from computer_vision_v2.workers.queueing import offer_event

logger = logging.getLogger(__name__)


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
            for passage in completed:
                event, crops = passage.event, passage.candidates
                logger.info('Vehicle left ROI camera=%s track=%s direction=%s candidates=%s',
                            event['camera_id'], event['track_id'], event['direction'], len(crops))
                offer_event(ocr_queue, {'event':event, 'candidates':crops, 'person':None},
                            'ocr', stopping=not is_running())
        except Exception:
            logger.exception('Observation failed')
        finally:
            frame_queue.task_done()
