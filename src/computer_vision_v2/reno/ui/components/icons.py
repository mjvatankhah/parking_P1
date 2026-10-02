"""The exact SVG symbols from dashboard-prototype.html, shipped as offline textures."""

import os

from kivy.uix.widget import Widget
from kivy.properties import StringProperty, ListProperty, NumericProperty
from kivy.graphics import Color, Line, Ellipse, Rectangle
from kivy.core.image import Image as CoreImage


_ASSET_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                 "assets", "icons")
)

_ICON_FILES = {
    "dashboard": "reference/grid.png",
    "database": "reference/log.png",
    "log": "reference/log.png",
    "search": "reference/icon-search.png",
    "reports": "reference/chart.png",
    "settings": "reference/settings.png",
    "camera": "reference/camera.png",
    "car": "reference/car.png",
    "shield": "reference/shield.png",
    "bell": "reference/bell.png",
    "menu": "reference/menu.png",
    "logout": "tabler/logout.png",
    "help": "tabler/help-circle.png",
}
_TEXTURES = {}
APP_ICON = os.path.join(_ASSET_DIR, "reference", "app.png")



class Icon(Widget):
    name = StringProperty("dashboard")
    color = ListProperty([0.12, 0.17, 0.16, 1])
    line_width = NumericProperty(1.0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._texture = None
        self._icon_color = None
        self._icon_rect = None
        self.bind(pos=self._redraw, size=self._redraw,
                  color=self._redraw, name=self._redraw)
        self._load_texture()

    def _load_texture(self):
        self._texture = None
        filename = _ICON_FILES.get(self.name)
        if filename:
            path = os.path.join(_ASSET_DIR, filename)
            if os.path.isfile(path):
                try:
                    if path not in _TEXTURES:
                        _TEXTURES[path] = CoreImage(path, mipmap=True).texture
                    self._texture = _TEXTURES[path]
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
                pad = 0
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
            if self.name == "car":
                Line(rounded_rectangle=(x, y+s*.2, s, s*.4, s*.08), width=self.line_width)
                Line(points=[x+s*.15,y+s*.6,x+s*.3,y+s*.85,x+s*.7,y+s*.85,x+s*.85,y+s*.6], width=self.line_width)
                for cx in (.2, .8):
                    Line(circle=(x+s*cx,y+s*.2,s*.1), width=self.line_width)
            elif self.name == "bell":
                Line(points=[x+s*.1,y+s*.25,x+s*.25,y+s*.4,x+s*.25,y+s*.7,x+s*.4,y+s*.9,x+s*.6,y+s*.9,x+s*.75,y+s*.7,x+s*.75,y+s*.4,x+s*.9,y+s*.25,x+s*.1,y+s*.25], width=self.line_width)
                Line(circle=(x+s*.5,y+s*.12,s*.08), width=self.line_width)
            elif self.name == "qrcode":
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
