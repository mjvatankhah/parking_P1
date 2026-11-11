import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.scrollview import ScrollView
from kivy.uix.boxlayout import BoxLayout

from reno.ui.dashboard import DashboardScreen
from reno.ui import theme
from reno.models.plate_record import PlateRecord
from reno.services.camera_service import camera_service
from reno.services.dashboard_service import DashboardStatistics


def layout():
    for _ in range(6):
        Clock.tick()
        Clock.tick_draw()


class RecordScrollTests(unittest.TestCase):
    @staticmethod
    def build_records(screen):
        screen._record_holder = BoxLayout(orientation='vertical')
        screen.add_widget(screen._record_holder)
        for name in ('_chart', '_chart_status', '_record_status', '_data_status',
                     '_today', '_inside', '_guests', '_blocked', '_breakdown'):
            setattr(screen, name, Mock())

    def setUp(self):
        theme.register_app_font()
        with patch.object(camera_service, 'get_cameras', return_value=[]), \
                patch.object(camera_service, 'subscribe'), \
                patch.object(camera_service, 'subscribe_status'), \
                patch.object(DashboardScreen, '_build', self.build_records):
            self.screen = DashboardScreen(size=Window.size)
        Window.add_widget(self.screen)
        self.screen._active = True
        self.records = [PlateRecord(str(i), '2026-10-02', '12:00:00', 'cam')
                        for i in range(20)]
        self.stats = DashboardStatistics(20, 20, 0, 0, 0)
        self.refresh(self.records)
        self.scroll = next(w for w in self.screen._record_holder.children if isinstance(w, ScrollView))
        self.scroll.scroll_y = .4
        self.scroll.scroll_x = .3
        layout()

    def tearDown(self):
        self.screen.on_leave()
        Window.remove_widget(self.screen)

    def refresh(self, records, stats=True):
        self.screen._apply(0, self.stats if stats else None, records, [], 0)
        for _ in range(30):
            if self.screen._row_work._event is None:
                break
            Clock.tick()
        self.assertIsNone(self.screen._row_work._event)
        layout()

    def test_periodic_refresh_preserves_scroll_and_rows_for_unchanged_records(self):
        rows = list(self.scroll.children[0].children)
        self.refresh([replace(record) for record in self.records])
        self.assertIn(self.scroll, self.screen._record_holder.children)
        self.assertAlmostEqual(self.scroll.scroll_y, .4)
        self.assertAlmostEqual(self.scroll.scroll_x, .3)
        self.assertEqual(self.scroll.children[0].children, rows)

    def test_new_record_keeps_existing_visible_row_at_same_position(self):
        rows = self.scroll.children[0]
        anchor = rows.children[10]
        before = anchor.to_window(*anchor.pos)[1]
        newest = PlateRecord('new', '2026-10-02', '12:01:00', 'cam')
        self.refresh([newest] + self.records[:-1])
        self.assertIn(self.scroll, self.screen._record_holder.children)
        self.assertIn(anchor, rows.children)
        self.assertAlmostEqual(anchor.to_window(*anchor.pos)[1], before, delta=1)

    def test_transient_database_error_keeps_scrolled_records(self):
        self.refresh(None, stats=False)
        self.assertIn(self.scroll, self.screen._record_holder.children)
        self.assertAlmostEqual(self.scroll.scroll_y, .4)

    def test_statistics_failure_does_not_hide_successfully_received_events(self):
        newest = PlateRecord('12ب34567', '2026-11-06', '12:01:00', 'cam')
        self.screen._apply(0, None, [newest], [], 0, errors=('statistics',))
        layout()
        self.assertEqual(len(self.screen._record_rows.children), 2)
        self.assertEqual(self.screen._record_rows.children[0].record, newest)
        self.screen._record_status.set_text.assert_called_with('۱ تردد')

    def test_growing_list_keeps_visible_row_at_same_position(self):
        rows = self.scroll.children[0]
        anchor = rows.children[10]
        before = anchor.to_window(*anchor.pos)[1]
        self.refresh([PlateRecord('new', '2026-10-02', '12:01:00', 'cam')] + self.records)
        self.assertAlmostEqual(anchor.to_window(*anchor.pos)[1], before, delta=1)

    def test_at_top_new_records_remain_visible(self):
        self.scroll.scroll_y = 1
        layout()
        self.refresh([PlateRecord('new', '2026-10-02', '12:01:00', 'cam')] + self.records)
        self.assertAlmostEqual(self.scroll.scroll_y, 1)

    def test_empty_results_then_records_recover(self):
        self.refresh([])
        self.refresh(self.records)
        self.assertIsNotNone(self.screen._record_scroll)
        self.assertEqual(len(self.screen._record_rows.children), 21)

    def test_refreshes_during_vehicle_row_build_do_not_keep_table_empty(self):
        self.refresh([])
        records = [PlateRecord(str(i), '2026-11-07', '12:00:00', 'cam')
                   for i in range(50)]
        self.screen._set_records(records)
        for frame in range(60):
            if frame % 5 == 0:
                self.screen._set_records([replace(record) for record in records])
            Clock.tick()
        self.assertEqual(len(self.screen._record_rows.children), 51)
        self.assertIsNone(self.screen._row_work._event)

    def test_first_vehicle_is_visible_before_the_full_batch_finishes(self):
        self.refresh([])
        self.screen._set_records(self.records)
        Clock.tick()
        self.assertEqual(len(self.screen._record_rows.children), 2)
        self.assertEqual(self.screen._record_rows.children[0].record, self.records[0])
        self.assertIsNotNone(self.screen._row_work._event)

    def test_changed_snapshots_are_coalesced_without_losing_latest_vehicle(self):
        self.refresh([])
        self.screen._set_records(self.records)
        for frame in range(25):
            latest = [replace(self.records[0], plate=f'new-{frame}')] + self.records[1:]
            self.screen._set_records(latest)
            Clock.tick()
        for _ in range(30):
            Clock.tick()
        displayed = [row.record for row in reversed(self.screen._record_rows.children)
                     if hasattr(row, 'record')]
        self.assertEqual(displayed, latest)
        self.assertIsNone(self.screen._row_work._event)
        self.assertIsNone(self.screen._queued_records)

    def test_person_selection_cancels_unfinished_vehicle_batch_and_queued_refresh(self):
        self.refresh([])
        self.screen._set_records(self.records)
        Clock.tick()
        self.screen._set_records([replace(self.records[0], plate='new')] + self.records[1:])
        self.screen._search = Mock()
        self.screen._record_kind = Mock(text=theme.rtl('انسان'))
        with patch.object(self.screen, '_filters_changed'):
            self.screen._record_kind_changed()
        person = PlateRecord('', '2026-11-07', '12:00:00', 'cam', class_id=0)
        self.screen._set_records([person])
        layout()
        self.assertEqual(len(self.screen._record_rows.children), 2)
        self.assertEqual(self.screen._record_rows.children[0].record, person)
        self.assertIsNone(self.screen._queued_records)

    def test_leaving_mid_build_keeps_visible_rows_and_returning_finishes_list(self):
        self.refresh([])
        self.screen._set_records(self.records)
        for _ in range(3):
            Clock.tick()
        first_row = list(reversed(self.screen._record_rows.children))[1]
        self.screen._set_records([replace(self.records[0], plate='queued')] + self.records[1:])
        self.screen.on_leave()
        layout()
        self.assertIsNone(self.screen._queued_records)
        self.assertIsNone(self.screen._building_record_keys)
        self.screen._active = True
        self.refresh(self.records)
        displayed = list(reversed(self.screen._record_rows.children))[1:]
        self.assertIs(displayed[0], first_row)
        self.assertEqual([row.record for row in displayed], self.records)
