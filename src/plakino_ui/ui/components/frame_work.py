"""Bound widget construction so navigation can run between new table rows."""
from kivy.clock import Clock


class FrameWork:
    def __init__(self):
        self._event = None
        self._work = None

    def start(self, work):
        self.cancel()
        self._work = work
        self._event = Clock.schedule_interval(self._step, 0)

    def _step(self, _dt):
        try:
            next(self._work)
        except StopIteration:
            self.cancel()
            return False
        except Exception:
            self.cancel()
            raise

    def cancel(self):
        if self._event is not None:
            self._event.cancel()
            self._event = None
        if self._work is not None:
            self._work.close()
            self._work = None
