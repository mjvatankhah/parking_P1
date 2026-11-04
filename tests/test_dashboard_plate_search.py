"""Dashboard plate entry and normalized searching regressions."""
import unittest
from unittest.mock import patch, MagicMock
from datetime import date
from kivy.clock import Clock
from reno.ui import theme
from reno.ui.dashboard import DashboardScreen
from reno.models.plate_record import PlateRecord
from reno.services.plate_service import PlateService
from reno.services.dashboard_service import DashboardService


class DashboardPlateSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        theme.register_app_font()

    def test_dashboard_formats_typed_plate_and_keeps_groups_ltr(self):
        screen = DashboardScreen()
        field = screen._search
        for char in '۱۲الف۳۴۵۶۷':
            field.insert_text(char)
            Clock.tick()
        self.assertEqual(field.text, '12 الف 345 67')
        self.assertEqual(field.halign, 'left')
        self.assertEqual(field.base_direction, 'ltr')
        display, order, _ = field._display_line(field.text, 4)
        self.assertTrue(display.startswith('12 '))
        self.assertTrue(display.endswith(' 345 67'))
        self.assertEqual(sorted(order), list(range(len(field.text))))

    def test_paste_backspace_and_selection_preserve_format(self):
        from reno.ui.components.plate_input import PlateSearchInput
        field = PlateSearchInput()
        field.insert_text('۱۲ الف ۳۴۵ ۶۷')
        self.assertEqual(field.text, '12 الف 345 67')
        field.do_backspace()
        self.assertEqual(field.text, '12 الف 345 6')
        field.do_backspace()
        self.assertEqual(field.text, '12 الف 345')
        field.do_backspace()
        self.assertEqual(field.text, '12 الف 34')
        field.select_all()
        field.insert_text('98ب76543')
        self.assertEqual(field.text, '98 ب 765 43')
        field.insert_text('9')
        self.assertEqual(field.text, '98 ب 765 43')

    def test_database_queries_normalize_both_input_and_stored_plate(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = []
        with patch('reno.services.plate_service.MOCK_DATA_ENABLED', False), \
             patch('reno.services.plate_service.ensure_schema'):
            PlateService(connection_factory=lambda: connection).get_recent_records(plate='۱۲ الف ۳۴۵ ۶۷')
        sql, params = cursor.execute.call_args.args
        self.assertIn('regexp_replace(translate', sql)
        self.assertEqual(params[-2:], ('12الف34567', 50))
        with patch('reno.services.dashboard_service.MOCK_DATA_ENABLED', False), \
             patch('reno.services.dashboard_service.get_connection', return_value=connection):
            DashboardService().get_daily_flow(plate='۱۲ الف ۳۴۵ ۶۷')
        sql, params = cursor.execute.call_args.args
        self.assertIn('regexp_replace(translate', sql)
        self.assertEqual(params[-1], '12الف34567')

    def test_spaced_persian_digits_find_compact_stored_plate(self):
        record = PlateRecord(plate='12الف34567', date=date.today().isoformat(),
                             time='12:00:00', camera='c1', direction='entry')
        service = PlateService()
        service._mock_records = [record]
        with patch('reno.services.plate_service.MOCK_DATA_ENABLED', True):
            self.assertEqual(service.get_recent_records(plate='۱۲ الف ۳۴۵ ۶۷'), [record])
        with patch('reno.services.dashboard_service.MOCK_DATA_ENABLED', True), \
             patch('reno.services.dashboard_service.plate_service', service):
            self.assertEqual(DashboardService().get_daily_flow(plate='۱۲ الف ۳۴۵ ۶۷')[-1][1:], (1, 0))
