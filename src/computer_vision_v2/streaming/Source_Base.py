from abc import ABC, abstractmethod
from pathlib import Path
import cv2 as cv
import math

class BaseSource(ABC):

    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def get_frame(self):
        pass

    @abstractmethod
    def disconnect(self):
        pass
#--------------------------------

class VideoSource(BaseSource):

    def __init__(self, path):
        # Camera file paths are relative to the project, just like monitoring.
        path = Path(path).expanduser()
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[3] / path
        self.path = str(path)
        self.capture = None
        self.fps = 25.

    def connect(self):
        self.capture = cv.VideoCapture(self.path)
        if not self.capture.isOpened():
            raise RuntimeError(f"Could not open video: {self.path}")
        fps = self.capture.get(cv.CAP_PROP_FPS)
        self.fps = fps if math.isfinite(fps) and fps > 0 else 25.

    def get_frame(self):

        return self.capture.read()
        
    

    def disconnect(self):
        
        if self.capture is not None:
            self.capture.release()
            self.capture = None

class RTSPSource(BaseSource):

    def __init__(self, rtsp_url):
        self.url = rtsp_url
        self.capture = None

    def connect(self):
        self.capture = cv.VideoCapture(
            self.url,
            cv.CAP_FFMPEG,
            [cv.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv.CAP_PROP_READ_TIMEOUT_MSEC, 5000],
        )
        if not self.capture.isOpened():
            self.disconnect()
            raise RuntimeError("Could not open RTSP stream")

    def get_frame(self):
        if self.capture is None:
            raise RuntimeError("RTSP source is not get_frame")
            
        return self.capture.read()

    def disconnect(self):
        if self.capture is not None:
            self.capture.release()
            self.capture = None
