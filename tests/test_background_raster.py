"""Slow rasterization must not stall navigation or publish stale chart data."""
import threading
import time
import unittest
from unittest.mock import patch

from kivy.clock import Clock
from kivy.uix.screenmanager import Screen, ScreenManager
from reno.main import InstantTransition
from reno.ui import theme
from reno.ui.components.background_raster import BackgroundRaster
from reno.ui.components.traffic_chart import TrafficChart
from reno.ui.components.traffic_breakdown import StatusRing


def pump_until(condition, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        Clock.tick()
        if condition():
            return True
    return False


class BackgroundRasterTests(unittest.TestCase):
    def test_slow_chart_keeps_navigation_responsive_and_drops_stale_snapshots(self):
        started, release = threading.Event(), threading.Event()
        rendered, applied = [], []
        main_thread = threading.get_ident()

        def render(key):
            self.assertNotEqual(threading.get_ident(), main_thread)
            rendered.append(key)
            if key == 1:
                started.set()
                release.wait(5)
            return key

        def apply(key, result):
            self.assertEqual(threading.get_ident(), main_thread)
            applied.append((key, result))

        worker = BackgroundRaster(render, apply)
        manager = ScreenManager(transition=InstantTransition())
        manager.add_widget(Screen(name='dashboard'))
        manager.add_widget(Screen(name='reports'))
        try:
            worker.request(1)
            self.assertTrue(started.wait(5))
            worker.request(2)
            worker.request(3)
            manager.current = 'reports'
            Clock.tick()
            self.assertEqual(manager.current, 'reports')
            self.assertEqual(applied, [])
            self.assertFalse(release.is_set())
        finally:
            release.set()
        self.assertTrue(pump_until(lambda: bool(applied)))
        self.assertEqual(rendered, [1, 3])
        self.assertEqual(applied, [(3, 3)])

    def test_chart_and_ring_rasterize_off_ui_thread_and_upload_on_ui_thread(self):
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        original = FigureCanvasAgg.draw
        threads = []
        main_thread = threading.get_ident()

        def draw(figure, *args, **kwargs):
            threads.append(threading.get_ident())
            return original(figure, *args, **kwargs)

        theme.register_app_font()
        with patch.object(FigureCanvasAgg, 'draw', draw):
            chart = TrafficChart(period='hourly', size=(400, 200))
            ring = StatusRing()
            chart.set_data([(hour, hour, 23-hour) for hour in range(24)])
            ring.set_data((5, 3, 1))
            try:
                self.assertTrue(pump_until(lambda: chart._render_key == chart._snapshot()
                                           and ring._render_key == (5, 3, 1), timeout=15))
                self.assertTrue(threads)
                self.assertNotIn(main_thread, threads)
                self.assertIsNotNone(chart._image.texture)
                self.assertIsNotNone(ring._image.texture)
            finally:
                chart._render_trigger.cancel()
