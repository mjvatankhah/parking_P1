"""UI controls reflect the backend and closing the UI never requests a stop."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from computer_vision_v2.runtime.health import source_key
from plakino_ui.services.backend_service import BackendMonitor
from plakino_ui.services.auth_service import auth_service
from plakino_ui.ui import theme
from plakino_ui.ui.components.backend_bar import BackendBar
from plakino_ui.models.camera import STATUS_ONLINE, STATUS_OFFLINE


class BackendUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        theme.register_app_font()

    def setUp(self):
        self.client = Mock()
        self.cameras = Mock()
        self.cameras.get_cameras.return_value = [SimpleNamespace(id='cam', source='rtsp://test')]
        self.callback = Mock()
        self.monitor = BackendMonitor(self.cameras, self.callback, self.client)

    def tearDown(self):
        auth_service.logout()

    def test_ui_close_only_cancels_monitoring_and_ignores_late_status(self):
        timer = Mock()
        self.monitor._poll = timer
        self.monitor.stop()
        timer.cancel.assert_called_once()
        self.client.stop.assert_not_called()
        self.monitor._apply(0, dict(state='running', cameras=[]))
        self.callback.assert_not_called()

    def test_camera_badge_uses_backend_capture_and_rejects_old_source(self):
        camera = dict(id='cam', source_key=source_key('rtsp://test'), state='processing', received_age=.2)
        self.monitor._apply(0, dict(state='running', cameras=[camera]))
        self.cameras.set_status.assert_called_with('cam', STATUS_ONLINE)
        camera['source_key'] = source_key('rtsp://old')
        self.monitor._apply(0, dict(state='running', cameras=[camera]))
        self.cameras.set_status.assert_called_with('cam', STATUS_OFFLINE)
        self.monitor._apply(0, dict(state='unavailable', cameras=[]))
        self.cameras.set_status.assert_called_with('cam', STATUS_OFFLINE)

    def test_start_stop_controls_and_persistent_camera_error(self):
        auth_service.current_role = 'guard'
        bar = BackendBar()
        bar.update(dict(state='stopped', cameras=[]))
        self.assertFalse(bar.start_button.disabled)
        self.assertTrue(bar.stop_button.disabled)
        snapshot = dict(state='running', cameras=[dict(id='cam', state='disconnected',
            received=12, processed=10, fps=0, processed_age=11)])
        bar.update(snapshot)
        self.assertTrue(bar.start_button.disabled)
        self.assertFalse(bar.stop_button.disabled)
        self.assertIn('cam', bar.label.text)
        self.assertEqual(tuple(bar.label.color), theme.rgba(theme.COLORS['offline']))
        with patch('plakino_ui.ui.components.backend_bar.App.get_running_app', return_value=SimpleNamespace(backend_monitor=self.monitor)):
            with patch.object(self.monitor, 'command') as command:
                bar.stop_button.dispatch('on_release')
                command.assert_called_once_with('stop')
        bar.update(dict(state='starting', cameras=[]))
        self.assertFalse(bar.stop_button.disabled)  # cancellation during model loading
        auth_service.logout()
        bar.update(snapshot)
        self.assertTrue(bar.stop_button.disabled)

    def test_expired_license_disables_start_but_keeps_activation_available(self):
        auth_service.current_role = 'guard'
        bar = BackendBar()
        bar.update(dict(state='stopped', cameras=[], license=dict(valid=False, code='expired')))
        self.assertTrue(bar.start_button.disabled)
        self.assertFalse(bar.license_button.disabled)
        bar.update(dict(state='stopped', cameras=[], license=dict(valid=True, code='valid')))
        self.assertFalse(bar.start_button.disabled)

    def test_activation_dialog_exports_and_imports_through_backend(self):
        import json
        import tempfile
        from pathlib import Path
        from plakino_ui.ui.components.license_dialog import LicenseDialog
        client = Mock()
        client.license_request.return_value = dict(device_id='a' * 64)
        client.install_license.return_value = dict(valid=True, code='valid')
        with patch.object(LicenseDialog, '_work'):
            popup = LicenseDialog(client=client)
        with tempfile.TemporaryDirectory() as directory:
            popup.chooser.path = directory
            popup._work = lambda operation: operation()
            popup._export()
            path = Path(directory) / ('device-request-' + 'a' * 12 + '.json')
            self.assertEqual(json.loads(path.read_text()), client.license_request.return_value)
            license_path = Path(directory) / 'customer.plakino'
            license_path.write_text('{"payload": {}, "signature": "test"}')
            popup.chooser.selection = [str(license_path)]
            popup._import()
            client.install_license.assert_called_once_with(dict(payload={}, signature='test'))
            client.start.assert_not_called()

    def test_no_overlapping_status_requests(self):
        with patch('plakino_ui.services.backend_service.Thread') as thread:
            self.monitor.poll()
            self.monitor.poll()
            thread.assert_called_once()

    def test_background_poll_keeps_start_available(self):
        auth_service.current_role = 'guard'
        bar = BackendBar()
        self.monitor.snapshot = dict(state='stopped', cameras=[])
        self.monitor.callback = bar.update
        bar.update(self.monitor.snapshot)
        with patch('plakino_ui.services.backend_service.Thread'):
            self.monitor.poll()
        self.assertFalse(bar.start_button.disabled)

    def test_click_during_poll_is_delivered_and_shows_immediate_feedback(self):
        self.monitor.snapshot = dict(state='stopped', cameras=[])
        self.client.status.return_value = dict(state='stopped', cameras=[])
        self.client.start.return_value = dict(state='starting', cameras=[])
        workers, completions = [], []
        with patch('plakino_ui.services.backend_service.Thread') as thread, \
                patch('plakino_ui.services.backend_service.Clock.schedule_once') as schedule:
            thread.side_effect = lambda **kwargs: SimpleNamespace(start=lambda: workers.append(kwargs['target']))
            schedule.side_effect = lambda callback, *_: completions.append(callback)
            self.monitor.poll()
            self.monitor.command('start')
            self.assertEqual(self.monitor.snapshot['state'], 'starting')
            self.assertTrue(self.monitor.busy)
            workers.pop(0)()
            completions.pop(0)(0)
            self.assertEqual(len(workers), 1)
            workers.pop(0)()
            completions.pop(0)(0)
        self.client.start.assert_called_once()
        self.assertFalse(self.monitor.busy)

    def test_status_refresh_preserves_camera_widgets_and_top_close(self):
        bar = BackendBar()
        snapshot = dict(state='running', cameras=[dict(id='cam', state='processing',
            received=12, processed=10, fps=4, processed_age=1)])
        bar.update(snapshot)
        bar._details()
        popup = bar._popup
        try:
            rows = tuple(bar._rows.children)
            bar.update(snapshot, busy=True)
            self.assertEqual(tuple(bar._rows.children), rows)
            bar._details()
            self.assertIs(bar._popup, popup)
            popup.scroll.scroll_y = .4
            updated = snapshot | {'cameras': [snapshot['cameras'][0] | {'processed': 15}]}
            bar.update(updated)
            self.assertEqual(tuple(bar._rows.children), rows)
            self.assertEqual(popup.scroll.scroll_y, .4)
            self.assertIn(theme.fa_number(15), popup._camera_cards['cam'].metrics.text)
            self.assertIsNotNone(popup.close_button)
            popup.close_button.dispatch('on_release')
            self.assertIsNone(bar._popup)
        finally:
            popup.dismiss(animation=False)

    def test_queued_stop_survives_poll_and_duplicate_click(self):
        self.monitor.snapshot = dict(state='running', cameras=[])
        with patch('plakino_ui.services.backend_service.Thread') as thread:
            self.monitor.poll()
            self.assertTrue(self.monitor.command('stop'))
            self.assertFalse(self.monitor.command('stop'))
            self.monitor.poll()
            self.assertEqual(thread.call_count, 1)
            self.assertEqual(self.monitor.snapshot['state'], 'stopping')
            self.monitor._apply(0, dict(state='running', cameras=[]))
            self.assertEqual(thread.call_count, 2)
            self.assertEqual(self.monitor.snapshot['state'], 'stopping')
            self.monitor._apply(0, dict(state='stopped', cameras=[]))
        self.assertFalse(self.monitor.busy)
        self.assertEqual(self.monitor.snapshot['state'], 'stopped')

    def test_closing_monitor_discards_queued_command_and_late_callback(self):
        with patch('plakino_ui.services.backend_service.Thread') as thread:
            self.monitor.poll()
            self.monitor.command('start')
            self.monitor.stop()
            self.callback.reset_mock()
            self.monitor._apply(0, dict(state='stopped', cameras=[]))
            thread.assert_called_once()
        self.assertFalse(self.monitor.busy)
        self.callback.assert_not_called()

    def test_command_failure_releases_buttons_for_retry(self):
        self.client.start.side_effect = RuntimeError('test connection failure')
        workers, completions = [], []
        with patch('plakino_ui.services.backend_service.Thread') as thread, \
                patch('plakino_ui.services.backend_service.Clock.schedule_once') as schedule:
            thread.side_effect = lambda **kwargs: SimpleNamespace(start=lambda: workers.append(kwargs['target']))
            schedule.side_effect = lambda callback, *_: completions.append(callback)
            self.monitor.command('start')
            with self.assertLogs('plakino_ui.services.backend_service', level='ERROR'):
                workers.pop(0)()
            completions.pop(0)(0)
            self.assertFalse(self.monitor.busy)
            self.assertEqual(self.monitor.snapshot['state'], 'unavailable')
            self.assertTrue(self.monitor.command('start'))

    def test_button_text_restores_contrast_after_disabled_state(self):
        auth_service.current_role = 'guard'
        bar = BackendBar()
        bar.update(dict(state='running', cameras=[]))
        bar.update(dict(state='stopped', cameras=[]))
        self.assertEqual(tuple(bar.start_button.color), theme.rgba(theme.COLORS['text_on_primary']))
