"""Soft moving blue and matte-purple lights, shared by login and app pages."""
import math
from functools import lru_cache
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.graphics.texture import Texture
from kivy.uix.boxlayout import BoxLayout
from computer_vision_v2.reno.ui import theme


@lru_cache(maxsize=1)
def _light_texture():
    pixels = bytearray()
    for y in range(128):
        for x in range(128):
            radius = ((x-63.5)**2+(y-63.5)**2)/64**2
            pixels.extend((255, 255, 255, round(255*max(0, 1-radius)**2.5)))
    texture = Texture.create(size=(128, 128), colorfmt='rgba')
    texture.blit_buffer(bytes(pixels), colorfmt='rgba', bufferfmt='ubyte')
    return texture


class AmbientBackground(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*theme.rgba(theme.COLORS['background']))
            self._base = Rectangle()
            self._blue_color = Color(*theme.rgba('#00A9E8', .18))
            self._blue = Rectangle(texture=_light_texture())
            self._purple_color = Color(*theme.rgba('#9254FF', .24))
            self._purple = Rectangle(texture=_light_texture())
            Color(*theme.rgba('#7052B8', .1))
            self._haze = Rectangle(texture=_light_texture())
        self._phase = 0
        self.bind(pos=self._position, size=self._position)
        self._position()
        self._animation = Clock.schedule_interval(self._tick, 1/30)

    def _tick(self, dt):
        if not self.get_root_window():
            return
        self._phase += dt*.24
        self._position()

    def _position(self, *_):
        self._base.pos, self._base.size = self.pos, self.size
        p, w, h = self._phase, self.width, self.height
        self._blue.size = (w*.95, h*1.25)
        self._purple.size = (w*.85, h*1.25)
        self._haze.size = (w*.7, h*.95)
        self._blue.pos = (self.x+w*(-.25+.12*math.sin(p)), self.y+h*(.12+.06*math.cos(p*.8)))
        self._purple.pos = (self.x+w*(.35+.14*math.cos(p*.7)), self.y+h*(-.35+.12*math.sin(p*.9)))
        self._haze.pos = (self.x+w*(.1+.15*math.sin(p*.6)), self.y+h*(.35+.1*math.cos(p)))
        self._purple_color.a = .22+.035*math.sin(p)
        self._blue_color.a = .16+.025*math.cos(p*.8)
