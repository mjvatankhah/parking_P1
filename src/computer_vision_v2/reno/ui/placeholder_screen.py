"""
ui/placeholder_screen.py

A generic "this page isn't built yet" screen shell, reused for Search
and Reports. It has the same header + sidebar shell as every other
screen (so navigation feels consistent and nothing looks broken), and
an EmptyState in the content area instead of a popup interrupting the
flow - which is what these two used to do before this screen existed.

There is deliberately no logic here beyond layout: this is a shell to
build the real Search / Reports screen into later. When that happens,
this file's `_build_content()` is the only thing that needs to change
into a real implementation - the header/sidebar/navigation wiring
stays exactly as-is.
"""

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.graphics import Color, Rectangle

from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.ui.theme import COLORS, FONT_SIZE, SPACING, PAGE_BG_TOP, PAGE_BG_BOTTOM
from computer_vision_v2.reno.ui.components.common import Card, make_gradient_texture, RTLLabel, EmptyState
from computer_vision_v2.reno.ui.components.sidebar import Sidebar
from computer_vision_v2.reno.ui.components.app_header import AppHeader


class PlaceholderScreen(Screen):
    """`on_navigate` is set by main.py. `page_key` must match one of
    the sidebar's keys ("search" or "reports") so the sidebar shows
    the right item as active. `title` and `subtitle` are the Persian
    strings shown in the header and empty state."""

    def __init__(self, page_key: str, title: str, icon_name: str = "reports",
                 subtitle: str = "این بخش هنوز آماده نشده است",
                 on_navigate=None, **kwargs):
        super().__init__(**kwargs)
        self.on_navigate = on_navigate
        self._page_key = page_key
        self._title = title
        self._icon_name = icon_name
        self._subtitle = subtitle
        self._build()

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
        content = BoxLayout(orientation="vertical",
                             padding=[SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"]])
        content.add_widget(EmptyState(
            icon_name=self._icon_name,
            title=self._subtitle,
            subtitle="این صفحه در نسخه‌ی بعدی تکمیل می‌شود",
        ))
        body.add_widget(content)
        body.add_widget(Sidebar(active=self._page_key, on_navigate=self._handle_navigate))
        content_root.add_widget(body)

        self.add_widget(content_root)

    def _redraw_bg(self, *_args):
        self._bg_rect.pos = self._content_root.pos
        self._bg_rect.size = self._content_root.size

    def _build_header(self):
        return AppHeader(self._title)

    def _handle_navigate(self, key):
        if self.on_navigate:
            self.on_navigate(key)
