from datetime import date
import unittest
from unittest.mock import patch
from kivy.clock import Clock
from reno.ui import theme
from reno.ui.reports import ReportsScreen,_COUNTS
from reno.services.report_service import ReportFilter,ReportPage
from reno.models.plate_record import PlateRecord
from reno.ui.components.traffic_record import TrafficRecordRow


class ReportsUITests(unittest.TestCase):
    def test_large_report_yields_between_rows_and_stops_when_leaving(self):
        record = PlateRecord('12ب34567', '2026-11-04', '12:30:00', 'cam')
        with patch('reno.ui.reports.TrafficRecordRow', wraps=TrafficRecordRow) as build:
            self.screen._loaded(0, ReportPage((record,) * 50, 50, 0, 50), '')
            self.assertEqual(build.call_count, 0)
            Clock.tick()
            self.assertEqual(build.call_count, 1)
            self.screen.on_leave()
            Clock.tick()
            self.assertEqual(build.call_count, 1)
            self.assertIsNone(self.screen._row_work._event)

    def finish_rows(self):
        for _ in range(55):
            Clock.tick()
            Clock.tick_draw()
            if self.screen._row_work._event is None:
                return
        self.fail('Report rows did not finish')

    def test_returning_to_unchanged_report_preserves_rows_and_scroll(self):
        record = PlateRecord('12ب34567', '2026-11-04', '12:30:00', 'cam')
        page = ReportPage((record,) * 20, 20, 0, 20)
        self.screen._loaded(0, page, '')
        self.finish_rows()
        scroll = self.screen.table_holder.children[0]
        scroll.scroll_y = .4
        rows = list(scroll.children[0].children)
        self.screen.on_leave()
        with patch('reno.ui.reports.TrafficRecordRow', wraps=TrafficRecordRow) as build:
            self.screen._loaded(self.screen._generation, page, '')
        self.assertEqual(build.call_count, 0)
        self.assertIs(self.screen.table_holder.children[0], scroll)
        self.assertEqual(scroll.children[0].children, rows)
        self.assertAlmostEqual(scroll.scroll_y, .4)

    def test_person_selection_resets_page_and_removes_plate_filter_and_columns(self):
        self.screen._offset = 30
        self.screen._filters = ReportFilter(plate='12ب34567', class_id=2)
        with patch.object(self.screen, '_load') as load:
            self.screen.kind.text = theme.rtl('انسان')
            load.assert_called_once()
        self.assertEqual(self.screen._filters, ReportFilter(class_id=0))
        self.assertEqual(self.screen._offset, 0)
        self.assertTrue(self.screen.plate.disabled)
        person = PlateRecord('', '2026-11-04', '12:30:00', 'cam', class_id=0)
        self.screen._loaded(self.screen._generation, ReportPage((person,), 1, 0, 20), '')
        self.finish_rows()
        row = next(w for w in self.screen.table_holder.walk() if isinstance(w, TrafficRecordRow))
        self.assertIsNone(row._plate.parent)
        self.assertIsNone(row._access_label.parent)

    @classmethod
    def setUpClass(cls):
        theme.register_app_font()

    def setUp(self):
        self.screen=ReportsScreen(name='reports')

    def tearDown(self):
        self.screen.on_leave()

    def test_plate_search_formats_and_displays_groups_left_to_right(self):
        field=self.screen.plate
        for char in '۱۲الف۳۴۵۶۷':
            field.insert_text(char)
            Clock.tick()
        self.assertEqual(field.text,'12 الف 345 67')
        self.assertEqual(field.halign,'left')
        self.assertEqual(field.base_direction,'ltr')
        display,order,_=field._display_line(field.text,4)
        self.assertTrue(display.startswith('12 '))
        self.assertTrue(display.endswith(' 345 67'))
        self.assertEqual(sorted(order),list(range(len(field.text))))
        with patch.object(self.screen,'_load'):
            self.screen._apply()
        self.assertEqual(self.screen._filters.plate,'12 الف 345 67')

    def test_default_twenty_and_filters_are_intersected(self):
        self.assertEqual(self.screen.page_size,20)
        self.screen.plate.text='۱۲ب۳۴۵۶۷'
        self.screen.start.selected=date(2026,11,1)
        self.screen.end.selected=date(2026,11,4)
        self.screen.camera.text='  gate-camera  '
        with patch.object(self.screen,'_load') as load:
            self.screen._apply()
            load.assert_called_once()
        self.assertEqual(self.screen._filters,ReportFilter('۱۲ب۳۴۵۶۷',date(2026,11,1),date(2026,11,4),camera='gate-camera',class_id=2))
        self.screen.start.selected=date(2026,11,5)
        with patch.object(self.screen,'_load') as load:
            self.screen._apply()
            load.assert_not_called()

    def test_all_mode_pages_thirty_and_count_changes_reset_offset(self):
        with patch.object(self.screen,'_load') as load:
            self.screen.count.text=theme.rtl('همه ترددها')
            self.assertEqual(self.screen.page_size,30)
            self.screen._total=65
            self.screen._turn(1)
            self.assertEqual(self.screen._offset,30)
            self.screen._turn(1)
            self.assertEqual(self.screen._offset,60)
            self.screen._turn(1)
            self.assertEqual(self.screen._offset,60)
            self.screen.count.text=theme.rtl('۵۰ تردد')
            self.assertEqual(self.screen.page_size,50)
            self.assertEqual(self.screen._offset,0)

    def test_table_uses_dashboard_rows_and_stale_results_are_ignored(self):
        record=PlateRecord('12ب34567','2026-11-04','12:30:00','cam')
        self.screen._loaded(0,ReportPage((record,)*20,100,0,20),'')
        self.finish_rows()
        self.assertEqual(len([w for w in self.screen.table_holder.walk() if isinstance(w,TrafficRecordRow)]),20)
        self.screen.on_leave()
        self.screen._loaded(0,ReportPage((),0,0,20),'')
        self.assertEqual(self.screen._total,100)

    def test_export_uses_applied_filters_and_does_not_limit_to_page(self):
        self.screen._filters=ReportFilter('12ب34567')
        with patch('reno.ui.reports.Thread') as worker,patch('reno.ui.reports.report_service.export',return_value=85) as export,patch.object(self.screen,'_exported') as done:
            self.screen._export('/tmp/report-test.xlsx')
            worker.call_args.kwargs['target']()
            Clock.tick()
            export.assert_called_once_with(self.screen._filters,'/tmp/report-test.xlsx')
            done.assert_called_once_with('/tmp/report-test.xlsx',85,'')

    def test_calendar_selects_single_day_and_can_clear_date(self):
        from reno.ui.components.jalali_calendar import jalali_text
        picker=self.screen.start
        with patch('reno.ui.components.jalali_date_picker.Popup'):
            picker._open()
            picker._select(date(2026,11,4))
            self.assertEqual(picker.selected,date(2026,11,4))
            self.assertEqual(picker.text,theme.rtl(jalali_text(date(2026,11,4))))
            picker._select(None)
            self.assertIsNone(picker.selected)

    def test_export_destination_requires_explicit_overwrite(self):
        from types import SimpleNamespace
        from pathlib import Path
        import tempfile
        from unittest.mock import Mock
        from reno.ui.components.export_dialog import ExportDialog
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'report.xlsx'
            path.write_bytes(b'old')
            dialog=SimpleNamespace(filename=SimpleNamespace(text='report'),chooser=SimpleNamespace(path=folder),
                                   error=Mock(),save=SimpleNamespace(text=''),_overwrite=None,dismiss=Mock(),on_save=Mock())
            ExportDialog._save(dialog)
            dialog.on_save.assert_not_called()
            self.assertEqual(path.read_bytes(),b'old')
            ExportDialog._save(dialog)
            dialog.on_save.assert_called_once_with(path)
