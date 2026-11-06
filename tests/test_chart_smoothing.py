import unittest
import numpy as np
from reno.ui.components.traffic_chart import smooth_series,TrafficChart
from reno.ui import theme


class ChartSmoothingTests(unittest.TestCase):
    def test_knots_preserved_and_no_extra_extrema_or_negative_counts(self):
        x=np.arange(7)
        y=[0,100,3,3,80,0,20]
        xx,yy=smooth_series(x,y)
        np.testing.assert_array_equal(xx[::32],x)
        np.testing.assert_array_equal(yy[::32],y)
        for i in range(6):
            segment=yy[i*32:(i+1)*32+1]
            self.assertGreaterEqual(segment.min(),min(y[i:i+2])-1e-9)
            self.assertLessEqual(segment.max(),max(y[i:i+2])+1e-9)
        self.assertGreaterEqual(yy.min(),0)
        self.assertLess(abs(yy[31]-yy[32]),1)
        self.assertLess(abs(yy[33]-yy[32]),1)

    def test_empty_single_and_two_point_series_are_supported(self):
        for x,y in (([],[]),([1],[5]),([1,2],[3,0])):
            xx,yy=smooth_series(x,y)
            np.testing.assert_array_equal(xx,x)
            np.testing.assert_array_equal(yy,y)

    def test_both_rendered_series_use_solid_smoothed_lines_and_fill(self):
        theme.register_app_font()
        chart=TrafficChart(size=(600,320))
        chart.set_metric('both')
        chart.set_data([('2026-11-01',0,20),('2026-11-02',30,40),('2026-11-03',10,0)])
        chart._draw()
        axes=chart._figure.axes[0]
        for line in axes.lines:
            self.assertEqual(line.get_linestyle(),'-')
            self.assertGreater(len(line.get_xdata()),3)
        self.assertEqual(len(axes.images),2)

    def test_hourly_chart_preserves_all_24_measurements_and_semantic_colors(self):
        theme.register_app_font()
        chart=TrafficChart(period='hourly',size=(700,280))
        chart.set_metric('both')
        data=[(hour,hour,23-hour) for hour in range(24)]
        chart.set_data(list(reversed(data)))
        chart._draw()
        axes=chart._figure.axes[0]
        self.assertEqual(chart.data,data)
        self.assertEqual(len(axes.lines),2)
        for line,column,color in zip(axes.lines,(1,2),('cyan','amber')):
            np.testing.assert_array_equal(line.get_xdata()[::32],range(24))
            np.testing.assert_array_equal(line.get_ydata()[::32],[row[column] for row in data])
            self.assertEqual(line.get_color(),theme.DASHBOARD_COLORS[color])
        self.assertIn(23,axes.get_xticks())
