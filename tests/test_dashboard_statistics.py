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
        self.assertEqual(stats.access_counts, (0, 2, 1, 2))
        self.assertEqual(sum(stats.access_counts), stats.today_total)

    def test_database_statistics_include_open_sessions_and_daily_access_counts(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [(10, 6, 1, 3, 2, 3, 4, 2), (4,)]
        with patch('reno.services.dashboard_service.MOCK_DATA_ENABLED', False), \
             patch('reno.services.dashboard_service.get_connection', return_value=connection), \
             patch('reno.services.dashboard_service.ensure_schema'), \
             patch('reno.services.dashboard_service.camera_service.get_cameras', return_value=[]):
            stats = DashboardService().get_statistics()
        self.assertEqual((stats.today_total, stats.inside_vehicles, stats.guest_vehicles, stats.blocked_vehicles), (10, 4, 3, 2))
        self.assertIn("WHERE status = 'open'", cursor.execute.call_args.args[0])
        self.assertEqual(stats.access_counts, (3, 4, 1, 2))

    def test_hourly_flow_zero_fills_and_intersects_date_camera_and_plate_filters(self):
        day = date(2026, 11, 6)
        records = [
            PlateRecord('12ب34567', day.isoformat(), '00:00:00', 'cam'),
            PlateRecord('۱۲ ب ۳۴۵ ۶۷', day.isoformat(), '23:59:59', 'cam', direction='exit'),
            PlateRecord('12ب34567', day.isoformat(), '12:00:00', 'other'),
            PlateRecord('22ب34567', day.isoformat(), '12:00:00', 'cam'),
            PlateRecord('12ب34567', '2026-11-05', '12:00:00', 'cam'),
        ]
        with patch('reno.services.dashboard_service.MOCK_DATA_ENABLED', True), \
             patch('reno.services.dashboard_service.plate_service') as plates:
            plates._mock_records = records
            flow = DashboardService().get_hourly_flow(day, 'cam', '۱۲ ب ۳۴۵ ۶۷')
        self.assertEqual(len(flow), 24)
        self.assertEqual(flow[0], (0, 1, 0))
        self.assertEqual(flow[23], (23, 0, 1))
        self.assertTrue(all(row[1:] == (0, 0) for row in flow[1:23]))

    def test_hourly_database_query_uses_day_boundaries_and_normalized_plate(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [(8, 5, 2), (23, 0, 1)]
        day = date(2026, 11, 6)
        with patch('reno.services.dashboard_service.MOCK_DATA_ENABLED', False), \
             patch('reno.services.dashboard_service.get_connection', return_value=connection):
            flow = DashboardService().get_hourly_flow(day, 'cam', '۱۲ ب ۳۴۵ ۶۷')
        sql, params = cursor.execute.call_args.args
        self.assertIn('EXTRACT(HOUR FROM captured_at)', sql)
        self.assertEqual(params[:3], [day, day + timedelta(days=1), 'cam'])
        self.assertEqual(params[-1], '12ب34567')
        self.assertEqual(flow[8], (8, 5, 2))
        self.assertEqual(flow[23], (23, 0, 1))
        self.assertEqual(flow[0], (0, 0, 0))
