from ultralytics import YOLO

from .frame_info import Detection, TrackedFrame
from .optical_flow import OpticalFlow


VEHICLE_CLASSES = [0, 2]


class CameraTracker:
    def __init__(self, camera_id, model_path, detection_interval=3):
        if isinstance(detection_interval, bool) or not isinstance(detection_interval, int) or detection_interval < 1:
            raise ValueError("detection_interval must be a positive integer")
        self.camera_id = camera_id
        # Keep the deployed backend/size unchanged for this tracking change.
        self.model = YOLO("yolov8n_openvino_model", task="detect")
        self.detection_interval = detection_interval
        self.flow = OpticalFlow()
        self._since_detection = detection_interval
        self._last_idx = None
        self._last_ts = None
        self.yolo_calls = 0
        self.flow_frames = 0
        self.flow_fallbacks = 0

    def _detect(self, image):
        results = self.model.track(
            image, persist=True, classes=VEHICLE_CLASSES, verbose=False,
            tracker="bytetrack.yaml", imgsz=(256, 416),
        )
        self.yolo_calls += 1
        if not results or results[0].boxes is None or results[0].boxes.id is None:
            return []
        boxes = results[0].boxes
        return [
            Detection(track_id=track_id, bbox=tuple(box), class_id=class_id, confidence=confidence)
            for box, track_id, class_id, confidence in zip(
                boxes.xyxy.cpu().numpy(), boxes.id.int().cpu().tolist(),
                boxes.cls.int().cpu().tolist(), boxes.conf.cpu().tolist(),
            )
        ]

    def process(self, frame_idx, ts, image):
        # LK requires adjacent images. Re-detect after a discontinuity or long outage.
        discontinuity = self._last_idx is not None and (
            frame_idx != self._last_idx + 1 or ts <= self._last_ts or ts - self._last_ts > 1.0
        )
        detect = self._since_detection >= self.detection_interval - 1 or discontinuity
        detections = None
        if not detect:
            detections = self.flow.advance(image)
            if detections is None:
                self.flow_fallbacks += 1
                detect = True
        if detect:
            detections = self._detect(image)
            self._since_detection = 0
            if self.detection_interval > 1:
                self.flow.seed(image, detections)
        else:
            self._since_detection += 1
            self.flow_frames += 1
        self._last_idx, self._last_ts = frame_idx, ts
        return TrackedFrame(self.camera_id, frame_idx, ts, image, detections)
