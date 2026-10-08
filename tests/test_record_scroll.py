import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.scrollview import ScrollView
from kivy.uix.boxlayout import BoxLayout

from computer_vision_v2.reno.ui.dashboard import DashboardScreen
from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.models.plate_record import PlateRecord
from computer_vision_v2.reno.services.camera_service import camera_service
from computer_vision_v2.reno.services.dashboard_service import DashboardStatistics


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
                     '_today', '_unique', '_online', '_alerts'):
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
