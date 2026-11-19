"""Actual capture/observation progress, independent of UI and wall clock."""
from collections import deque
import hashlib
import logging
import threading
import time

logger = logging.getLogger(__name__)


def source_key(source):
    return hashlib.sha256(str(source).encode()).hexdigest()


class FrameHealth:
    def __init__(self, cameras, clock=time.monotonic, stale_after=10):
        self.clock = clock
        self.stale_after = stale_after
        self.started = clock()
        self.lock = threading.Lock()
        self.cameras = {str(c['id']): dict(id=str(c['id']), source_key=source_key(c['source']),
            source_type=c['type'], connection='waiting', received=0, processed=0,
            last_received=None, last_processed=None, samples=deque(maxlen=6000),
            reported=None) for c in cameras}

    def connection(self, camera_id, state):
        with self.lock:
            self.cameras[str(camera_id)]['connection'] = state

    def received(self, camera_id):
        with self.lock:
            camera = self.cameras[str(camera_id)]
            camera['received'] += 1
            camera['last_received'] = self.clock()
            camera['connection'] = 'connected'

    def processed(self, camera_id):
        with self.lock:
            camera = self.cameras[str(camera_id)]
            now = self.clock()
            camera['processed'] += 1
            camera['last_processed'] = now
            camera['samples'].append(now)

    def snapshot(self):
        result = []
        with self.lock:
            now = self.clock()
            for camera in self.cameras.values():
                received_age = None if camera['last_received'] is None else now-camera['last_received']
                processed_age = None if camera['last_processed'] is None else now-camera['last_processed']
                connection = camera['connection']
                if connection in ('ended', 'error', 'disconnected'):
                    state = connection
                elif received_age is None:
                    state = 'waiting' if now-self.started < self.stale_after else 'no_frames'
                elif received_age > self.stale_after:
                    state = 'no_frames'
                elif processed_age is None:
                    state = 'waiting' if now-self.started < self.stale_after else 'stalled'
                elif processed_age > self.stale_after:
                    state = 'stalled'
                else:
                    state = 'processing'
                while camera['samples'] and camera['samples'][0] < now-5:
                    camera['samples'].popleft()
                if state != camera['reported']:
                    bad = state in ('error', 'disconnected', 'no_frames', 'stalled')
                    logger.log(logging.ERROR if bad else logging.INFO, 'Camera processing state: %s', state,
                               extra={'event': 'camera_processing_state', 'camera_id': camera['id'], 'status': state})
                    camera['reported'] = state
                result.append({key: camera[key] for key in ('id', 'source_key', 'source_type', 'received', 'processed')} |
                    dict(state=state, received_age=received_age, processed_age=processed_age,
                         fps=round(len(camera['samples']) / max(1, min(5, now-self.started)), 1)))
        return result
