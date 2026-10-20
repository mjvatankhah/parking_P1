"""UI regression tests; run with a working Kivy/OpenGL display."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from kivy.clock import Clock

from computer_vision_v2.preview import PreviewPublisher
from reno.models.camera import Camera
from reno.ui.theme import register_app_font
from reno.ui.components.camera_card import CameraCard
from computer_vision_v2.tracking.frame_info import TrackedFrame


class CameraCardTests(unittest.TestCase):
    def test_live_page_subscription_displays_then_stops_and_resumes_preview(self):
        from kivy.uix.screenmanager import Screen, ScreenManager
        from reno.main import InstantTransition
        from reno.ui.live_detection import LiveDetectionScreen
        register_app_font()
        camera = Camera(id='preview-lifecycle', source='unused')
        frame = TrackedFrame(camera.id, 1, 0,
                             np.full((120, 220, 3), 128, dtype=np.uint8), [])
        def pump_until(condition, timeout=3):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                Clock.tick()
                if condition():
                    return True
                time.sleep(.01)
            return False
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'preview.jpg'
            with patch('computer_vision_v2.preview.preview_path', return_value=path), \
                 patch('reno.ui.components.camera_card.preview_path', return_value=path), \
                 patch('reno.ui.live_detection.camera_service.get_cameras', return_value=[camera]), \
                 patch('reno.ui.live_detection.camera_service.subscribe'):
                publisher = PreviewPublisher([{'id': camera.id, 'source': camera.source}])
                screen = LiveDetectionScreen(name='live')
            manager = ScreenManager(transition=InstantTransition())
            manager.add_widget(Screen(name='other'))
            manager.add_widget(screen)
            card = screen._cards[camera.id]
            publisher.start()
            try:
                publisher.publish(frame)
                manager.current = 'live'
                self.assertTrue(pump_until(lambda: card._video_surface.has_texture))
                self.assertEqual(card._state, 'online')
                manager.current = 'other'
                self.assertIsNone(card._poll_event)
                self.assertFalse(card._preview_subscription.path.exists())
                self.assertTrue(pump_until(lambda: not publisher._active))
                version = path.stat().st_mtime_ns
                publisher.publish(frame)
                manager.current = 'live'
                self.assertTrue(pump_until(lambda: path.stat().st_mtime_ns != version))
                self.assertTrue(pump_until(lambda: card._state == 'online'))
            finally:
                screen.on_leave()
                publisher.stop()

    def test_preview_stays_inside_moved_and_resized_tile(self):
        register_app_font()
        card = CameraCard(Camera(id="layout-test"), size_hint=(None, None))
        frame = TrackedFrame("layout-test", 1, 0,
                             np.full((120, 220, 3), 128, dtype=np.uint8), [])
        with tempfile.TemporaryDirectory() as directory:
            card._preview_path = Path(directory) / "preview.jpg"
            PreviewPublisher._write(card._preview_path, frame, time.time())
            card._update_frame(0)
            self.assertEqual(card._state, "online")
            for position, size in [((150, 350), (600, 320)), ((40, 100), (420, 280))]:
                card.pos, card.size = position, size
                for _ in range(5):
                    Clock.tick()
                surface = card._video_surface
                self.assertEqual(surface.pos, surface.parent.pos)
                self.assertEqual(surface.size, surface.parent.size)
                self.assertTrue(surface.has_texture)
                self.assertEqual(surface.opacity, 1)
                x, y = surface._frame_rect.pos
                width, height = surface._frame_rect.size
                self.assertGreaterEqual(x, surface.x)
                self.assertGreaterEqual(y, surface.y)
                self.assertLessEqual(x + width, surface.right + 0.01)
                self.assertLessEqual(y + height, surface.top + 0.01)
        card.stop_stream()


if __name__ == "__main__":
    unittest.main()
