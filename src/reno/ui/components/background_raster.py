"""Serialize CPU chart rendering outside Kivy; publish textures on its UI thread."""
from concurrent.futures import ThreadPoolExecutor
import logging
from threading import RLock

from kivy.clock import Clock

# Matplotlib's font/cache state is shared. All rasterizers use this lock, also
# when a synchronous snapshot is requested by visual tests or export tooling.
RASTER_LOCK = RLock()
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix='reno-raster')


def render_locked(render, key):
    with RASTER_LOCK:
        return render(key)


class BackgroundRaster:
    """One in-flight snapshot per widget; intermediate requests are discarded."""

    def __init__(self, render, apply):
        self._render = render
        self._apply = apply
        self._latest = None
        self._running = False

    def request(self, key):
        self._latest = key
        if not self._running:
            self._start(key)

    def _start(self, key):
        self._running = True
        future = _EXECUTOR.submit(render_locked, self._render, key)
        future.add_done_callback(lambda result: Clock.schedule_once(
            lambda _: self._finish(key, result), 0))

    def _finish(self, key, future):
        self._running = False
        try:
            result = future.result()
        except Exception:
            logging.getLogger(__name__).exception('Chart rasterization failed')
        else:
            if key == self._latest:
                self._apply(key, result)
        if key != self._latest:
            self._start(self._latest)
