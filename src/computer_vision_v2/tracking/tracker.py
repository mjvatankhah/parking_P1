from ultralytics import YOLO
import cv2
import numpy as np

from .frame_info import Detection, TrackedFrame
from .optical_flow import OpticalFlow


VEHICLE_CLASSES = [0, 2]


class CameraTracker:
    def __init__(self, camera_id, model_path, detection_interval=3, roi=None):
        if isinstance(detection_interval, bool) or not isinstance(detection_interval, int) or detection_interval < 1:
            raise ValueError("detection_interval must be a positive integer")
        self.camera_id = camera_id
        self.roi = None
        if roi is not None:
            points = np.asarray(roi, dtype=np.float32)
            if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3 or not np.isfinite(points).all() or (points < 0).any() or (points > 1).any() or cv2.contourArea(points) == 0:
                raise ValueError('ROI must be a nonempty normalized polygon')
            self.roi = points
        # Keep the deployed backend/size unchanged for this tracking change.
        self.model = YOLO(model_path, task="detect")
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
        print(f"[FRAME] camera={self.camera_id} frame={frame_idx} processing", flush=True)
        original = image
        offset_x = offset_y = 0
        polygon = None
        if self.roi is not None:
            h, w = image.shape[:2]
            polygon = np.rint(self.roi * [w-1,h-1]).astype(np.int32)
            offset_x, offset_y, rw, rh = cv2.boundingRect(polygon)
            image = image[offset_y:offset_y+rh, offset_x:offset_x+rw].copy()
            mask = np.zeros((rh,rw), np.uint8)
            cv2.fillPoly(mask, [polygon-[offset_x,offset_y]], 255)
            image[mask==0] = 0
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
        output = []
        for detection in detections:
            x1,y1,x2,y2 = detection.bbox
            bbox = (x1+offset_x,y1+offset_y,x2+offset_x,y2+offset_y)
            if polygon is not None and cv2.pointPolygonTest(polygon, (float((bbox[0]+bbox[2])/2),float(bbox[3])), False) < 0:
                continue
            output.append(Detection(detection.track_id, bbox, detection.class_id,
                                    detection.confidence, detection.is_predicted, detection.tracking_quality))
        return TrackedFrame(self.camera_id, frame_idx, ts, original, output)
