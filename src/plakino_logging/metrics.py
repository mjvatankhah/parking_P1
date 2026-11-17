"""Per-stage frame counts; intentional sampling is not called frame loss."""
import logging
import threading
import time

logger = logging.getLogger(__name__)


class FrameMetrics:
    def __init__(self, camera_id, stage, interval=30):
        self.camera_id, self.stage, self.interval = camera_id, stage, interval
        self.started = time.monotonic()
        self.counts = {}
        self.lock = threading.Lock()

    def add(self, **counts):
        with self.lock:
            for name, count in counts.items():
                self.counts[name] = self.counts.get(name, 0) + count
            now = time.monotonic()
            if now - self.started < self.interval:
                return
            summary, self.counts = self.counts, {}
            elapsed, self.started = now - self.started, now
        received = summary.get('received', 0)
        summary['replacement_percent'] = round(100 * summary.get('replaced', 0) / received, 2) if received else None
        summary['window_seconds'] = round(elapsed, 2)
        logger.info('Frame window', extra=dict(event='frame_window', camera_id=self.camera_id,
                                              stage=self.stage, metrics=summary))
