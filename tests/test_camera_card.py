"""UI regression tests; run with a working Kivy/OpenGL display."""
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np
from kivy.clock import Clock

from computer_vision_v2.preview import PreviewPublisher
from reno.models.camera import Camera
from reno.ui.theme import register_app_font
from reno.ui.components.camera_card import CameraCard
from computer_vision_v2.tracking.frame_info import TrackedFrame


class CameraCardTests(unittest.TestCase):
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
