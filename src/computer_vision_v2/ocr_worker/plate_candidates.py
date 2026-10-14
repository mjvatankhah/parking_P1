"""Keep one crossing open while its vehicle remains visible in the ROI."""
from dataclasses import dataclass, field
import logging
import math

import cv2
import numpy as np
from computer_vision_v2.inference.plate_geometry import prepare_plate

logger = logging.getLogger(__name__)

@dataclass(eq=False)
class Candidate:
    crop: object
    ts: float
    frame_idx: int
    confidence: float
    quality: float
    context: object = None
    prepared: object = None


@dataclass
class TrackEvidence:
    seen: float
    bbox: tuple
    aliases: set = field(default_factory=set)
    event: dict | None = None
    sampled: float = -math.inf
    sampled_predicted: bool = False
    candidates: list = field(default_factory=list)
    fallback: Candidate | None = None


@dataclass
class CompletedPassage:
    event: dict
    candidates: list


class PlateCandidates:
    def __init__(self, reader, interval=0.1, capacity=12, near=0.09, stale=5.0,
                 exit_delay=0.75, reid_gap=0.5, reid_iou=0.35):
        if (not all(math.isfinite(v) for v in (interval, near, stale, exit_delay, reid_gap, reid_iou))
                or interval <= 0 or near < 0 or stale <= 0 or exit_delay <= 0
                or reid_gap <= 0 or reid_gap > exit_delay or not 0 < reid_iou <= 1
                or isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1):
            raise ValueError('Invalid candidate buffer limits')
        self.reader = reader
        self.interval, self.capacity, self.near, self.stale = interval, capacity, near, stale
        self.exit_delay, self.reid_gap, self.reid_iou = exit_delay, reid_gap, reid_iou
        self.tracks = {}
        self.aliases = {}
        self.closed = {}

    @staticmethod
    def _iou(a, b):
        x1, y1 = max(a[0], b[0]), max(a[1], b[1])
        x2, y2 = min(a[2], b[2]), min(a[3], b[3])
        intersection = max(0, x2-x1) * max(0, y2-y1)
        area_a = max(0, a[2]-a[0]) * max(0, a[3]-a[1])
        area_b = max(0, b[2]-b[0]) * max(0, b[3]-b[1])
        return intersection / (area_a + area_b - intersection) if intersection else 0.0

    def _attach_tracks(self, frame, detections):
        """Associate a new tracker ID only with one recently missing, nearby car."""
        visible = {(frame.camera_id, det.track_id) for det in detections}
        assigned = {self.aliases[key] for key in visible if key in self.aliases}
        for det in detections:
            key = (frame.camera_id, det.track_id)
            if key in self.aliases or key in self.closed:
                continue
            options = sorted(
                ((self._iou(det.bbox, state.bbox), canonical)
                 for canonical, state in self.tracks.items()
                 if canonical[0] == frame.camera_id and canonical not in assigned
                 and frame.ts - state.seen <= self.reid_gap),
                reverse=True,
            )
            # Ambiguous overlap must not join two simultaneous vehicles.
            match = options[0][1] if options and options[0][0] >= self.reid_iou and (
                len(options) == 1 or options[0][0] - options[1][0] >= 0.15) else None
            if match is None:
                match = key
                self.tracks[match] = TrackEvidence(frame.ts, tuple(det.bbox))
            self.aliases[key] = match
            self.tracks[match].aliases.add(key)
            assigned.add(match)

    def _retire(self, key, now):
        state = self.tracks.pop(key)
        for alias in state.aliases:
            del self.aliases[alias]
            if state.event is not None:
                self.closed[alias] = now
        if state.event is None:
            return None
        crops = state.candidates + ([state.fallback] if state.fallback else [])
        return CompletedPassage(state.event, crops)

    def _sample(self, frame, det, state):
        predicted = getattr(det, 'is_predicted', False)
        elapsed = frame.ts - state.sampled
        # Prefer current detector boxes; use optical flow after a longer gap.
        if predicted and elapsed + 1e-9 < 2 * self.interval:
            return
        # Three frames at 30.015 FPS are just under 100 ms.
        if not predicted and not state.sampled_predicted and elapsed + 1e-9 < .9 * self.interval:
            return
        state.sampled = frame.ts
        state.sampled_predicted = predicted
        h, w = frame.image.shape[:2]
        x1, y1, x2, y2 = map(int, det.bbox)
        vehicle = frame.image[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        if not vehicle.size:
            return
        try:
            detection = self.reader.detect_plate(vehicle)
        except Exception:
            logger.exception('Plate detection failed for %s/%s', frame.camera_id, det.track_id)
            return
        if detection is None:
            return
        crop, confidence, context = detection
        ph, pw = crop.shape[:2]
        if ph < 8 or pw < 30:
            return
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        exposure = float(np.mean((gray < 8) | (gray > 247)))
        sharp = float(cv2.Laplacian(gray, cv2.CV_32F).var())
        # Saturation prevents noisy backgrounds from winning through unbounded sharpness.
        quality = (
            0.5 * confidence
            + 0.2 * min(ph / 32, 1)
            + 0.2 * min(sharp / 500, 1)
            + 0.1 * min(float(gray.std()) / 40, 1)
        ) * (1 - exposure)
        candidate = Candidate(crop.copy(), frame.ts, frame.frame_idx, confidence, quality, context)
        if 1.15 <= pw / ph <= 8 and exposure <= 0.9:
            try:
                candidate.prepared = prepare_plate(context if context is not None else crop)
            except Exception:
                logger.exception('Plate geometry failed for %s/%s', frame.camera_id, det.track_id)
        if candidate.prepared is None:
            if state.fallback is None or quality > state.fallback.quality:
                state.fallback = candidate
            return
        nearby = [c for c in state.candidates if abs(c.ts - frame.ts) < self.near]
        if nearby and max(c.quality for c in nearby) >= quality:
            return
        state.candidates = [c for c in state.candidates if c not in nearby]
        state.candidates.append(candidate)
        state.candidates.sort(key=lambda c: c.quality, reverse=True)
        del state.candidates[self.capacity:]

    def observe(self, frame, crossings=()):
        """Return crossings ready for OCR once their car is no longer visible."""
        for key, seen in list(self.closed.items()):
            if key[0] == frame.camera_id and frame.ts - seen > 60.0:
                del self.closed[key]
        detections = [det for det in frame.detections if det.class_id == 2]
        self._attach_tracks(frame, detections)
        for event in crossings:
            if event['class_id'] != 2:
                continue
            key = (event['camera_id'], event['track_id'])
            canonical = self.aliases.get(key)
            if canonical is not None and self.tracks[canonical].event is None:
                self.tracks[canonical].event = event
        for det in detections:
            key = (frame.camera_id, det.track_id)
            if key in self.closed:
                self.closed[key] = frame.ts
                continue
            state = self.tracks[self.aliases[key]]
            state.seen = frame.ts
            state.bbox = tuple(det.bbox)
            self._sample(frame, det, state)

        finished = []
        for key, state in list(self.tracks.items()):
            if key[0] != frame.camera_id:
                continue
            timeout = self.exit_delay if state.event is not None else self.stale
            if frame.ts - state.seen >= timeout:
                passage = self._retire(key, frame.ts)
                if passage is not None:
                    finished.append(passage)
        return finished
