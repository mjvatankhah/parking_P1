"""Small OpenCV reader used by the dashboard's live camera cards.

Capture happens on a worker thread because opening an RTSP source can block.
The Kivy UI only polls the latest decoded frame and therefore stays responsive.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

import cv2

from computer_vision_v2.reno.models.camera import Camera, SOURCE_TYPE_VIDEO_FILE


class VideoStream:
    def __init__(self, camera: Camera, on_state: Optional[Callable[[str], None]] = None):
        self.camera = camera
        self.on_state = on_state
        self._capture = None
        self._frame = None
        self._frame_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"reno-{camera.id}")

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def latest_frame(self):
        with self._frame_lock:
            return None if self._frame is None else self._frame.copy()

    def _set_state(self, state: str) -> None:
        if self.on_state:
            self.on_state(state)

    def _run(self) -> None:
        self._set_state("connecting")
        while not self._stop.is_set():
            source = self.camera.source
            if self.camera.source_type == SOURCE_TYPE_VIDEO_FILE:
                path = Path(source).expanduser()
                if not path.is_absolute():
                    path = Path(__file__).resolve().parents[4] / path
                source = str(path)
            if self.camera.source_type == SOURCE_TYPE_VIDEO_FILE:
                capture = cv2.VideoCapture(source)
            else:
                capture = cv2.VideoCapture(
                    source, cv2.CAP_FFMPEG,
                    [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000,
                     cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000],
                )
            self._capture = capture
            if not capture.isOpened():
                self._set_state("offline")
                capture.release()
                if self.camera.source_type == SOURCE_TYPE_VIDEO_FILE:
                    return
                self._stop.wait(2.0)
                continue

            self._set_state("online")
            while not self._stop.is_set():
                ok, frame = capture.read()
                if not ok:
                    if self.camera.source_type == SOURCE_TYPE_VIDEO_FILE:
                        capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ok, frame = capture.read()
                        if not ok:
                            self._set_state("offline")
                            break
                    else:
                        self._set_state("offline")
                        break
                with self._frame_lock:
                    self._frame = frame
                # Avoid decoding local files as fast as the CPU permits.
                if self.camera.source_type == SOURCE_TYPE_VIDEO_FILE:
                    fps = capture.get(cv2.CAP_PROP_FPS) or 25
                    self._stop.wait(max(0.001, 1.0 / min(fps, 60)))

            capture.release()
            if self.camera.source_type == SOURCE_TYPE_VIDEO_FILE:
                return
            self._stop.wait(1.0)

        self._set_state("offline")
