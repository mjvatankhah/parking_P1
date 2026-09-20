"""Compact, modern left navigation for the RENO desktop app.

The sidebar intentionally follows the reference visual language: a clean
white rail, small centered line icons, a soft green active tile, compact
labels under each icon, and a separated logout action at the bottom.
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.graphics import Color, RoundedRectangle, Line
from kivy.properties import StringProperty, BooleanProperty, ObjectProperty, ListProperty
from kivy.animation import Animation

from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.ui.theme import COLORS, FONT_SIZE, SIDEBAR_WIDTH
from computer_vision_v2.reno.ui.components.icons import Icon
from computer_vision_v2.reno.ui.components.common import RTLLabel, HoverBehavior


_ITEMS = [
    ("dashboard", "dashboard", "داشبورد"),
    ("cameras", "camera", "دوربین‌ها"),
    ("search", "search", "جستجو"),
    ("reports", "reports", "گزارش‌ها"),
    ("camera_settings", "settings", "تنظیمات"),
]


class _SidebarItem(HoverBehavior, ButtonBehavior, BoxLayout):
    active = BooleanProperty(False)
    key = StringProperty("")
    _bg_rgba = ListProperty([0, 0, 0, 0])

    def __init__(self, icon_name, label_text, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.size_hint = (1, None)
        self.height = 72
        self.padding = [5, 4, 5, 4]
        self.spacing = 3

        with self.canvas.before:
            self._bg_color = Color(0, 0, 0, 0)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[14])
        self.bind(pos=self._redraw_bg, size=self._redraw_bg)

        icon_slot = AnchorLayout(anchor_x="center", anchor_y="center",
                                 size_hint=(1, None), height=39)
        icon_tile = AnchorLayout(anchor_x="center", anchor_y="center",
                                 size_hint=(None, None), size=(38, 36))
        with icon_tile.canvas.before:
            self._tile_color = Color(*theme.rgba(COLORS["surface_alt"]))
            self._tile = RoundedRectangle(pos=icon_tile.pos, size=icon_tile.size, radius=[12])
            self._tile_border_color = Color(1, 1, 1, 0)
            self._tile_border = Line(rounded_rectangle=(*icon_tile.pos, *icon_tile.size, 12), width=1)
        icon_tile.bind(pos=self._redraw_tile, size=self._redraw_tile)

        self._icon = Icon(
            name=icon_name,
            color=theme.rgba(COLORS["text_secondary"]),
            size_hint=(None, None),
            size=(21, 21),
        )
        icon_tile.add_widget(self._icon)
        icon_slot.add_widget(icon_tile)
        self._icon_tile_widget = icon_tile

        self._label = RTLLabel(
            text=label_text,
            font_size=11.5,
            color=theme.rgba(COLORS["text_secondary"]),
            halign="center",
            valign="middle",
            size_hint=(1, None),
            height=17,
        )

        self.add_widget(icon_slot)
        self.add_widget(self._label)
        self._apply_active_style(False)

    def _redraw_bg(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def _redraw_tile(self, widget, *_):
        self._tile.pos = widget.pos
        self._tile.size = widget.size
        self._tile_border.rounded_rectangle = (*widget.pos, *widget.size, 12)

    def on_active(self, *_):
        self._apply_active_style(True)

    def on_hovered(self, *_):
        self._apply_active_style(True)

    def on__bg_rgba(self, _, value):
        self._bg_color.rgba = value

    def _apply_active_style(self, animate=True):
        highlighted = self.active or self.hovered
        bg = theme.rgba(COLORS["primary_light"], 1 if self.active else (0.55 if self.hovered else 0))
        tile = theme.rgba(COLORS["primary_light"] if highlighted else COLORS["surface_alt"])
        icon = COLORS["primary"] if highlighted else COLORS["text_secondary"]
        label = COLORS["primary_dark"] if highlighted else COLORS["text_secondary"]

        Animation.cancel_all(self, "_bg_rgba")
        if animate:
            Animation(_bg_rgba=bg, duration=theme.ANIM_NORMAL, t="out_quad").start(self)
        else:
            self._bg_rgba = bg

        self._icon.color = theme.rgba(icon)
        self._tile_color.rgba = tile
        self._label.color = theme.rgba(label)
        self._tile_border_color.rgba = theme.rgba(COLORS["primary"], 0.10 if self.active else 0)

        # The icon tile expands a touch for the current or hovered page.
        # It gives the otherwise compact rail clear, responsive feedback.
        target_tile = (44, 42) if highlighted else (38, 36)
        target_icon = (23, 23) if highlighted else (21, 21)
        Animation.cancel_all(self._icon_tile_widget, "size")
        Animation.cancel_all(self._icon, "size")
        if animate:
            Animation(size=target_tile, duration=theme.ANIM_NORMAL, t="out_back").start(self._icon_tile_widget)
            Animation(size=target_icon, duration=theme.ANIM_NORMAL, t="out_back").start(self._icon)
        else:
            self._icon_tile_widget.size = target_tile
            self._icon.size = target_icon


class Sidebar(BoxLayout):
    active = StringProperty("dashboard")
    on_navigate = ObjectProperty(None)

    def __init__(self, **kwargs):
        active = kwargs.pop("active", "dashboard")
        on_navigate = kwargs.pop("on_navigate", None)
        super().__init__(orientation="vertical", **kwargs)
        self.size_hint = (None, 1)
        self.width = SIDEBAR_WIDTH
        self.padding = [7, 12, 7, 12]
        self.spacing = 2
        self.active = active
        self.on_navigate = on_navigate
        self._items = {}

        with self.canvas.before:
            self._surface_color = Color(*theme.rgba(COLORS["sidebar"]))
            self._surface = RoundedRectangle(pos=self.pos, size=self.size, radius=[0])
            self._edge_color = Color(*theme.rgba(COLORS["border"]))
            self._edge = Line(points=[self.right, self.y, self.right, self.top], width=1.0)
        self.bind(pos=self._redraw_surface, size=self._redraw_surface)

        self._build()

    def _redraw_surface(self, *_):
        self._surface.pos = self.pos
        self._surface.size = self.size
        self._edge.points = [self.right, self.y, self.right, self.top]

    def _build(self):
        self.add_widget(RTLLabel(
            text="کالپینو", font_size=14, bold=True, halign="center",
            size_hint=(1, None), height=46,
        ))

        self.add_widget(Widget(size_hint_y=None, height=10))
        for key, icon_name, label in _ITEMS:
            item = _SidebarItem(icon_name, label, key=key)
            item.active = key == self.active
            item.bind(on_release=self._make_handler(key))
            self._items[key] = item
            self.add_widget(item)

        self.add_widget(Widget())
        logout = _SidebarItem("logout", "خروج", key="logout")
        logout.active = False
        logout.bind(on_release=self._make_handler("logout"))
        self._items["logout"] = logout
        self.add_widget(logout)

    def _make_handler(self, key):
        def _handler(*_args):
            if self.on_navigate:
                self.on_navigate(key)
        return _handler

    def set_active(self, key: str):
        self.active = key
        for item_key, item in self._items.items():
            item.active = item_key == key
