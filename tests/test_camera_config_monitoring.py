"""Run with a working Kivy/OpenGL display."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from computer_vision_v2.reno.main import RenoApp
from computer_vision_v2.reno.services.camera_service import CameraService
from computer_vision_v2.reno.ui.cameras import CamerasScreen
from computer_vision_v2.reno.ui.theme import register_app_font


class CameraConfigMonitoringTests(unittest.TestCase):
    def test_app_poll_replaces_active_monitoring_stream_after_external_edit(self):
        register_app_font()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cameras.json'

            def write(source):
                path.write_text(json.dumps({'cameras': [
                    {'id': 'cam2', 'type': 'video', 'source': source},
                ]}), encoding='utf-8')

            write('old.mp4')
            with patch('computer_vision_v2.reno.services.camera_service.os.path.join',
                       return_value=str(path)):
                service = CameraService()
            with patch('computer_vision_v2.reno.main.camera_service', service), \
                 patch('computer_vision_v2.reno.ui.cameras.camera_service', service), \
                 patch('computer_vision_v2.reno.ui.components.raw_camera_card.camera_service', service), \
                 patch('computer_vision_v2.reno.ui.components.raw_camera_card.VideoStream',
                       side_effect=lambda *args, **kwargs: Mock()) as streams:
                screen = CamerasScreen(name='cameras')
                try:
                    screen.on_enter()
                    old_card = screen._cards['cam2']
                    old_stream = old_card._stream
                    self.assertEqual(streams.call_args.args[0].source, 'old.mp4')
                    write('new.mp4')
                    RenoApp._refresh_camera_config(None)
                    new_card = screen._cards['cam2']
                    self.assertIsNot(new_card, old_card)
                    old_stream.stop.assert_called_once()
                    self.assertEqual(new_card.camera.source, 'new.mp4')
                    self.assertEqual(streams.call_args.args[0].source, 'new.mp4')
                    new_card._stream.start.assert_called_once()
                    RenoApp._refresh_camera_config(None)
                    self.assertIs(screen._cards['cam2'], new_card)
                    self.assertEqual(streams.call_count, 2)
                finally:
                    screen.on_leave()
                    service.unsubscribe(screen._on_cameras_changed)

    def test_app_starts_and_cancels_config_poll(self):
        app = SimpleNamespace(_refresh_camera_config=Mock(), _camera_config_poll=None,
                              screen_manager=Mock())
        with patch('computer_vision_v2.reno.main.Clock.schedule_interval') as schedule:
            RenoApp.on_start(app)
            app._refresh_camera_config.assert_called_once_with()
            schedule.assert_called_once_with(app._refresh_camera_config, 1)
            poll = app._camera_config_poll
            RenoApp.on_stop(app)
            poll.cancel.assert_called_once_with()
            self.assertIsNone(app._camera_config_poll)


if __name__ == '__main__':
    unittest.main()
