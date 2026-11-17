from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from plakino_ui.services.auth_service import auth_service
from plakino_ui.models.plate_record import PlateRecord
from plakino_ui.ui import theme
from plakino_ui.ui.components.traffic_record import TrafficRecordRow
from plakino_ui.ui.components.diagnostic_report_dialog import DiagnosticReportDialog, open_document


class OwnerReportUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        theme.register_app_font()

    def setUp(self):
        self.record = PlateRecord('نامطمئن', '2026-11-17', '13:00:00', 'cam', event_id=7,
                                  recognition_status='uncertain')
        self.addCleanup(auth_service.logout)

    def test_button_only_for_owner_unread_or_uncertain_vehicle(self):
        for role in ('', 'guard', 'admin', 'superadmin'):
            auth_service.current_role = role
            for status in ('read', 'unread', 'uncertain'):
                row = TrafficRecordRow(replace(self.record, recognition_status=status))
                self.assertEqual(row.diagnostic_button is not None, role=='superadmin' and status!='read')
            self.assertIsNone(TrafficRecordRow(replace(self.record, class_id=0)).diagnostic_button)

    def test_reused_row_removes_action_on_logout_and_rechecks_click(self):
        auth_service.current_role = 'superadmin'
        row = TrafficRecordRow(self.record)
        self.assertIsNotNone(row.diagnostic_button)
        auth_service.logout()
        with patch.object(DiagnosticReportDialog, 'open') as opening:
            row._open_diagnostics()
            opening.assert_not_called()
        row.refresh_access()
        self.assertIsNone(row.diagnostic_button)
        auth_service.current_role = 'superadmin'
        row.refresh_access()
        with patch.object(DiagnosticReportDialog, 'open') as opening:
            row.diagnostic_button.dispatch('on_release')
            opening.assert_called_once()
            self.assertEqual(row.diagnostic_dialog.record.event_id, 7)

    def test_stale_callback_after_logout_cannot_open_report(self):
        auth_service.current_role = 'superadmin'
        dialog = DiagnosticReportDialog(self.record)
        auth_service.logout()
        auth_service.current_role = 'superadmin'
        with patch('plakino_ui.ui.components.diagnostic_report_dialog.webbrowser.open') as browser:
            dialog._ready(Path('/tmp/private.html'), '')
            browser.assert_not_called()
        self.assertIsNone(dialog.document)

    def test_missing_report_is_a_clear_message_and_no_browser(self):
        auth_service.current_role = 'superadmin'
        dialog = DiagnosticReportDialog(self.record)
        with patch('plakino_ui.ui.components.diagnostic_report_dialog.webbrowser.open') as browser:
            dialog._ready(None, 'برای این تردد گزارش تشخیصی موجود نیست')
            browser.assert_not_called()
        self.assertTrue(dialog.open_button.disabled)

    def test_ready_opens_local_document_and_dismissal_revokes_callback(self):
        auth_service.current_role = 'superadmin'
        dialog = DiagnosticReportDialog(self.record)
        with patch('plakino_ui.ui.components.diagnostic_report_dialog.platform.release', return_value='Linux'), \
             patch('plakino_ui.ui.components.diagnostic_report_dialog.webbrowser.open', return_value=True) as browser:
            dialog._ready(Path('/tmp/report.html'), '')
            browser.assert_called_once_with('file:///tmp/report.html')
            dialog.on_dismiss()
            dialog._open_document()
            self.assertEqual(browser.call_count, 1)

    def test_wsl_bypasses_linux_opener_that_claims_success(self):
        from types import SimpleNamespace
        with patch('plakino_ui.ui.components.diagnostic_report_dialog.platform.release', return_value='microsoft-standard-WSL2'), \
             patch('plakino_ui.ui.components.diagnostic_report_dialog.webbrowser.open', return_value=True) as linux, \
             patch('plakino_ui.ui.components.diagnostic_report_dialog.shutil.which', side_effect=lambda name: {'wslpath': '/usr/bin/wslpath', 'msedge.exe': '/mnt/c/edge.exe'}.get(name)), \
             patch('plakino_ui.ui.components.diagnostic_report_dialog.subprocess.run', return_value=SimpleNamespace(stdout='C:/reports/report name.html')) as convert, \
             patch('plakino_ui.ui.components.diagnostic_report_dialog.subprocess.Popen') as launch:
            launch.return_value.wait.return_value = 0
            self.assertTrue(open_document(Path('/tmp/report name.html')))
            linux.assert_not_called()
            self.assertEqual(convert.call_args.args[0], ['/usr/bin/wslpath', '-w', '/tmp/report name.html'])
            self.assertEqual(launch.call_args.args[0], ['/mnt/c/edge.exe', 'file:///C:/reports/report%20name.html'])
            self.assertNotIn('shell', launch.call_args.kwargs)

    def test_wsl_browser_failure_is_not_reported_as_success(self):
        from types import SimpleNamespace
        with patch('plakino_ui.ui.components.diagnostic_report_dialog.platform.release', return_value='microsoft-standard-WSL2'), \
             patch('plakino_ui.ui.components.diagnostic_report_dialog.shutil.which', return_value='/mock/tool'), \
             patch('plakino_ui.ui.components.diagnostic_report_dialog.subprocess.run', return_value=SimpleNamespace(stdout='C:/report.html')), \
             patch('plakino_ui.ui.components.diagnostic_report_dialog.subprocess.Popen') as launch:
            launch.return_value.wait.return_value = 1
            self.assertFalse(open_document(Path('/tmp/report.html')))
