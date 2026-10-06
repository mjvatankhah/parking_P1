
import queue
import logging
import time

from computer_vision_v2.workers.queueing import offer_event

logger = logging.getLogger(__name__)

def line_worker(line_queue, cross_queue, line_manager, is_running):
    """تشخیص عبور خودرو از خط، مستقل از ترد اصلی."""
    while True:
        try:
            tracked_frame = line_queue.get(timeout=0.1)
            
        except queue.Empty:
            continue
        if tracked_frame is None:
            line_queue.task_done()
            break
        try:
            events = line_manager.update(tracked_frame)
            for event in events:
                logger.info(
                    "Crossing camera=%s track=%s direction=%s",
                    event["camera_id"], event["track_id"], event["direction"],
                )
                offer_event(cross_queue, event, "cross", stopping=not is_running())
        except Exception:  # noqa: BLE001
            logger.exception("Line processing failed")
        finally:
            line_queue.task_done()


def crop_worker(crop_queue, cross_queue, ocr_queue, selector, is_running, wait_after_cross=5.0):
    """انتخاب بهترین کراپ‌ها و ارسال به OCR، مستقل از ترد اصلی."""
    pending = {}
    dispatched = {}

    def drain_cross_events():
        while True:
            try:
                event = cross_queue.get_nowait()
            except queue.Empty:
                return
            if event is None:
                return
            key = (event["camera_id"], event["track_id"])
            if key not in dispatched:
                pending.setdefault(key, {"event":event, "crossed_ts":event.get('ts') or time.monotonic()})
            cross_queue.task_done()

    def flush_pending(final=False):
        now = time.monotonic()
        # Match the line detector's finite track lifetime; this state must not
        # grow for every vehicle in a long-running RTSP session.
        for key, dispatched_at in list(dispatched.items()):
            if now - dispatched_at > 120:
                del dispatched[key]
        for key, pending_data in list(pending.items()):
            camera_id, track_id = key
            event = pending_data['event']
            crossed_ts = pending_data['crossed_ts']

            best_crop = selector.get(camera_id, track_id)
            if best_crop is None and not final:
                if not is_running():
                    continue  # در پایان، رویداد بدون کراپ هم ثبت می‌شود.
                if (now - crossed_ts) <= wait_after_cross:
                    continue

                # Preserve the crossing even when no usable crop was found.

            pending.pop(key, None)
            dispatched[key] = now
            offer_event(
                ocr_queue, {"event": event, "crop": best_crop},
                "ocr", stopping=final or not is_running(),
            )
        selector._cleanup(now)

    while True:
       
        try:
            tracked_frame = crop_queue.get(timeout=0.1)
            
        except queue.Empty:
            drain_cross_events()
            flush_pending()
            continue
        if tracked_frame is None:
            # ورکر خط قبلاً تمام شده؛ رویداد تازه‌ای در راه نیست.
            drain_cross_events()
            flush_pending(final=True)
            crop_queue.task_done()
            break
        try:
            selector.update(tracked_frame.camera_id,tracked_frame)
            

        except Exception:  # noqa: BLE001
            logger.exception("Crop selection failed")
        finally:
            crop_queue.task_done()
        drain_cross_events()
        flush_pending()
