from abc import ABC, abstractmethod
import math
import cv2 as cv

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
        self.path = path
        self.capture = None

    def connect(self):
        self.capture = cv.VideoCapture(self.path)
        if not self.capture.isOpened():
            raise RuntimeError(f"Could not open video: {self.path}")

    def get_frame(self):

        return self.capture.read()

    def get_fps(self):
        fps = self.capture.get(cv.CAP_PROP_FPS)
        return fps if math.isfinite(fps) and fps > 0 else 25.0
        
    

    def disconnect(self):
        
        if self.capture is not None:
            self.capture.release()
            self.capture = None

class RTSPSource(BaseSource):

    def __init__(self, rtsp_url):
        self.url = rtsp_url
        self.capture = None

    def connect(self):
        self.capture = cv.VideoCapture(self.url)
        if not self.capture.isOpened():
            raise RuntimeError(f"Could not open RTSP stream: {self.url}")

    def get_frame(self):
        if self.capture is None:
            raise RuntimeError("RTSP source is not get_frame")
            
        return self.capture.read()

    def disconnect(self):
        if self.capture is not None:
            self.capture.release()
            self.capture = None

class DVRSource:

    pass
