"""Dedicated view of the backend's annotated camera frames."""

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.graphics import Color, Rectangle

from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.ui.theme import COLORS, SPACING, PAGE_BG_TOP, PAGE_BG_BOTTOM
from computer_vision_v2.reno.ui.components.common import Card, RTLLabel, EmptyState, make_gradient_texture
from computer_vision_v2.reno.ui.components.app_header import AppHeader
from computer_vision_v2.reno.ui.components.sidebar import Sidebar
from computer_vision_v2.reno.ui.components.camera_selector import build_camera_selector, ALL_CAMERAS_VALUE
from computer_vision_v2.reno.ui.components.camera_card import CameraCard
from computer_vision_v2.reno.services.camera_service import camera_service


class CamerasScreen(Screen):
    def __init__(self, on_navigate=None, **kwargs):
        super().__init__(**kwargs)
        self.on_navigate = on_navigate
        self._camera_filter = ALL_CAMERAS_VALUE
        self._active = False
        self._cards = []
        root = BoxLayout(orientation="vertical")
        with root.canvas.before:
            Color(1, 1, 1, 1)
            background = Rectangle(pos=root.pos, size=root.size, texture=make_gradient_texture(PAGE_BG_TOP, PAGE_BG_BOTTOM))
        root.bind(pos=lambda widget, value: setattr(background, "pos", value),
                  size=lambda widget, value: setattr(background, "size", value))
        root.add_widget(AppHeader("دوربین‌ها — تصاویر تشخیص‌داده‌شده"))
        body = BoxLayout(orientation="horizontal")
        content = BoxLayout(orientation="vertical", padding=SPACING["lg"], spacing=SPACING["sm"])
        content.add_widget(RTLLabel(
            text="نمایش خروجی پردازش دوربین‌ها • انسان و خودرو",
            size_hint_y=None, height=32,
        ))
        content.add_widget(self._build_camera_panel())
        body.add_widget(content)
        body.add_widget(Sidebar(active="cameras", on_navigate=self._handle_navigate))
        root.add_widget(body)
        self.add_widget(root)
        camera_service.subscribe(self._on_cameras_changed)

    def on_enter(self, *_args):
        self._active = True
        for card in self._cards:
            card.ensure_stream_started()

    def on_leave(self, *_args):
        self._active = False
        for card in self._cards:
            card.stop_stream()

    def _handle_navigate(self, key):
        if self.on_navigate:
            self.on_navigate(key)

    def _on_camera_selected(self, value):
        self._camera_filter = value
        self._rebuild_camera_grid()

    def _on_cameras_changed(self, _cameras):
        self._rebuild_camera_grid()

    def _build_camera_panel(self):
        panel = Card(orientation="vertical", padding=[SPACING["md"], SPACING["md"], SPACING["md"], SPACING["md"]],
                      spacing=SPACING["sm"])

        selector_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=44, spacing=SPACING["sm"])
        label = RTLLabel(
            text="دوربین مورد نظر را انتخاب کنید:",
            color=theme.rgba(COLORS["text_secondary"]),
            size_hint_x=1,
            valign="middle",
        )

        self._selector = build_camera_selector(on_select=self._on_camera_selected)

        selector_row.add_widget(label)
        selector_row.add_widget(self._selector)

        self._camera_grid_holder = BoxLayout(orientation="vertical")

        panel.add_widget(selector_row)
        panel.add_widget(self._camera_grid_holder)
        self._rebuild_camera_grid()
        return panel

    def _rebuild_camera_grid(self):
        for card in self._cards:
            card.stop_stream()
        self._cards = []
        self._camera_grid_holder.clear_widgets()
        all_cameras = camera_service.get_cameras()
        cameras = all_cameras
        if self._camera_filter != ALL_CAMERAS_VALUE:
            cameras = [c for c in all_cameras if c.id == self._camera_filter]

        if not all_cameras:
            # No cameras configured anywhere yet - this is a real,
            # honest empty state (not a filtered-down view), so it
            # gets a call-to-action straight to Camera Settings.
            empty = EmptyState(
                icon_name="camera",
                title="هنوز دوربینی تنظیم نشده است",
                subtitle="برای مشاهده تصویر دوربین‌ها، ابتدا یک دوربین اضافه کنید",
                action_text="افزودن دوربین",
                on_action=lambda: self._handle_navigate("camera_settings"),
                size_hint_y=None,
                height=220,
            )
            self._camera_grid_holder.add_widget(empty)
            return

        if not cameras:
            # A specific camera was selected in the dropdown but no
            # longer exists (e.g. deleted from Camera Settings).
            empty = EmptyState(icon_name="camera", title="این دوربین دیگر موجود نیست",
                                size_hint_y=None, height=160)
            self._camera_grid_holder.add_widget(empty)
            return

        columns = 2 if len(cameras) > 1 else 1
        grid = GridLayout(cols=columns, size_hint_y=None, spacing=SPACING["sm"], padding=[0, SPACING["sm"], 0, 0])
        grid.bind(minimum_height=grid.setter("height"))
        for camera in cameras:
            card = CameraCard(camera, size_hint_y=None, height=320)
            self._cards.append(card)
            grid.add_widget(card)
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(grid)
        self._camera_grid_holder.add_widget(scroll)
        if self._active:
            for card in self._cards:
                card.ensure_stream_started()
