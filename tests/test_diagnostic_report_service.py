from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from PIL import Image

from plakino_ui.models.plate_record import PlateRecord
from plakino_ui.services.auth_service import AuthService
from plakino_ui.services.diagnostic_report_service import DiagnosticReportService, ArchiveImages, decision
from plakino_ui.services.report_service import record_from_row
from plakino_ui.services.plate_service import PlateService


class DiagnosticReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'archive' / 'trace'
        self.archive.mkdir(parents=True)
        Image.new('RGB', (78, 36), '#888888').save(self.archive / 'raw.png')
        self.auth = AuthService()
        self.auth.current_role = 'superadmin'
        self.service = DiagnosticReportService(self.auth, self.archive.parent, self.root/'documents')
        self.record = PlateRecord('نامطمئن', '2026-11-17', '13:14:15', 'gate', event_id=7,
                                  recognition_status='uncertain')
        self.manifest = {'database_event_id': 7, 'event': {'camera_id': 'gate', 'direction': 'entry', 'ts': 2},
            'created_at': '2026-11-17T10:00:00+00:00', 'crossing': {'image': 'raw.png', 'bbox': [1,2,70,32]},
            'samples': [{'frame_idx': 1, 'ts': 1.5, 'vehicle': 'raw.png', 'raw': 'raw.png',
                'reason': 'geometry_unavailable', 'ocr_sources': ['raw'], 'retained_for_recognition': True}],
            'ocr_inputs': [{'frame_idx': 1, 'source': 'raw', 'image': 'raw.png',
                            'text': '12ب34567', 'confidence': .93, 'valid': True}],
            'omitted_samples': 3, 'dropped_pending': 2, 'omitted_images': 0}
        self.save()

    def save(self):
        (self.archive/'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def test_only_owner_can_prepare_even_when_service_called_directly(self):
        for role in ('', 'guard', 'admin'):
            self.auth.current_role = role
            with patch.object(self.service, '_roots') as roots:
                with self.assertRaises(PermissionError):
                    self.service.prepare(self.record)
                roots.assert_not_called()
        self.assertFalse(self.service.output_root.exists())

    def test_document_has_real_event_time_images_decisions_and_missing_evidence(self):
        path = self.service.prepare(self.record)
        content = path.read_text()
        for text in ('13:14:15', '13:30:00', 'data:image/png;base64,', '78 × 36',
                     '12ب34567', 'حداقل دو رأی', 'نسخهٔ مدل', 'ثبت نشده', 'فریم 1'):
            self.assertIn(text, content)
        self.assertNotIn('http://', content)
        self.assertNotIn('https://', content)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads((self.archive/'manifest.json').read_text()), self.manifest)

    def test_record_identity_and_eligibility_prevent_wrong_archive(self):
        for record in (replace(self.record, recognition_status='read'), replace(self.record, class_id=0),
                       replace(self.record, event_id=None)):
            with self.assertRaises(ValueError):
                self.service.prepare(record)
        for record in (replace(self.record, event_id=8), replace(self.record, camera='other'),
                       replace(self.record, direction='exit')):
            with self.assertRaises(FileNotFoundError):
                self.service.prepare(record)

    def test_paths_and_html_cannot_read_external_files_or_execute_scripts(self):
        outside = self.root/'private.png'
        Image.new('RGB', (1,1), '#ff0000').save(outside)
        (self.archive/'symlink.png').symlink_to(outside)
        images = ArchiveImages(self.archive)
        for name in (str(outside), '../../private.png', 'symlink.png', 'https://example.com/a.png'):
            self.assertIsNone(images.read(name))
        self.manifest['ocr_inputs'][0]['text'] = '<script>alert(1)</script>'
        self.save()
        content = self.service.prepare(self.record).read_text()
        self.assertNotIn('<script>', content)
        self.assertIn('&lt;script&gt;', content)

    def test_logout_during_generation_prevents_document_publication(self):
        def render(*args):
            self.auth.logout()
            return 'private document'
        with patch('plakino_ui.services.diagnostic_report_service.render_report', side_effect=render):
            with self.assertRaises(PermissionError):
                self.service.prepare(self.record)
        self.assertFalse(self.service.output_root.exists())

    def test_duplicate_archive_is_not_silently_chosen(self):
        second = self.archive.parent/'duplicate'
        second.mkdir()
        (second/'manifest.json').write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, 'بیش از یک'):
            self.service.prepare(self.record)

    def test_decision_distinguishes_no_ocr_invalid_single_and_tie(self):
        self.assertIn('هیچ خوانش OCR', decision([])[0])
        self.assertIn('هیچ خوانشی', decision([{'text':'123', 'valid':False, 'confidence':.99}])[0])
        a = {'text':'12ب34567', 'valid':True, 'confidence':.9}
        b = dict(a, text='12ب34568')
        self.assertIn('حداقل دو', decision([a, b])[0])
        self.assertIn('برابر', decision([a, a, b, b])[0])

    def test_dashboard_and_reports_preserve_event_id_status_and_tehran_time(self):
        row = (None, datetime(2026,11,17,10,tzinfo=timezone.utc), 'gate', 'entry', 2, None, 'uncertain', 'unknown', 7)
        report = record_from_row(row)
        connection = MagicMock()
        connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [row]
        with patch('plakino_ui.services.plate_service.ensure_schema'), patch('plakino_ui.services.plate_service.MOCK_DATA_ENABLED', False):
            recent = PlateService(lambda: connection).get_recent_records()[0]
        self.assertEqual(report, recent)
        self.assertEqual((recent.event_id, recent.recognition_status, recent.time), (7, 'uncertain', '13:30:00'))
