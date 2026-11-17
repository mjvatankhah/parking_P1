"""Recognize passages and hand off disk I/O to the storage worker."""
import time
import logging
from computer_vision_v2.workers.queueing import offer_event

logger = logging.getLogger(__name__)


def ocr_worker(ocr_queue, storage_queue, plate_reader, running_flag):
    while True:
        item = ocr_queue.get()
        try:
            if item is None:
                return
            event = item['event']
            started = time.monotonic()
            result = {'plate_text':None, 'confidence':float(event.get('confidence',0.)) if event['class_id']==0 else 0., 'recognition_status':'unread',
                      'readings':[], 'image':item.get('person')}
            if event['class_id'] == 2:
                try:
                    result = plate_reader.recognize_candidates(item['candidates'])
                except Exception as exc:
                    result['recognition_error'] = type(exc).__name__
                    logger.exception('OCR failed for %s/%s', event['camera_id'], event['track_id'])
            trace = item.get('trace')
            if trace is not None and result['recognition_status'] == 'read':
                trace.discard()
                trace = None
            logger.info('ocr completed', extra={'event': 'ocr_completed',
                'camera_id': event.get('camera_id'), 'track_id': event.get('track_id'),
                'passage_id': event.get('passage_id'), 'status': result['recognition_status'],
                'duration_ms': round((time.monotonic()-started)*1000, 2),
                'candidates': len(item.get('candidates', [])), 'readings': len(result.get('readings', []))})
            offer_event(storage_queue, {'event': event, 'result': result,
                        'trace': trace, 'candidates': item['candidates'] if trace is not None else []},
                        'storage', stopping=not running_flag())
        finally:
            item = result = trace = None
            ocr_queue.task_done()
