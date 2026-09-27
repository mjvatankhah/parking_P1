


from dataclasses import dataclass


@dataclass
class Detection:
    track_id: int
    bbox: tuple
    class_id: int
    confidence: float
    # confidence remains the last YOLO score, not optical-flow confidence.
    is_predicted: bool = False
    tracking_quality: float | None = None


@dataclass
class TrackedFrame:
    camera_id: str
    frame_idx: int
    ts: float
    image: object
    detections: list
