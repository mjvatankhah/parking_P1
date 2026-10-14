import sys
import os
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reno.services import plate_service as module


class PlateServiceTests(unittest.TestCase):
    def setUp(self):
        mock_mode = patch.object(module, 'MOCK_DATA_ENABLED', False)
        mock_mode.start()
        self.addCleanup(mock_mode.stop)
        self.factory = MagicMock()
        self.cursor = self.factory.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        self.service = module.PlateService(connection_factory=self.factory)

    def test_event_rows_map_to_dashboard_records(self):
        self.cursor.fetchall.return_value = [
            ('12ب345', datetime(2026, 9, 14, 13, 4, 5), 'cam2', 'exit', 2, 'captured_plates/test.jpg', 'read'),
            (None, datetime(2026, 9, 14, 12, 1, 2), 'cam1', 'entry', 0, None, 'unread'),
        ]
        records = self.service.get_recent_records(50)
        self.assertEqual(len(records), 2)
        self.assertEqual((records[0].plate, records[0].date, records[0].time,
                          records[0].camera, records[0].direction, records[0].class_id),
                         ('12ب345', '2026-09-14', '13:04:05', 'cam2', 'exit', 2))
        self.assertEqual(records[0].image_path, str(module._PROJECT_ROOT / 'captured_plates/test.jpg'))
        self.assertEqual(records[1].image_path, '')
        self.assertEqual(records[1].plate, 'خوانده نشد')
        self.assertEqual(records[1].class_label(), 'انسان')
        query, params = self.cursor.execute.call_args.args
        self.assertIn('ORDER BY captured_at DESC, id DESC', query)
        self.assertEqual(params, (50,))
        self.factory.return_value.__exit__.assert_called_once()

    def test_no_rows_is_empty(self):
        self.cursor.fetchall.return_value = []
        self.assertEqual(self.service.get_recent_records(), [])

    def test_uncertain_event_has_distinct_label(self):
        self.cursor.fetchall.return_value = [
            (None,datetime(2026,10,13,12),'cam2','exit',2,None,'uncertain')]
        self.assertEqual(self.service.get_recent_records()[0].plate,'نامطمئن')

    @unittest.skipUnless(hasattr(time, 'tzset'), 'Requires system timezone control')
    def test_database_timestamp_is_displayed_in_system_timezone(self):
        self.cursor.fetchall.return_value = [
            (None, datetime(2026, 10, 10, 23, 45, tzinfo=timezone.utc),
             'cam2', 'entry', 0, None, 'unread'),
        ]
        try:
            with patch.dict(os.environ, {'TZ': 'Asia/Tehran'}):
                time.tzset()
                record = self.service.get_recent_records()[0]
                self.assertEqual(record.date, '2026-10-11')
                self.assertEqual(record.time, '03:15:00')
        finally:
            time.tzset()

    def test_database_errors_are_not_reported_as_empty_results(self):
        self.cursor.fetchall.side_effect = RuntimeError('database unavailable')
        with self.assertRaises(RuntimeError):
            self.service.get_recent_records()
        self.factory.return_value.__exit__.assert_called_once()

    def test_nonpositive_limit_does_not_connect(self):
        self.assertEqual(self.service.get_recent_records(0), [])
        self.factory.assert_not_called()

    def test_demo_mode_does_not_connect(self):
        with patch.object(module, 'MOCK_DATA_ENABLED', True):
            service = module.PlateService(connection_factory=self.factory)
            self.assertEqual(len(service.get_recent_records(3)), 3)
        self.factory.assert_not_called()


if __name__ == '__main__':
    unittest.main()
