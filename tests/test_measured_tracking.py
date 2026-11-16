"""Entering from the image edge must not inflate a vehicle into its neighbour."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import torch
from ultralytics.engine.results import Results
from ultralytics.trackers.byte_tracker import BYTETracker
from computer_vision_v2.tracking.tracker import CameraTracker


class DetectorSequence:
    def __init__(self, boxes):
        self.boxes = iter(boxes)
        self.legacy = BYTETracker(SimpleNamespace(track_high_thresh=.25, track_low_thresh=.1,
            new_track_thresh=.25, track_buffer=30, match_thresh=.8, fuse_score=True))

    def predict(self, image, **kwargs):
        boxes = np.array(next(self.boxes), dtype=np.float32).reshape(-1, 6)
        return [Results(image, path='test', names={2: 'car'}, boxes=torch.from_numpy(boxes))]

    def track(self, image, **kwargs):
        result = self.predict(image)[0]
        tracks = self.legacy.update(result.boxes.numpy(), image)
        if len(tracks):
            result = result[tracks[:, -1].astype(int)]
            result.update(boxes=torch.from_numpy(tracks[:, :-1]))
        return [result]


class MeasuredTrackingTests(unittest.TestCase):
    def test_partial_entry_keeps_measured_boxes_and_identity(self):
        # Recorded cc2 detections, starting while only a narrow top-edge slice is visible.
        boxes = [
            [722.66, 0, 1015.01, 70.36], [665.21, .37, 1017.37, 114.97],
            [604.15, 0, 986.85, 165.48], [549.1, 0, 955.9, 221.1],
            [507.48, 3, 924.79, 290.17], [480.91, 1.87, 898.51, 358.50],
            [469.82, 2.42, 892.05, 435.65], [480.37, 31.91, 916.91, 503.39],
            [509.47, 79.08, 979.34, 615.86],
        ]
        model = DetectorSequence([[b + [.9, 2]] for b in boxes])
        with patch('computer_vision_v2.tracking.tracker.YOLO', return_value=model):
            tracker = CameraTracker('test', 'unused', 1)
        image = np.zeros((1080, 1920, 3), np.uint8)
        ids = []
        for i, box in enumerate(boxes):
            frame = tracker.process(i, i * .2, image)
            self.assertEqual(len(frame.detections), 1)
            det = frame.detections[0]
            np.testing.assert_allclose(det.bbox, box, atol=.01)
            # Correcting only the public output leaves the inflated internal
            # state in matching, where it can steal a neighbouring vehicle's ID.
            state = next(s for s in tracker.association._tracker.tracked_stracks
                         if s.track_id == det.track_id)
            self.assertLess(state.tlwh[2], 1.5 * (box[2] - box[0]))
            ids.append(det.track_id)
        self.assertEqual(len(set(ids)), 1)

    def test_empty_frame_and_reordered_neighbour_keep_measurement_assignment(self):
        a = [100, 100, 200, 200, .9, 2]
        b = [400, 100, 500, 200, .8, 2]
        # The low-score match must retain its original detection index even
        # after ByteTrack splits high/low confidence sets and reorders tracks.
        low_b = b[:4] + [.2, 2]
        model = DetectorSequence([[a, b], [low_b, a], [], [a, b]])
        with patch('computer_vision_v2.tracking.tracker.YOLO', return_value=model):
            tracker = CameraTracker('test', 'unused', 1)
        image = np.zeros((600, 800, 3), np.uint8)
        outputs = [tracker.process(i, i * .2, image).detections for i in range(4)]
        self.assertEqual(outputs[2], [])
        first = {d.track_id: d.bbox for d in outputs[0]}
        self.assertEqual(len(first), 2)
        for detections in (outputs[1], outputs[3]):
            self.assertEqual({d.track_id: d.bbox for d in detections}, first)
