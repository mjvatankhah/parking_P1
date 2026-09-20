


from dataclasses import dataclass


@dataclass
class Detection:
    track_id: int
    bbox: tuple
    class_id: int
    confidence: float


@dataclass
class TrackedFrame:
    camera_id: str
    frame_idx: int
    ts: float
    image: object
    detections: list

