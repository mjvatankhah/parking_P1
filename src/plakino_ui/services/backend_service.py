"""One bounded background status poll for all UI pages; never owns backend lifetime."""
import logging
from threading import Thread

from kivy.clock import Clock
from computer_vision_v2.runtime.control import BackendClient
from computer_vision_v2.runtime.health import source_key
from plakino_ui.models.camera import STATUS_ONLINE, STATUS_OFFLINE

logger = logging.getLogger(__name__)


class BackendMonitor:
    def __init__(self, cameras, callback, client=None):
        self.cameras, self.callback = cameras, callback
        self.client = client or BackendClient()
        self.snapshot = dict(state='unavailable', cameras=[], error=None)
        self.busy = False
        self._in_flight = False
        self._pending_command = None
        self._poll = None
        self._generation = 0

    def start(self):
        if self._poll is None:
            self.poll()
            self._poll = Clock.schedule_interval(self.poll, 1)

    def stop(self):
        # Closing a window cancels monitoring only, never sends backend.stop().
        self._generation += 1
        self.busy = False
        self._in_flight = False
        self._pending_command = None
        if self._poll is not None:
            self._poll.cancel()
            self._poll = None

    def poll(self, *_):
        self._request('status')

    def command(self, action):
        if action not in ('start', 'stop') or self.busy:
            return False
        self.busy = True
        self.snapshot = self.snapshot | {'state': 'starting' if action == 'start' else 'stopping'}
        self.callback(self.snapshot, True)
        if self._in_flight:
            # Keep a user command behind the bounded status request, never drop it.
            self._pending_command = action
        else:
            self._request(action)
        return True

    def _request(self, action):
        if self._in_flight:
            return
        self._in_flight = True
        generation = self._generation

        def work():
            try:
                result = getattr(self.client, action)()
            except Exception:
                logger.exception('Backend control request failed', extra={'event': 'backend_control_failed'})
                result = dict(state='unavailable', error='control_failed', cameras=[])
            Clock.schedule_once(lambda _: self._apply(generation, result), 0)
        Thread(target=work, name='backend-status', daemon=True).start()

    def _apply(self, generation, result):
        if generation != self._generation:
            return
        self._in_flight = False
        if self._pending_command is not None:
            action, self._pending_command = self._pending_command, None
            # The poll predates the click: do not flash its old state in the UI.
            self._request(action)
            return
        self.busy = False
        self.snapshot = result
        reported = {camera['id']: camera for camera in result.get('cameras', [])}
        for camera in self.cameras.get_cameras():
            current = reported.get(str(camera.id), {})
            live = (result['state'] in ('running', 'error') and
                    current.get('source_key') == source_key(camera.source) and
                    current.get('state') in ('processing', 'stalled', 'waiting') and
                    current.get('received_age') is not None and current['received_age'] <= 10)
            self.cameras.set_status(camera.id, STATUS_ONLINE if live else STATUS_OFFLINE)
        self.callback(result, False)
