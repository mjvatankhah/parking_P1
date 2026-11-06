"""Dashboard totals count vehicles rather than repeated detections."""
import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch
from reno.models.plate_record import PlateRecord
from reno.services.dashboard_service import DashboardService


class DashboardStatisticsTests(unittest.TestCase):
    def test_occupancy_includes_earlier_entries_and_daily_categories_are_unique(self):
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        records = [
            PlateRecord('12ب34567', yesterday, '10:00:00', 'cam'),
            PlateRecord('22ب34567', today, '09:00:00', 'cam'),
            PlateRecord('22ب34567', today, '10:00:00', 'cam', direction='exit'),
            PlateRecord('32ب34567', today, '11:00:00', 'cam', access_status='blocked'),
            PlateRecord('32ب34567', today, '12:00:00', 'cam', access_status='blocked'),
            PlateRecord('خوانده نشد', today, '13:00:00', 'cam', access_status='unknown'),
        ]
        with patch('reno.services.dashboard_service.MOCK_DATA_ENABLED', True), \
             patch('reno.services.dashboard_service.plate_service') as plates, \
             patch('reno.services.dashboard_service.camera_service.get_cameras', return_value=[]):
            plates._mock_records = records
            stats = DashboardService().get_statistics()
        self.assertEqual(stats.today_total, 5)
        self.assertEqual(stats.inside_vehicles, 2)
        self.assertEqual(stats.guest_vehicles, 1)
        self.assertEqual(stats.blocked_vehicles, 1)

    def test_database_statistics_include_open_sessions_and_daily_access_counts(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [(10, 6, 1, 3, 2), (4,)]
        with patch('reno.services.dashboard_service.MOCK_DATA_ENABLED', False), \
             patch('reno.services.dashboard_service.get_connection', return_value=connection), \
             patch('reno.services.dashboard_service.ensure_schema'), \
             patch('reno.services.dashboard_service.camera_service.get_cameras', return_value=[]):
            stats = DashboardService().get_statistics()
        self.assertEqual((stats.today_total, stats.inside_vehicles, stats.guest_vehicles, stats.blocked_vehicles), (10, 4, 3, 2))
        self.assertIn("WHERE status = 'open'", cursor.execute.call_args.args[0])
