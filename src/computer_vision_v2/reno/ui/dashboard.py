"""
ui/dashboard.py

The main Dashboard screen: header, sidebar, three statistic cards, the
recent
records table.

Everything shown here comes from the service layer
(services/dashboard_service.py, services/camera_service.py,
services/plate_service.py) - this file only arranges widgets and
reacts to service updates. No YOLO/RTSP/PostgreSQL code belongs here.
"""

import logging
import threading
from functools import partial

from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.graphics import Color, Rectangle

from computer_vision_v2.reno.ui.theme import SPACING, PAGE_BG_TOP, PAGE_BG_BOTTOM
from computer_vision_v2.reno.ui.components.common import make_gradient_texture
from computer_vision_v2.reno.ui.components.app_header import AppHeader
from computer_vision_v2.reno.ui.components.sidebar import Sidebar
from computer_vision_v2.reno.ui.components.stat_card import (
    StatCard, GRADIENT_TEAL, GRADIENT_BLUE, GRADIENT_ORANGE,
)
from computer_vision_v2.reno.ui.components.recent_records import RecentRecordsPanel

from computer_vision_v2.reno.services.camera_service import camera_service
from computer_vision_v2.reno.services.dashboard_service import dashboard_service
from computer_vision_v2.reno.services.plate_service import plate_service


class DashboardScreen(Screen):
    """`on_navigate` is set by main.py and receives every sidebar key,
    including "logout" - main.py's _navigate() handles that one."""

    def __init__(self, on_navigate=None, **kwargs):
        super().__init__(**kwargs)
        self.on_navigate = on_navigate
        self._records_timer = None
        self._records_active = False
        self._records_loading = False
        self._last_records = None
        self._build()
        camera_service.subscribe(self._on_cameras_changed)
        camera_service.subscribe_status(self._on_camera_status_changed)

    # ------------------------------------------------------------------
    def _build(self):
        content_root = BoxLayout(orientation="vertical")
        with content_root.canvas.before:
            Color(1, 1, 1, 1)
            self._bg_rect = Rectangle(
                pos=content_root.pos,
                size=content_root.size,
                texture=make_gradient_texture(PAGE_BG_TOP, PAGE_BG_BOTTOM),
            )
        content_root.bind(pos=self._redraw_bg, size=self._redraw_bg)
        self._content_root = content_root

        content_root.add_widget(self._build_header())

        body = BoxLayout(orientation="horizontal")

        content = BoxLayout(
            orientation="vertical",
            padding=[SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"]],
            spacing=SPACING["lg"],
        )
        content.add_widget(self._build_top_row())
        content.add_widget(self._build_bottom_row())
        body.add_widget(content)
        body.add_widget(Sidebar(active="dashboard", on_navigate=self._handle_navigate))
        content_root.add_widget(body)

        # A FloatLayout wrapper so toasts (save/delete feedback, etc.)
        # can be overlaid on top of the whole screen via pos_hint,
        # instead of being squeezed into whatever BoxLayout happens to
        # be nearby. See ui/components/common.py's show_toast().
        overlay_root = FloatLayout()
        overlay_root.add_widget(content_root)
        self.add_widget(overlay_root)

    def _redraw_bg(self, *_args):
        self._bg_rect.pos = self._content_root.pos
        self._bg_rect.size = self._content_root.size

    def _build_header(self):
        return AppHeader("داشبورد سامانه کنترل تردد")

    def _build_top_row(self):
        row = BoxLayout(orientation="horizontal", spacing=SPACING["lg"], size_hint_y=None, height=112)

        stats_col = GridLayout(cols=3, spacing=SPACING["lg"])
        self._today_card = StatCard(
            title="ورود و خروج امروز", value=0, icon_name="reports",
            gradient=GRADIENT_TEAL, size_hint_y=1,
        )
        self._week_card = StatCard(
            title="ورود و خروج این هفته", value=0, icon_name="reports",
            gradient=GRADIENT_BLUE, size_hint_y=1,
        )
        self._camera_count_card = StatCard(
            title="تعداد دوربین‌ها", value=0, icon_name="camera",
            gradient=GRADIENT_ORANGE, size_hint_y=1,
        )
        stats_col.add_widget(self._camera_count_card)
        stats_col.add_widget(self._week_card)
        stats_col.add_widget(self._today_card)

        row.add_widget(stats_col)
        return row

    def _build_bottom_row(self):
        self._records_panel = RecentRecordsPanel()
        return self._records_panel

    # -- events -----------------------------------------------------------
    def on_pre_enter(self, *_args):
        self._records_active = True
        self._refresh_stats()
        self._refresh_records()
        if self._records_timer is None:
            self._records_timer = Clock.schedule_interval(self._refresh_records, 2)

    def on_leave(self, *_args):
        self._records_active = False
        if self._records_timer is not None:
            self._records_timer.cancel()
            self._records_timer = None

    def _handle_navigate(self, key):
        if self.on_navigate:
            self.on_navigate(key)

    def _on_cameras_changed(self, _cameras):
        self._refresh_stats()

    def _on_camera_status_changed(self, _cameras):
        self._refresh_stats()

    # -- data refresh -------------------------------------------------
    def _refresh_stats(self):
        stats = dashboard_service.get_statistics()
        self._today_card.set_value(stats.today_total)
        self._week_card.set_value(stats.week_total)
        self._camera_count_card.set_value(stats.total_cameras)

    def _refresh_records(self, *_args):
        if not self._records_active or self._records_loading:
            return
        self._records_loading = True
        threading.Thread(target=self._load_records, daemon=True,
                         name='recent-plate-records').start()

    def _load_records(self):
        try:
            records = plate_service.get_recent_records(limit=50)
        except Exception:
            logging.getLogger(__name__).exception('Failed to read recent plate events')
            Clock.schedule_once(partial(self._apply_records, None), 0)
        else:
            Clock.schedule_once(partial(self._apply_records, records), 0)

    def _apply_records(self, records, _dt):
        self._records_loading = False
        if not self._records_active:
            return
        if records is None:
            self._records_panel.set_error()
            return
        if records != self._last_records:
            self._records_panel.set_records(records)
            self._last_records = records
        self._records_panel.clear_error(len(records))

