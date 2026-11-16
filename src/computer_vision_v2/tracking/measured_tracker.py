"""ByteTrack association with independent width/height and measured output boxes."""
from types import SimpleNamespace

from ultralytics.trackers.byte_tracker import BYTETracker
from ultralytics.trackers.bot_sort import BOTrack
from ultralytics.trackers.utils.kalman_filter import KalmanFilterXYWH
from ultralytics.utils import YAML
from ultralytics.utils.checks import check_yaml

from .frame_info import Detection


class _WidthHeightTracker(BYTETracker):
    # Reuse the XYWH track state, without enabling BoT-SORT's ReID or camera
    # motion compensation. ByteTrack association and thresholds stay unchanged.
    track_class = BOTrack

    def get_kalmanfilter(self):
        return KalmanFilterXYWH()

    def multi_predict(self, tracks):
        BOTrack.multi_predict(tracks)


class MeasuredTracker:
    def __init__(self):
        args = SimpleNamespace(**YAML.load(check_yaml('bytetrack.yaml')))
        self._tracker = _WidthHeightTracker(args)

    def update(self, boxes, image):
        measurements = boxes.cpu().numpy()
        tracks = self._tracker.update(measurements, image)
        output = []
        for track in tracks:
            # ByteTrack returns the matched detection index in its last column.
            # Use it, rather than list order or overlap with the predicted box.
            index = int(track[-1])
            output.append(Detection(
                track_id=int(track[4]),
                bbox=tuple(float(v) for v in measurements.xyxy[index]),
                class_id=int(measurements.cls[index]),
                confidence=float(measurements.conf[index]),
            ))
        return output
