"""
برای هر ماشین یعنی هر (camera_id, track_id) فقط بهترین crop دیده‌شده تا الان رو
نگه می‌داره - نه یه بافر ثابت N فریمی. با اومدن هر فریم جدید، اگه crop اون فریم
از بهترین قبلی بهتر بود جایگزینش می‌کنه.
"""
import time
import cv2


class BestCropSelector:
    def __init__(self, stale_after=5.0):
        self.best_frames = {}   # (camera_id, track_id) -> {'crop','score','sharpness','frame_idx','ts'}
        self.stale_after = stale_after
        self._retained = set()

    def _score(self, image, bbox, confidence):
        x1, y1, x2, y2 = map(int, bbox)
        h, w = image.shape[:2]
        if x1 <= 0 or y1 <= 0 or x2 >= w or y2 >= h:
            return None  # ماشین کامل تو فریم نیست، رد کن
        crop = image[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        area = (x2 - x1) * (y2 - y1)
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
        score = area * 0.001 + sharpness + confidence * 100
        return score, crop, sharpness

    def update(self, camera_id, tracked_frame, excluded_tracks=()):
        now = time.monotonic()
        for det in tracked_frame.detections:
            if det.track_id in excluded_tracks:
                continue
            key = (camera_id, det.track_id)
            current = self.best_frames.get(key)
            if current is not None:
                current['last_seen'] = now
            result = self._score(tracked_frame.image, det.bbox, det.confidence)
            if result is None:
                continue
            score, crop, sharpness = result
            if current is None or score > current['score']:
                self.best_frames[key] = {
                    'crop': crop.copy(),
                    'score': score,
                    'sharpness': sharpness,
                    'frame_idx': tracked_frame.frame_idx,
                    'ts': now,
                    'last_seen': now,
                }
        self._cleanup(now)

    def retain(self, camera_id, track_id):
        """Keep the candidate until the crossing window is finalized."""
        self._retained.add((camera_id, track_id))

    def get(self, camera_id, track_id):
        """
        بهترین crop رو برمی‌گردونه و همون لحظه از best_frames حذفش می‌کنه.
        پس از پایان بازهٔ انتخاب، نگهداری محافظت‌شدهٔ این خودرو هم تمام می‌شود.
        """
        self._retained.discard((camera_id, track_id))
        return self.best_frames.pop((camera_id, track_id), None)

    def _cleanup(self, now):
        stale = [k for k, v in self.best_frames.items()
                 if k not in self._retained
                 and now - v['last_seen'] > self.stale_after]
        for k in stale:
            del self.best_frames[k]
