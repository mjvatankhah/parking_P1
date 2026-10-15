"""One camera's capture, tracking, and reconnection lifecycle."""

import logging
import threading
import time
from typing import NamedTuple

from .Source_Base import RTSPSource, VideoSource
from computer_vision_v2.tracking.tracker import CameraTracker


logger = logging.getLogger(__name__)
MAX_READ_FAILURES = 30
MAX_RETRY_DELAY = 30


class CapturedFrame(NamedTuple):
    index: int
    received_at: float
    image: object


class StreamManager:
    def __init__(self, camera_id, source, source_type, model_path, detection_interval=3, roi=None):
        self.camera_id = camera_id
        self.source = source
        self.source_type = source_type
        self.tracker = CameraTracker(camera_id, model_path, detection_interval, roi=roi)

        self._stop = threading.Event()
        self.ended = threading.Event()
        self._condition = threading.Condition()
        self._latest_capture = None
        self._latest_tracked = None
        self._capture_index = 0
        self._capture_thread = None
        self._process_thread = None

    def _create_source(self):
        if self.source_type == "video":
            return VideoSource(self.source)
        if self.source_type == "rtsp":
            return RTSPSource(self.source)
        raise ValueError(f"Unknown source type for camera {self.camera_id}")

    def start(self):
        if self._capture_thread is not None:
            raise RuntimeError(f"Camera {self.camera_id} already started")
        if self.source_type not in ("rtsp", "video"):
            raise ValueError(f"Unknown source type for camera {self.camera_id}")
        self._stop.clear()
        if self.source_type == "rtsp":
            self._process_thread = threading.Thread(
                target=self._process_loop, name=f"tracking-{self.camera_id}", daemon=True
            )
        self._capture_thread = threading.Thread(
            target=self._capture_loop if self.source_type == "rtsp" else self._video_loop,
            name=f"capture-{self.camera_id}", daemon=True
        )
        try:
            if self._process_thread is not None:
                self._process_thread.start()
            self._capture_thread.start()
        except Exception:
            self.stop()
            raise

    def _video_loop(self):
        # File playback must not decode a clip faster than tracking can consume it.
        source = None
        try:
            source = self._create_source()
            source.connect()
            while not self._stop.is_set():
                ok, image = source.get_frame()
                if not ok:
                    return
                self._capture_index += 1
                fps = getattr(source, 'fps', 25.)
                tracked = self.tracker.process(self._capture_index, self._capture_index/fps, image)
                with self._condition:
                    self._latest_tracked = tracked
        except Exception:
            logger.exception("Camera %s video playback failed", self.camera_id)
        finally:
            if source is not None:
                source.disconnect()
            self.ended.set()

    def _capture_loop(self):
        retry_delay = 1
        try:
            while not self._stop.is_set():
                source = None
                try:
                    source = self._create_source()
                    source.connect()
                    retry_delay = 1
                    failures = 0
                    while not self._stop.is_set():
                        ok, image = source.get_frame()
                        if not ok:
                            failures += 1
                            if failures >= MAX_READ_FAILURES:
                                raise ConnectionError("too many failed reads")
                            self._stop.wait(0.1)
                            continue

                        failures = 0
                        captured_at = time.monotonic()
                        with self._condition:
                            self._capture_index += 1
                            self._latest_capture = CapturedFrame(
                                self._capture_index, captured_at, image
                            )
                            self._condition.notify()
                except Exception as exc:
                    # OpenCV errors can contain an RTSP URL with credentials.
                    logger.warning("Camera %s disconnected (%s)", self.camera_id, type(exc).__name__)
                finally:
                    with self._condition:
                        self._latest_capture = None
                    if source is not None:
                        try:
                            source.disconnect()
                        except Exception:
                            logger.exception("Camera %s could not release capture", self.camera_id)

                if self._stop.wait(retry_delay):
                    return
                retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
        finally:
            with self._condition:
                self._condition.notify_all()

    def _process_loop(self):
        while not self._stop.is_set():
            with self._condition:
                self._condition.wait_for(
                    lambda: self._latest_capture is not None or self._stop.is_set(), timeout=0.5
                )
                if self._stop.is_set():
                    return
                if self._latest_capture is None:
                    continue
                frame = self._latest_capture
                self._latest_capture = None

            try:
                tracked = self.tracker.process(frame.index, frame.received_at, frame.image)
            except Exception:
                logger.exception("Camera %s tracking failed", self.camera_id)
                continue
            with self._condition:
                self._latest_tracked = tracked

    def get_latest_frame(self):
        with self._condition:
            return self._latest_tracked

    def stop(self):
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        for name in ("_capture_thread", "_process_thread"):
            thread = getattr(self, name)
            if thread is not None:
                if thread.ident is None:
                    setattr(self, name, None)
                    continue
                thread.join(timeout=7)
                if thread.is_alive():
                    logger.error("Camera %s did not stop %s within seven seconds", self.camera_id, thread.name)
                else:
                    setattr(self, name, None)
        return self._capture_thread is None and self._process_thread is None
