"""Bounded, local preview bridge between the pipeline and desktop UI.

Only the newest frame per camera is retained. JPEG encoding and drawing run
outside the pipeline thread; original images and detections are never modified.
"""
import hashlib
import logging
import os
from pathlib import Path
import tempfile
import threading
import time

import cv2
import numpy as np


MAX_FRAME_AGE = 5.0
PREVIEW_FPS = 30
PREVIEW_MAX_WIDTH = 960


def preview_path(camera_id, source):
    key = hashlib.sha256(f"{camera_id}\0{source}".encode()).hexdigest()
    user = str(os.getuid()) if hasattr(os, "getuid") else os.environ.get("USERNAME", "local")
    return Path(tempfile.gettempdir()) / f"kalpino-preview-{user}" / f"{key}.jpg"


def annotate_frame(frame):
    # تصویر خام فقط خوانده می‌شود؛ کپی زمانی لازم است که روی تصویر رسم کنیم.
    image = frame.image.copy() if frame.detections else frame.image
    height, width = image.shape[:2]
    for detection in frame.detections:
        if detection.class_id not in (0, 2):
            continue
        x1, y1, x2, y2 = map(int, detection.bbox)
        x1, x2 = (max(0, min(width - 1, x)) for x in (x1, x2))
        y1, y2 = (max(0, min(height - 1, y)) for y in (y1, y2))
        color = (80, 210, 80) if detection.class_id == 0 else (255, 180, 40)
        label = "Person" if detection.class_id == 0 else "Car"
        label += f" #{detection.track_id} {detection.confidence:.0%}"
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        cv2.putText(image, label, (x1, max(18, y1 - 7)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
    if width > PREVIEW_MAX_WIDTH:
        image = cv2.resize(image, (PREVIEW_MAX_WIDTH, max(1, round(height * PREVIEW_MAX_WIDTH / width))))
    return image


class PreviewPublisher:
    def __init__(self, cameras):
        self._paths = {c['id']: preview_path(c['id'], c['source']) for c in cameras}
        self._pending = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="camera-preview")
        self._thread.start()

    def publish(self, frame):
        with self._lock:
            self._pending[frame.camera_id] = (frame, time.time())

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        with self._lock:
            self._pending.clear()
        for path in self._paths.values():
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logging.getLogger(__name__).warning("Could not remove preview %s", path)

    def _run(self):
        while not self._stop.is_set():
            started = time.monotonic()
            with self._lock:
                pending, self._pending = self._pending, {}
            for camera_id, (frame, received_at) in pending.items():
                try:
                    self._write(self._paths[camera_id], frame, received_at)
                except Exception:
                    # Preview failures must never interrupt recognition/OCR.
                    logging.getLogger(__name__).exception("Preview failed for %s", camera_id)
            # زمان encode هم جزو فاصلهٔ فریم‌هاست؛ هر بار ۳۳ میلی‌ثانیه اضافه نمی‌کنیم.
            self._stop.wait(max(0, 1 / PREVIEW_FPS - (time.monotonic() - started)))

    @staticmethod
    def _write(path, frame, received_at):
        ok, encoded = cv2.imencode(".jpg", annotate_frame(frame), [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            return
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(encoded.tobytes())
            os.utime(temporary, (received_at, received_at))
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def read_preview(path, last_version=None):
    """Return (BGR image, version); stale/missing frames return (None, None)."""
    try:
        with path.open('rb') as handle:
            stat = os.fstat(handle.fileno())
            if time.time() - stat.st_mtime > MAX_FRAME_AGE:
                return None, None
            version = (stat.st_mtime_ns, stat.st_ino)
            if version == last_version:
                return None, version
            image = cv2.imdecode(np.frombuffer(handle.read(), dtype=np.uint8), cv2.IMREAD_COLOR)
            return (image, version) if image is not None else (None, None)
    except OSError:
        return None, None
