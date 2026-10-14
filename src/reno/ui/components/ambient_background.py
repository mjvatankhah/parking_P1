"""Static graphite background; motion is reserved for interaction feedback."""
from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from reno.ui import theme


class AmbientBackground(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*theme.rgba(theme.COLORS['background']))
            self._base = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._position, size=self._position)

    def _position(self, *_):
        self._base.pos, self._base.size = self.pos, self.size
