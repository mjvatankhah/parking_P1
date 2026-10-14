"""Live detection follows camera edits without keeping an old preview alive."""

import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from reno.main import RenoApp
from reno.services.camera_service import CameraService
from reno.ui.components.camera_card import CameraCard
from reno.ui.live_detection import LiveDetectionScreen
from reno.ui.theme import register_app_font


class LiveDetectionTests(unittest.TestCase):
    def test_camera_source_edit_replaces_active_annotated_preview(self):
        register_app_font()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cameras.json'

            def write(source):
                path.write_text(json.dumps({'cameras': [
                    {'id': 'cam2', 'type': 'video', 'source': source},
                ]}), encoding='utf-8')

            write('old.mp4')
            with patch('reno.services.camera_service.os.path.join',
                       return_value=str(path)):
                service = CameraService()
            with patch('reno.main.camera_service', service), \
                 patch('reno.ui.live_detection.camera_service', service), \
                 patch.object(CameraCard, 'ensure_stream_started') as start, \
                 patch.object(CameraCard, 'stop_stream') as stop:
                screen = LiveDetectionScreen(name='live_detection')
                try:
                    screen.on_enter()
                    old_card = screen._cards['cam2']
                    old_path = old_card._preview_path
                    self.assertEqual(start.call_count, 1)

                    write('new.mp4')
                    RenoApp._refresh_camera_config(None)
                    new_card = screen._cards['cam2']
                    self.assertIsNot(new_card, old_card)
                    self.assertNotEqual(new_card._preview_path, old_path)
                    self.assertEqual(stop.call_count, 1)
                    self.assertEqual(start.call_count, 2)

                    RenoApp._refresh_camera_config(None)
                    self.assertIs(screen._cards['cam2'], new_card)
                    self.assertEqual(start.call_count, 2)
                finally:
                    screen.on_leave()
                    service.unsubscribe(screen._on_cameras_changed)

    def test_app_starts_and_cancels_config_poll(self):
        app = SimpleNamespace(_refresh_camera_config=Mock(), _camera_config_poll=None,
                              screen_manager=Mock())
        with patch('reno.main.Clock.schedule_interval') as schedule:
            RenoApp.on_start(app)
            app._refresh_camera_config.assert_called_once_with()
            schedule.assert_called_once_with(app._refresh_camera_config, 1)
            poll = app._camera_config_poll
            RenoApp.on_stop(app)
            poll.cancel.assert_called_once_with()
            self.assertIsNone(app._camera_config_poll)


if __name__ == '__main__':
    unittest.main()
