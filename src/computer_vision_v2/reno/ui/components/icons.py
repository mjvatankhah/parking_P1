"""RENO icon widget.

The navigation icons use local Tabler-style SVG/PNG assets. Keeping the
assets inside the application makes the desktop UI crisp and offline-safe,
while the Kivy Color instruction lets the same white source texture be tinted
for normal/active/hover states.
"""

import os

from kivy.uix.widget import Widget
from kivy.properties import StringProperty, ListProperty, NumericProperty
from kivy.graphics import Color, Line, Ellipse, Rectangle
from kivy.core.image import Image as CoreImage


_ASSET_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                 "assets", "icons", "tabler")
)

_ICON_FILES = {
    "dashboard": "layout-dashboard.png",
    "database": "database.png",
    "search": "search.png",
    "reports": "chart-bar.png",
    "settings": "settings.png",
    "logout": "logout.png",
    "camera": "camera.png",
    "help": "help-circle.png",
}


class Icon(Widget):
    name = StringProperty("dashboard")
    color = ListProperty([0.12, 0.17, 0.16, 1])
    line_width = NumericProperty(2.0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._texture = None
        self._icon_color = None
        self._icon_rect = None
        self.bind(pos=self._redraw, size=self._redraw,
                  color=self._redraw, name=self._redraw)
        self._load_texture()

    def _load_texture(self):
        filename = _ICON_FILES.get(self.name)
        if filename:
            path = os.path.join(_ASSET_DIR, filename)
            if os.path.isfile(path):
                try:
                    self._texture = CoreImage(path, mipmap=True).texture
                except Exception:
                    self._texture = None
        self._redraw()

    def on_name(self, *_args):
        self._load_texture()

    def _redraw(self, *_args):
        if self.canvas is None:
            return
        self.canvas.clear()
        if self.width <= 0 or self.height <= 0:
            return

        if self._texture is not None:
            with self.canvas:
                self._icon_color = Color(*self.color)
                pad = min(self.width, self.height) * 0.08
                size = min(self.width, self.height) - pad * 2
                x = self.x + (self.width - size) / 2
                y = self.y + (self.height - size) / 2
                self._icon_rect = Rectangle(
                    texture=self._texture,
                    pos=(x, y),
                    size=(size, size),
                )
            return

        # Small fallback for icons that intentionally remain vector-drawn.
        with self.canvas:
            Color(*self.color)
            x, y, s = self.box()
            if self.name == "qrcode":
                self._draw_qrcode(x, y, s)
            elif self.name == "plus":
                Line(points=[x + s/2, y, x + s/2, y+s], width=self.line_width)
                Line(points=[x, y+s/2, x+s, y+s/2], width=self.line_width)
            elif self.name == "close":
                Line(points=[x, y, x+s, y+s], width=self.line_width)
                Line(points=[x, y+s, x+s, y], width=self.line_width)
            elif self.name == "chevron_down":
                Line(points=[x, y+s*.65, x+s/2, y+s*.15, x+s, y+s*.65], width=self.line_width)
            elif self.name == "edit":
                Line(points=[x+s*.2, y+s*.2, x+s*.75, y+s*.75], width=self.line_width)
                Line(points=[x+s*.55, y+s*.9, x+s*.9, y+s*.55], width=self.line_width)
            elif self.name == "delete":
                Line(rounded_rectangle=(x+s*.28, y+s*.12, s*.44, s*.68, s*.05), width=self.line_width)
                Line(points=[x+s*.2, y+s*.82, x+s*.8, y+s*.82], width=self.line_width)
                Line(points=[x+s*.42, y+s*.9, x+s*.58, y+s*.9], width=self.line_width)

    def box(self):
        s = min(self.width, self.height) * 0.82
        return (
            self.x + (self.width - s) / 2,
            self.y + (self.height - s) / 2,
            s,
        )

    def _draw_qrcode(self, x, y, s):
        pattern = [
            "1110101110", "1000101000", "1011101011", "0000010010",
            "1101110101", "0010001100", "1111011111", "1000100001",
            "0110101110", "1001010001",
        ]
        cell = s / len(pattern)
        for row, bits in enumerate(pattern):
            for col, bit in enumerate(bits):
                if bit == "1":
                    Rectangle(pos=(x + col * cell, y + s - (row + 1) * cell),
                              size=(cell, cell))
