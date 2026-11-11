"""Panning must reuse the raster instead of blocking input with an Agg draw."""
import unittest
from unittest.mock import patch
from reno.ui import theme
from reno.ui.components.traffic_chart import TrafficChart, render_chart


class ChartPanPerformanceTests(unittest.TestCase):
    def test_pan_reuses_raster_and_refresh_invalidates_it(self):
        theme.register_app_font()
        chart = TrafficChart(period='hourly', size=(700, 280))
        chart.set_data([(h, h, 23-h) for h in range(24)])
        chart._draw()
        texture_id = chart._image.texture.id
        margins = (chart._left_margin.texture, chart._right_margin.texture)
        try:
            with patch('reno.ui.components.traffic_chart.render_chart', wraps=render_chart) as draw:
                for position in (0, .25, .5, 1):
                    chart.hour_scroll.scroll_x = position
                    chart._draw()
                    self.assertAlmostEqual(chart._figure.axes[0].get_xlim()[0], -.5+12*position)
                    self.assertEqual(chart._image.texture.id, texture_id)
                    self.assertEqual((chart._left_margin.texture, chart._right_margin.texture), margins)
                self.assertEqual(draw.call_count, 0)
                chart.set_metric('both')
                chart._draw()
                self.assertEqual(draw.call_count, 1)
        finally:
            chart._render_trigger.cancel()
