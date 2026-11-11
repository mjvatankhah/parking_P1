"""Exercise pointer input inside the dashboard's nested scrolling layout."""
import unittest
from kivy.base import EventLoop
from kivy.core.window import Window
from kivy.input.motionevent import MotionEvent
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from reno.ui import theme
from reno.ui.components.traffic_chart import TrafficChart


class Pointer(MotionEvent):
    def __init__(self, x, y):
        super().__init__('test', 1, (x / (Window.width - 1), y / (Window.height - 1)),
                         is_touch=True, type_id='touch')
        self.profile = ['pos']

    def depack(self, args):
        self.sx, self.sy = args
        super().depack(args)

    def touch_down(self):
        EventLoop.post_dispatch_input('begin', self)

    def touch_move(self, x, y):
        self.move((x / (Window.width - 1), y / (Window.height - 1)))
        EventLoop.post_dispatch_input('update', self)

    def touch_up(self):
        EventLoop.post_dispatch_input('end', self)


class HourlyScrollTests(unittest.TestCase):
    def test_visible_horizontal_bar_drags_inside_vertical_page(self):
        theme.register_app_font()
        page = ScrollView(do_scroll_x=False, size_hint=(None, None), size=(700, 550))
        content = BoxLayout(orientation='vertical', size_hint_y=None, height=1000)
        chart = TrafficChart(period='hourly', size_hint_y=None, height=300)
        content.add_widget(chart)
        content.add_widget(Widget(size_hint_y=None, height=700))
        page.add_widget(content)
        Window.add_widget(page)
        try:
            for _ in range(8):
                EventLoop.idle()
            initial = chart.hour_scroll.scroll_x
            x, y = chart.to_window(chart.x + chart.width * .55, chart.y + 8)
            touch = Pointer(x, y)
            touch.touch_down()
            for offset in (15, 40, 80):
                touch.touch_move(x + offset, y)
                EventLoop.idle()
            touch.touch_up()
            self.assertGreater(chart.hour_scroll.scroll_x, initial + .1)
            # Drag back toward earlier hours using the actual thumb location.
            moved = chart.hour_scroll.scroll_x
            start, width = chart.hour_scroll.hbar
            x, y = chart.to_window(chart.x + chart.width * (start + width / 2), chart.y + 8)
            touch = Pointer(x, y)
            touch.touch_down()
            for offset in (15, 40, 80):
                touch.touch_move(x - offset, y)
                EventLoop.idle()
            touch.touch_up()
            self.assertLess(chart.hour_scroll.scroll_x, moved - .1)
            self.assertAlmostEqual(page.scroll_y, 1)
            chart._draw()
            self.assertAlmostEqual(chart._figure.axes[0].get_xlim()[0],
                                   -.5 + 12 * chart.hour_scroll.scroll_x)
        finally:
            chart._render_trigger.cancel()
            Window.remove_widget(page)
