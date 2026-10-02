"""User-facing contracts with the HTML reference and requested desktop behavior."""
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from computer_vision_v2.reno.main import RenoApp
from kivy.clock import Clock
from kivy.core.window import Window
from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.ui.components.icons import _ICON_FILES, APP_ICON
from computer_vision_v2.reno.ui.components.brand import BrandMark
from computer_vision_v2.reno.ui.components.raw_camera_card import RawCameraCard
from computer_vision_v2.reno.ui.components.traffic_record import TrafficRecordRow
from computer_vision_v2.reno.models.plate_record import PlateRecord
from computer_vision_v2.reno.services.dashboard_service import DashboardStatistics, dashboard_service
from computer_vision_v2.reno.services.plate_service import plate_service

APP_PATH = Path(__file__).resolve().parents[1] / 'src/computer_vision_v2/reno'


def layout():
    for _ in range(8):
        Clock.tick()
        Clock.tick_draw()


class ReferenceUIContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = [PlateRecord('۱۲ب۳۴۵۶۷', '2026-10-02', '12:48:32', 'cam-1'),
                       PlateRecord('', '2026-10-02', '12:47:18', 'cam-2', class_id=0, direction='exit')]
        cls.patches = [
            patch.object(dashboard_service, 'get_statistics', return_value=DashboardStatistics(1248, 932, 2, 3, 3)),
            patch.object(dashboard_service, 'get_daily_flow', return_value=[('2026-10-02', 8, 2)]),
            patch.object(plate_service, 'get_recent_records', return_value=cls.records),
        ]
        for p in cls.patches:
            p.start()
        cls.app = RenoApp()
        cls.root = cls.app.build()
        cls.root.size = Window.size
        Window.add_widget(cls.root)
        cls.dashboard = cls.root.get_screen('dashboard')
        layout()

    @classmethod
    def tearDownClass(cls):
        cls.dashboard.on_leave()
        cls.root.get_screen('cameras').on_leave()
        Window.remove_widget(cls.root)
        for p in cls.patches:
            p.stop()

    def test_reference_icons_are_extracted_without_changing_paths(self):
        reference = (APP_PATH / 'dashboard-prototype.html').read_text()
        symbols = dict(re.findall(r'<symbol id="([^"]+)"[^>]*>(.*?)</symbol>', reference))
        for name, body in symbols.items():
            extracted = (APP_PATH / 'assets/icons/reference' / f'{name}.svg').read_text()
            self.assertIn(body, extracted)
            self.assertIn('stroke-width="1.6"', extracted)
        for name in ('car', 'camera', 'shield', 'bell', 'dashboard', 'reports', 'settings', 'search', 'log'):
            self.assertTrue(_ICON_FILES[name].startswith('reference/'))
        self.assertEqual(self.app.icon, APP_ICON)
        for screen_name in ('login', 'dashboard', 'cameras', 'reports', 'camera_settings'):
            marks = [w for w in self.root.get_screen(screen_name).walk(restrict=True) if isinstance(w, BrandMark)]
            self.assertTrue(marks, screen_name)
            self.assertTrue(all(w.source == APP_ICON for w in marks))

    def test_headline_copy_and_active_camera_semantics_match_reference(self):
        self.app._navigate('dashboard')
        layout()
        screen = self.dashboard
        expected = [(screen._today, 'تردد امروز', 'مجموع ورود و خروج'),
                    (screen._unique, 'خودروهای یکتا', 'بر اساس پلاک شناسایی‌شده'),
                    (screen._online, 'دوربین‌های فعال', '۱ دوربین قطع'),
                    (screen._alerts, 'هشدارها', '۲ پلاک ناخوانا · ۱ دوربین قطع')]
        for card, title, subtitle in expected:
            self.assertEqual(card._title_label.text, theme.rtl(title))
            self.assertEqual(card._subtitle_label.text, theme.rtl(subtitle))
        # Let the user-visible counter finish rather than checking its target.
        for _ in range(24):
            Clock.tick()
        self.assertIn('۲ ', screen._online._value_label.text)
        self.assertIn('/ ۳', screen._online._value_label.text)
        self.assertEqual(screen._today._value_label.text, '۱٬۲۴۸')

    def test_reference_layout_and_requested_panel_order_at_desktop_sizes(self):
        screen = self.dashboard
        for size in ((1000, 780), (1440, 1000)):
            self.root.size = size
            layout()
            self.assertLess(screen._shell.sidebar.right, screen._today.x)
            self.assertLess(screen._today.x, screen._unique.x)
            self.assertLess(screen._unique.x, screen._online.x)
            self.assertLess(screen._online.x, screen._alerts.x)
            self.assertLess(screen._chart.right, screen._record_panel.x)
            self.assertGreaterEqual(screen._today.width, 160)
            self.assertLessEqual(screen._alerts.right, screen._shell.frame.right)
            self.assertFalse(any(isinstance(w, RawCameraCard) for w in screen.walk(restrict=True)))
        self.root.size = Window.size
        layout()

    def test_gradient_frame_tracks_full_card_after_layout(self):
        layout()
        for card in (self.dashboard._today, self.dashboard._unique,
                     self.root.get_screen('login')._hero):
            vertices = card._frame.vertices
            self.assertAlmostEqual(min(vertices[::4]), card.x, places=3)
            self.assertAlmostEqual(max(vertices[::4]), card.x+card.width, places=3)
            self.assertAlmostEqual(min(vertices[1::4]), card.y, places=3)
            self.assertAlmostEqual(max(vertices[1::4]), card.y+card.height, places=3)

    def test_recent_rows_expose_object_direction_time_and_original_image(self):
        self.app._navigate('dashboard')
        layout()
        rows = [w for w in self.dashboard._record_holder.walk(restrict=True) if isinstance(w, TrafficRecordRow)]
        self.assertEqual(len(rows), 2)
        human = next(w for w in rows if w.record.class_id == 0)
        self.assertEqual(human._event_label.text, theme.rtl('انسان · خروج'))
        self.assertIs(human.record, self.records[1])
        self.assertEqual(human.image_path, '')
        human.dispatch('on_release')
        self.assertTrue(human.detail_dialog)
        human.detail_dialog.dismiss()

    def test_ticket_button_validation_receipt_and_no_duplicate_submission(self):
        self.app._navigate('dashboard')
        header = self.dashboard._shell.header
        self.assertEqual(header.ticket_button.text, theme.rtl('ثبت تیکت'))
        header.ticket_button.dispatch('on_release')
        dialog = header.ticket_dialog
        try:
            dialog.submit_button.dispatch('on_release')
            self.assertIsNone(dialog.receipt)
            self.assertEqual(dialog.status.text, theme.rtl('موضوع و شرح درخواست را وارد کنید.'))
            dialog.subject.text = 'آزمایش'
            dialog.description.text = 'بررسی ثبت نمایشی'
            dialog.submit_button.dispatch('on_release')
            self.assertRegex(dialog.receipt, r'^DEMO-\d{4}$')
            receipt = dialog.receipt
            self.assertFalse(dialog.submit())
            self.assertEqual(dialog.receipt, receipt)
            self.assertTrue(dialog.submit_button.disabled)
            self.assertIn(receipt, dialog.status.text)
        finally:
            dialog.dismiss()

    def test_fast_login_hover_and_moving_purple_light(self):
        self.app._navigate('logout')
        layout()
        login = self.root.get_screen('login')
        button = login._login_button
        button._track_pointer(Window, button.to_window(*button.center))
        self.assertTrue(button.hovered)
        for _ in range(8):
            Clock.tick()
        self.assertEqual(list(button._animated_color), list(button.bg_color_hover))
        self.assertLessEqual(theme.ANIM_FAST, .08)
        button._track_pointer(Window, (-100, -100))
        self.assertFalse(button.hovered)
        background = login._root.children[-1]
        previous = tuple(background._purple.pos)
        background._tick(3)
        self.assertNotEqual(previous, tuple(background._purple.pos))

    def test_four_destinations_and_logout_work(self):
        expected = ['dashboard', 'cameras', 'reports', 'camera_settings', 'logout']
        self.assertEqual(list(self.dashboard._shell.sidebar._items), expected)
        # Drive the real page navigation without opening installation-specific camera sources.
        with patch.object(RawCameraCard, 'start_stream'):
            for destination in ('reports', 'camera_settings', 'cameras', 'dashboard', 'logout'):
                self.dashboard._shell.sidebar._items[destination].dispatch('on_release')
                self.assertEqual(self.root.current, 'login' if destination == 'logout' else destination)
        self.assertEqual(len(self.root.get_screen('reports')._shell.main.children[0].children), 0)


if __name__ == '__main__':
    unittest.main()
