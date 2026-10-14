"""Consistent Lucide icons, shipped as offline textures with their SVG sources."""

import os

from kivy.uix.widget import Widget
from kivy.properties import StringProperty, ListProperty, NumericProperty
from kivy.graphics import Color, Rectangle
from kivy.core.image import Image as CoreImage


_ASSET_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                 "assets", "icons")
)

_ICON_FILES = {
    "maximize": "lucide/maximize.png",
    "minus": "lucide/minus.png",
    "dashboard": "lucide/layout-dashboard.png",
    "database": "lucide/file-text.png",
    "log": "lucide/file-text.png",
    "search": "lucide/search.png",
    "reports": "lucide/chart-column.png",
    "settings": "lucide/settings-2.png",
    "camera": "lucide/video.png",
    "car": "lucide/car-front.png",
    "shield": "lucide/shield-check.png",
    "bell": "lucide/bell.png",
    "menu": "lucide/menu.png",
    "logout": "lucide/log-out.png",
    "help": "lucide/circle-help.png",
    "qrcode": "lucide/qr-code.png",
    "plus": "lucide/plus.png",
    "close": "lucide/x.png",
    "chevron_down": "lucide/chevron-down.png",
    "edit": "lucide/pencil.png",
    "delete": "lucide/trash-2.png",
}

_TEXTURES = {}
APP_ICON = os.path.join(_ASSET_DIR, "lucide", "app.png")



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
