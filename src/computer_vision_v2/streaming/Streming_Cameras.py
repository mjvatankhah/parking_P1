import threading
import time
from collections import namedtuple

from .Source_Base import VideoSource, RTSPSource
from computer_vision_v2.tracking.tracker import CameraTracker

Frame = namedtuple('Frame', 'camera_id frame_idx ts image detections')


class StreamManager:
    def __init__(self, camera_id, source, source_type, model_path, frame_step=0):
        self.camera_id = camera_id
        self.source = source
        self.source_type = source_type
        if not isinstance(frame_step, int) or frame_step < 0:
            raise ValueError('frame_step must be a non-negative integer')
        # فقط برای فایل: صفر = آخرین فریم، ۲ = یکی‌درمیان، ۳ = دو تا در میان.
        self.frame_step = frame_step
        self.running = False
        self.thread = None
        self.track_thread = None
        self.my_source = None
        self.frame_idx = 0
        self.latest_raw_frame = None
        self.latest_tracked_frame = None
        self.tracker = CameraTracker(camera_id=camera_id, model_path=model_path)

        # قفل فقط برای خواندن و تعویض آخرین فریم است؛ مدل بیرون قفل اجرا می‌شود.
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.read_finished = threading.Event()
        self.model_ready = threading.Event()
        self.frame_processed = threading.Event()

    def _should_process(self, frame_idx):
        if self.source_type != 'video' or self.frame_step == 0:
            return True
        return (frame_idx - 1) % self.frame_step == 0

    def _creat_source(self):
        if self.source_type == 'video':
            return VideoSource(self.source)
        if self.source_type == 'rtsp':
            return RTSPSource(self.source)
        raise ValueError('unknown source type')

    def start(self):
        self.running = True
        self.stop_event.clear()
        self.read_finished.clear()
        self.model_ready.clear()
        self.frame_processed.clear()
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.track_thread = threading.Thread(target=self._track_loop, daemon=True)
        self.thread.start()
        self.track_thread.start()

    def _read_loop(self):
        try:
            # تا آماده‌شدن مدل حتی فایل را باز نمی‌کنیم؛ فریم اول از دست نمی‌رود.
            while not self.model_ready.wait(0.05):
                if self.stop_event.is_set():
                    return

            backoff = 1
            while not self.stop_event.is_set():
                try:
                    self.my_source = self._creat_source()
                    self.my_source.connect()
                    break
                except Exception as exc:
                    if self.my_source is not None:
                        self.my_source.disconnect()
                    print(f"{self.camera_id}: connection failed: {exc}")
                    if self.stop_event.wait(backoff):
                        return
                    backoff = min(backoff * 2, 30)

            if self.stop_event.is_set():
                return

            # فایل را با سرعت طبیعی پخش می‌کنیم، نه با حداکثر سرعت خواندن دیسک.
            interval = 0
            if self.source_type == 'video':
                interval = 1 / self.my_source.get_fps()
            next_frame_at = time.monotonic()
            failed_reads = 0

            while not self.stop_event.is_set():
                if interval and self.stop_event.wait(max(0, next_frame_at - time.monotonic())):
                    break
                read_started = time.monotonic()
                ok, image = self.my_source.get_frame()
                if not ok:
                    failed_reads += 1
                    if self.source_type == 'video':
                        print(f"[{self.camera_id}] Video ended: received {self.frame_idx} frames.")
                        break
                    if failed_reads > 30:
                        break
                    self.stop_event.wait(0.1)
                    continue

                failed_reads = 0
                self.frame_idx += 1
                frame = Frame(self.camera_id, self.frame_idx, time.monotonic(), image, [])
                wait_for_tracker = (
                    self.source_type == 'video'
                    and self.frame_step > 0
                    and self._should_process(frame.frame_idx)
                )
                if wait_for_tracker:
                    self.frame_processed.clear()
                with self.lock:
                    self.latest_raw_frame = frame
                # در حالت فاصلهٔ ثابت، فریم انتخابی را تا پایان Track جایگزین نمی‌کنیم.
                # این انتظار پخش فایل را کند می‌کند، اما فریم انتخابی از دست نمی‌رود.
                if wait_for_tracker:
                    while not self.frame_processed.wait(0.05):
                        if self.stop_event.is_set():
                            return
                # اگر خواندن کند بود، برای جبران چند فریم را پشت سر هم نمی‌خوانیم.
                next_frame_at = max(next_frame_at, read_started) + interval
        finally:
            if self.my_source is not None:
                self.my_source.disconnect()
                self.my_source = None
            self.read_finished.set()

    def _track_loop(self):
        print(f"[{self.camera_id}] Preparing model; video has not started yet...")
        try:
            self.tracker.warmup()
        except Exception as exc:
            print(f"[{self.camera_id}] Model preparation failed: {exc}")
            self.stop_event.set()
            return
        if self.stop_event.is_set():
            return
        print(f"[{self.camera_id}] Model ready; starting capture.")
        self.model_ready.set()

        last_processed_idx = -1
        processed_count = 0
        while not self.stop_event.is_set():
            # پایان دریافت را قبل از گرفتن فریم می‌خوانیم تا آخرین فریم جا نماند.
            finished = self.read_finished.is_set()
            frame = self.get_latest_raw_frame()
            if (frame is None or frame.frame_idx == last_processed_idx
                    or not self._should_process(frame.frame_idx)):
                if finished:
                    print(
                        f"[{self.camera_id}] Tracking finished: processed {processed_count} "
                        f"of {self.frame_idx} received frames."
                    )
                    break
                self.stop_event.wait(0.005)
                continue

            # دریافت تصویر در thread دیگر ادامه دارد؛ اینجا هیچ قفلی نگه نداشته‌ایم.
            try:
                tracked_frame = self.tracker.process(
                    frame_idx=frame.frame_idx, ts=frame.ts, image=frame.image,
                )
            except Exception as exc:
                print(f"[{self.camera_id}] Tracking failed: {exc}")
                self.stop_event.set()
                return
            last_processed_idx = frame.frame_idx
            processed_count += 1
            with self.lock:
                self.latest_tracked_frame = tracked_frame
            self.frame_processed.set()

    def get_latest_raw_frame(self):
        with self.lock:
            return self.latest_raw_frame

    def get_latest_frame(self):
        # قرارداد قبلی حفظ شده: این متد فقط نتیجهٔ Track را برمی‌گرداند.
        with self.lock:
            return self.latest_tracked_frame

    def stop(self):
        self.running = False
        self.stop_event.set()
        for thread in (self.thread, self.track_thread):
            if thread is not None:
                thread.join()
        self.thread = None
        self.track_thread = None
