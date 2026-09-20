
import queue
import time


def line_worker(line_queue, cross_queue, line_manager, is_running):
    """تشخیص عبور خودرو از خط، مستقل از ترد اصلی."""
    processed = 0
    last_report = time.monotonic()
    while True:
        try:
            tracked_frame = line_queue.get(timeout=0.1)
            processed += 1
            
        except queue.Empty:
            continue
        if tracked_frame is None:
            break
        try:
            events = line_manager.update(tracked_frame)
            
            #-------------------------------------------------
            print(
            f"[LINE] camera={tracked_frame.camera_id} "
            f"events={len(events)}")

            for event in events:
                print("========== CROSSING EVENT ==========")
                print(event)
                print("====================================")
            #-------------------------------------------------
                try:
                    
                    cross_queue.put(event, block=not is_running())
                except queue.Full:
                    print("[line_worker] cross_queue full, event dropped")
        except Exception as exc:  # noqa: BLE001
            print(f"[line_worker] error: {exc}")
        finally:
            line_queue.task_done()


def crop_worker(crop_queue, cross_queue, ocr_queue, selector, is_running, wait_after_cross=5.0):
    """انتخاب بهترین کراپ‌ها و ارسال به OCR، مستقل از ترد اصلی."""
    pending = {}
    dispatched = set()

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

                pending.pop(key, None)
                continue

            pending.pop(key, None)
            dispatched.add(key)

            try:
                ocr_queue.put(
                    {
                        "event": event,
                        "crop": best_crop,
                    },
                    block=final or not is_running(),
                )
            except queue.Full:
                print(
                    f"[crop_worker] ocr_queue full, "
                    f"dropped {camera_id}/{track_id}"
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
            break
        try:
            selector.update(tracked_frame.camera_id,tracked_frame)
            

        except Exception as exc:  # noqa: BLE001
            print(f"[crop_worker] error: {exc}")
        finally:
            crop_queue.task_done()
        drain_cross_events()
        flush_pending()
