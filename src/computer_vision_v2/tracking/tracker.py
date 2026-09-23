import numpy as np
from ultralytics import YOLO

from .frame_info import Detection, TrackedFrame


VEHICLE_CLASSES = [0,2] 


class CameraTracker:

    def __init__(self, camera_id, model_path):
        self.camera_id = camera_id
        self.model = YOLO("yolov8n_openvino_model", task="detect")

    def warmup(self):
        # آماده‌سازی سنگین OpenVINO قبل از شروع ویدئو انجام می‌شود.
        # تصویر سیاه وارد صف‌ها و پیش‌نمایش نمی‌شود.
        image = np.zeros((720, 1280, 3), dtype=np.uint8)
        for _ in range(2):
            self.process(frame_idx=0, ts=0, image=image)
        # سابقهٔ تصویر آزمایشی نباید روی شناسه‌های خودروهای واقعی اثر بگذارد.
        for tracker in self.model.predictor.trackers:
            tracker.reset()
        
    # تابع پردازش فریم
    def process(self, frame_idx, ts, image):
        
        results = self.model.track(
            image,
            persist=True,
            classes=VEHICLE_CLASSES,
            verbose=False,
            tracker="bytetrack.yaml",
            imgsz=(256,416)
            
        )
        result = results[0]
        
        detections = []

        if not results:
            return TrackedFrame(
                camera_id=self.camera_id,
                frame_idx=frame_idx,
                ts=ts,
                image=image,
                detections=[],
            )

        boxes = results[0].boxes

        if boxes.id is None:
            return TrackedFrame(
                camera_id=self.camera_id,
                frame_idx=frame_idx,
                ts=ts,
                image=image,
                detections=[],
            )

        xyxy = boxes.xyxy.cpu().numpy()
        ids = boxes.id.int().cpu().tolist()
        classes = boxes.cls.int().cpu().tolist()
        confidences = boxes.conf.cpu().tolist()

        for box, track_id, class_id, confidence in zip(
            xyxy,
            ids,
            classes,
            confidences,
        ):
            detections.append(
                Detection(
                    track_id=track_id,
                    bbox=tuple(box),
                    class_id=class_id,
                    confidence=confidence,
                )
            )

        return TrackedFrame(
            camera_id=self.camera_id,
            frame_idx=frame_idx,
            ts=ts,
            image=image,
            detections=detections,
        )
