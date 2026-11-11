"""Recent events must survive unrelated statistics/chart failures and chart filters."""
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch
from reno.ui.dashboard import DashboardScreen
from reno.models.plate_record import PlateRecord


class DashboardLoadingTests(unittest.TestCase):
    def load(self, *, statistics_error=False, chart_error=False):
        screen = SimpleNamespace(_apply=Mock())
        record = PlateRecord('12ب34567', '2026-11-06', '10:00:00', 'gate')
        with patch('reno.ui.dashboard.dashboard_service') as service, \
             patch('reno.ui.dashboard.plate_service') as plates, \
             patch('reno.ui.dashboard.Clock.schedule_once') as schedule:
            plates.get_recent_records.return_value = [record]
            if statistics_error:
                service.get_statistics.side_effect = RuntimeError('statistics unavailable')
            if chart_error:
                service.get_hourly_flow.side_effect = RuntimeError('chart unavailable')
            DashboardScreen._load(screen, 7, 'another-camera', date(2026, 11, 5), '12 ب')
            schedule.call_args.args[0](0)
        return screen._apply, plates.get_recent_records, record

    def test_chart_date_and_camera_do_not_silently_filter_latest_records(self):
        _, recent, _ = self.load()
        recent.assert_called_once_with(limit=50, plate='12 ب', class_id=2)

    def test_statistics_failure_still_delivers_successful_records(self):
        apply, _, record = self.load(statistics_error=True)
        self.assertEqual(apply.call_args.args[2], [record])

    def test_chart_failure_still_delivers_successful_records(self):
        apply, _, record = self.load(chart_error=True)
        self.assertEqual(apply.call_args.args[2], [record])
