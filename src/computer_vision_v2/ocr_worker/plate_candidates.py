"""Keep one crossing open while its vehicle remains visible in the ROI."""
from dataclasses import dataclass, field
import logging
import math
from collections import deque
import threading

import cv2
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
class VehicleSample:
    image: object
    ts: float
    frame_idx: int


class CandidateBuffer(list):
    """Unique view of independent quality and recent candidate reserves."""

    def __init__(self):
        super().__init__()
        self.best = []
        self.recent = []

    def groups(self):
        return {'quality': [c.frame_idx for c in self.best],
                'recent': [c.frame_idx for c in self.recent]}


class PassageCandidates(list):
    """Preserve buffer membership when raw/geometry evidence is merged."""

    def __init__(self, candidates, selection_groups):
        super().__init__(candidates)
        self.selection_groups = selection_groups


@dataclass
class TrackEvidence:
    seen: float
    bbox: tuple
    aliases: set = field(default_factory=set)
    event: dict | None = None
    sampled: float = -math.inf
    sampled_predicted: bool = False
    candidates: CandidateBuffer = field(default_factory=CandidateBuffer)
    fallback: Candidate | None = None
    raw_candidates: CandidateBuffer = field(default_factory=CandidateBuffer)
    pending: list = field(default_factory=list)
    in_flight: bool = False
    retiring: bool = False


@dataclass
class CompletedPassage:
    event: dict
    candidates: list


class PlateCandidates:
    def __init__(self, reader, interval=0.1, capacity=6, near=0.09, stale=5.0,
                 exit_delay=0.75, reid_gap=0.5, reid_iou=0.35,
                 deferred=False, vehicle_margin=0.2, sample_capacity=30):
        if (not all(math.isfinite(v) for v in (interval, near, stale, exit_delay, reid_gap, reid_iou))
                or interval <= 0 or near < 0 or stale <= 0 or exit_delay <= 0
                or reid_gap <= 0 or reid_gap > exit_delay or not 0 < reid_iou <= 1
                or isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1):
            raise ValueError('Invalid candidate buffer limits')
        if (not math.isfinite(vehicle_margin) or not 0 <= vehicle_margin <= .3
                or isinstance(sample_capacity, bool) or not isinstance(sample_capacity, int)
                or sample_capacity < 2):
            raise ValueError('Invalid raw sample limits')
        self.deferred, self.vehicle_margin = deferred, vehicle_margin
        self.sample_capacity = sample_capacity
        self.pending_bytes = 0
        self.dropped_samples = 0
        self._lock = threading.RLock()
        self._wake = threading.Condition(self._lock)
        self._work_order = deque()
        self.reader = reader
        self.interval, self.capacity, self.near, self.stale = interval, capacity, near, stale
        # Split the default six slots into three quality and three recent.
        self.recent_capacity = capacity // 2
        self.quality_capacity = capacity - self.recent_capacity
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
        crops = list(state.candidates)
        seen = {c.frame_idx for c in crops}
        crops.extend(c for c in state.raw_candidates if c.frame_idx not in seen)
        if not crops and state.fallback is not None:
            crops.append(state.fallback)
        if state.candidates or state.raw_candidates:
            crops = PassageCandidates(crops, {
                'geometry': state.candidates.groups(),
                'raw': state.raw_candidates.groups(),
            })
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
        mx, my = round((x2-x1)*self.vehicle_margin), round((y2-y1)*self.vehicle_margin)
        expanded = (max(0,x1-mx), max(0,y1-my), min(w,x2+mx), min(h,y2+my))
        # Do not expand into a neighbouring car. Existing overlap stays unchanged.
        if any(other.class_id == 2 and other.track_id != det.track_id
               and self._iou(expanded, other.bbox) > 0
               for other in frame.detections):
            expanded = (max(0,x1), max(0,y1), min(w,x2), min(h,y2))
        a,b,c,d = expanded
        vehicle = frame.image[b:d, a:c]
        if not vehicle.size:
            return
        sample = VehicleSample(vehicle.copy(), frame.ts, frame.frame_idx)
        if not self.deferred:
            self._store_candidate(state, self._detect_sample(sample))
            return
        state.pending.append(sample)
        self.pending_bytes += sample.image.nbytes
        key = self.aliases[(frame.camera_id, det.track_id)]
        if key not in self._work_order:
            self._work_order.append(key)
        while len(state.pending) > self.sample_capacity:
            self._evict_sample(state)
        self._wake.notify_all()

    def _evict_sample(self, state):
        # Keep the first and newest samples where possible; remove the most
        # temporally redundant interior sample, not simply the oldest frame.
        if len(state.pending) > 2:
            index = min(range(1,len(state.pending)-1),
                        key=lambda i: state.pending[i+1].ts-state.pending[i-1].ts)
        else:
            index = 0
        self.pending_bytes -= state.pending.pop(index).image.nbytes
        self.dropped_samples += 1

    def _detect_sample(self, sample):
        try:
            detection = self.reader.detect_plate(sample.image)
        except Exception:
            logger.exception('Plate detection failed at frame %s', sample.frame_idx)
            return None
        if detection is None:
            return None
        crop, confidence, context = detection
        ph, pw = crop.shape[:2]
        if ph < 8 or pw < 30:
            return None
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        sharp = float(cv2.Laplacian(gray, cv2.CV_32F).var())
        quality = (0.5 * confidence + 0.2 * min(ph / 32, 1)
                   + 0.2 * min(sharp / 500, 1)
                   + 0.1 * min(float(gray.std()) / 40, 1))
        candidate = Candidate(crop.copy(), sample.ts, sample.frame_idx, confidence, quality, context)
        if 1.15 <= pw / ph <= 8:
            try:
                candidate.prepared = prepare_plate(context if context is not None else crop)
            except Exception:
                logger.exception('Plate geometry failed at frame %s', sample.frame_idx)
        return candidate

    def _keep(self, candidates, candidate):
        # Quality reserve keeps the existing scoring and near-time comparison.
        best = candidates.best
        nearby = [c for c in best if abs(c.ts-candidate.ts) < self.near]
        blocked = nearby and max(c.quality for c in nearby) >= candidate.quality
        if not blocked:
            best[:] = [c for c in best if c not in nearby and c.frame_idx != candidate.frame_idx]
            best.append(candidate)
            best.sort(key=lambda c: c.quality, reverse=True)
            del best[self.quality_capacity:]

        # Recent reserve never competes on quality. Among near-time samples,
        # retain the newest; overflow removes the oldest retained timestamp.
        recent = candidates.recent
        if self.recent_capacity:
            spaced = []
            for sample in sorted([*recent, candidate], key=lambda c: c.ts, reverse=True):
                if any(c.frame_idx == sample.frame_idx or abs(c.ts-sample.ts) < self.near
                       for c in spaced):
                    continue
                spaced.append(sample)
                if len(spaced) == self.recent_capacity:
                    break
            recent[:] = sorted(spaced, key=lambda c: c.ts)
        best_frames = {c.frame_idx for c in best}
        candidates[:] = best + [c for c in recent if c.frame_idx not in best_frames]
        return {
            'quality': ('reject_near_quality' if blocked else
                        'keep' if candidate in best else 'reject_capacity_quality'),
            'recent': 'keep' if candidate in recent else 'outside_recent_reserve',
        }

    def _store_candidate(self, state, candidate):
        if candidate is None:
            return
        ph,pw = candidate.crop.shape[:2]
        if 1.15 <= pw / ph <= 8:
            self._keep(state.raw_candidates, candidate)
        if candidate.prepared is None:
            if state.fallback is None or candidate.quality > state.fallback.quality:
                state.fallback = candidate
            return
        self._keep(state.candidates, candidate)

    def process_pending(self, timeout=0.):
        """One detector worker drains samples fairly; observation never waits for inference."""
        with self._wake:
            if not self._work_order:
                self._wake.wait(timeout)
            sample = state = None
            while self._work_order:
                key = self._work_order.popleft()
                state = self.tracks.get(key)
                if state is None or not state.pending:
                    continue
                sample = state.pending.pop(0)
                self.pending_bytes -= sample.image.nbytes
                state.in_flight = True
                if state.pending:
                    self._work_order.append(key)
                break
            if sample is None:
                return self._collect_ready()
        try:
            candidate = self._detect_sample(sample)
        except Exception:
            logger.exception('Sample processing failed at frame %s', sample.frame_idx)
            candidate = None
        with self._wake:
            try:
                self._store_candidate(state, candidate)
            finally:
                state.in_flight = False
                self._wake.notify_all()
            return self._collect_ready()

    def _collect_ready(self):
        completed = []
        for key,state in list(self.tracks.items()):
            if state.retiring and state.event is None:
                self.pending_bytes -= sum(sample.image.nbytes for sample in state.pending)
                state.pending.clear()
            if state.retiring and not state.pending and not state.in_flight:
                passage = self._retire(key, state.seen)
                if passage is not None:
                    completed.append(passage)
        return completed

    def observe(self, frame, crossings=()):
        with self._wake:
            return self._observe(frame, crossings)

    def _observe(self, frame, crossings=()):
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
            state.retiring = False
            state.seen = frame.ts
            state.bbox = tuple(det.bbox)
            self._sample(frame, det, state)

        finished = []
        for key, state in list(self.tracks.items()):
            if key[0] != frame.camera_id:
                continue
            timeout = self.exit_delay if state.event is not None else self.stale
            if frame.ts - state.seen >= timeout:
                state.retiring = True
        finished.extend(self._collect_ready())
        return finished
