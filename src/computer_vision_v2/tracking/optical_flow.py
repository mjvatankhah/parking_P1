"""Short-lived visual tracking between detector updates (no new object IDs)."""
from dataclasses import replace

import cv2
import numpy as np


class OpticalFlow:
    def __init__(self, max_width=640):
        self.max_width = max_width
        self.previous = None
        self.shape = None
        self.tracks = []

    def _gray(self, image):
        h, w = image.shape[:2]
        width = min(w, self.max_width)
        height = max(1, round(h * width / w))
        small = cv2.resize(image, (width, height)) if width != w else image
        return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), np.array([width / w, height / h])

    def seed(self, image, detections):
        self.previous, scale = self._gray(image)
        self.shape = image.shape[:2]
        self.tracks = []
        h, w = self.previous.shape
        for det in detections:
            x1, y1, x2, y2 = np.rint(np.array(det.bbox) * np.tile(scale, 2)).astype(int)
            x1, x2 = np.clip([x1, x2], 0, w)
            y1, y2 = np.clip([y1, y2], 0, h)
            points = None
            if x2 - x1 >= 5 and y2 - y1 >= 5:
                points = cv2.goodFeaturesToTrack(
                    self.previous[y1:y2, x1:x2], maxCorners=40,
                    qualityLevel=0.02, minDistance=4, blockSize=3,
                )
                if points is not None:
                    points += np.array([x1, y1], dtype=np.float32)
            self.tracks.append((det, points))

    def advance(self, image):
        """Return updated detections, or None to request an immediate detector refresh."""
        if self.previous is None or image.shape[:2] != self.shape:
            return None
        gray, scale = self._gray(image)
        if not self.tracks:
            self.previous = gray
            return []
        if any(points is None or len(points) < 5 for _, points in self.tracks):
            return None

        before = np.concatenate([points for _, points in self.tracks])
        options = dict(winSize=(21, 21), maxLevel=3,
                       criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03))
        after, forward_ok, _ = cv2.calcOpticalFlowPyrLK(self.previous, gray, before, None, **options)
        if after is None:
            return None
        back, backward_ok, _ = cv2.calcOpticalFlowPyrLK(gray, self.previous, after, None, **options)
        if back is None:
            return None
        valid = (forward_ok.ravel() == 1) & (backward_ok.ravel() == 1)
        valid &= np.linalg.norm(back[:, 0] - before[:, 0], axis=1) < 1.5
        valid &= np.isfinite(after[:, 0]).all(axis=1)
        valid &= (after[:, 0, 0] >= 0) & (after[:, 0, 0] < gray.shape[1])
        valid &= (after[:, 0, 1] >= 0) & (after[:, 0, 1] < gray.shape[0])

        updated = []
        offset = 0
        for det, points in self.tracks:
            end = offset + len(points)
            keep = valid[offset:end]
            old = before[offset:end, 0][keep]
            new = after[offset:end, 0][keep]
            offset = end
            if len(new) < 5 or len(new) / len(points) < 0.5:
                return None
            matrix, inliers = cv2.estimateAffinePartial2D(old, new, method=cv2.RANSAC,
                                                        ransacReprojThreshold=2.0)
            if matrix is None or not np.isfinite(matrix).all():
                return None
            inliers = inliers.ravel().astype(bool)
            quality = float(inliers.sum() / len(points)) * (
                det.tracking_quality if det.tracking_quality is not None else 1.0
            )
            zoom = float(np.hypot(matrix[0, 0], matrix[1, 0]))
            angle = abs(float(np.arctan2(matrix[1, 0], matrix[0, 0])))
            if inliers.sum() < 5 or quality < 0.5 or not 0.9 <= zoom <= 1.1 or angle > np.deg2rad(10):
                return None
            x1, y1, x2, y2 = np.array(det.bbox) * np.tile(scale, 2)
            # Move the center and scale its extent; repeatedly bounding rotated
            # rectangles inflates boxes even when the object size is unchanged.
            center = np.array([(x1 + x2) / 2, (y1 + y2) / 2])
            center = (matrix[:, :2] @ center + matrix[:, 2]) / scale
            half_size = np.array([x2 - x1, y2 - y1]) * zoom / (2 * scale)
            lo, hi = center - half_size, center + half_size
            h, w = image.shape[:2]
            lo = np.clip(lo, [0, 0], [w, h])
            hi = np.clip(hi, [0, 0], [w, h])
            if np.any(hi - lo < 2):
                return None
            prediction = replace(det, bbox=tuple(map(float, (*lo, *hi))),
                                 is_predicted=True, tracking_quality=quality)
            updated.append((prediction, new[inliers].reshape(-1, 1, 2)))
        self.previous = gray
        self.tracks = updated
        return [det for det, _ in updated]
