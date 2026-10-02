"""Weekly entries, grouped by day, in the reference palette and Persian font."""
import math
from datetime import date
from kivy.graphics import Color, Line, Ellipse
from kivy.uix.floatlayout import FloatLayout
from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.ui.components.common import RTLLabel


class TrafficChart(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data = []
        self.bind(pos=self._draw, size=self._draw)

    def set_data(self, data):
        self.data = data
        self._draw()

    def _label(self, text, x, y, width=58, color=None):
        self.add_widget(RTLLabel(text=text, font_size=10, halign='center',
                                color=theme.rgba(color or theme.COLORS['text_secondary']),
                                size_hint=(None, None), size=(width, 24), pos=(x, y)))

    def _draw(self, *_):
        self.canvas.before.clear()
        self.clear_widgets()
        if not self.data:
            self._label('در انتظار داده', self.center_x-60, self.center_y, 120)
            return
        left, bottom = self.x+42, self.y+72
        width, height = max(1, self.width-68), max(1, self.height-125)
        peak = max(4, *(row[1] for row in self.data))
        step = max(1, math.ceil(peak/4))
        maximum = step*4
        self._label('تعداد ورود', left-25, bottom+height+8, 80)
        with self.canvas.before:
            for i in range(5):
                y = bottom + height*i/4
                Color(*theme.rgba(theme.COLORS['border'], .8))
                Line(points=[left, y, left+width, y], width=1)
        for i in range(5):
            self._label(theme.fa_number(step*i), self.x, bottom+height*i/4-12, 35)
        for i, row in enumerate(self.data):
            day = date.fromisoformat(row[0])
            weekday = ['دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه', 'شنبه', 'یکشنبه'][day.weekday()]
            self._label(weekday, left+width*i/max(1, len(self.data)-1)-29, bottom-30)
            self._label(theme.fa_number(row[0][5:]), left+width*i/max(1, len(self.data)-1)-29, bottom-50)
        self._label('تاریخ میلادی', left+width/2-45, self.y-4, 90)
        for column, color in [(1, theme.COLORS['primary'])]:
            points = []
            for i, row in enumerate(self.data):
                points.extend([left+width*i/max(1, len(self.data)-1), bottom+height*row[column]/maximum])
            with self.canvas.before:
                Color(*theme.rgba(color))
                Line(points=points, width=1.1)
                for x, y in zip(points[::2], points[1::2]):
                    Ellipse(pos=(x-2,y-2), size=(4,4))
