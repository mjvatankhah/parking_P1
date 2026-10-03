"""Calendar boundaries, RTL plate order and operational row/series contracts."""
import unittest
from datetime import date, timedelta
from kivy.clock import Clock
from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.ui.components.jalali_calendar import week_bounds, week_text, jalali_text, WEEKDAYS
from computer_vision_v2.reno.ui.components.week_picker import WeekPicker
from computer_vision_v2.reno.ui.components.iranian_plate import PlainPlate, IranianPlate
from computer_vision_v2.reno.ui.components.traffic_record import TrafficRecordRow
from computer_vision_v2.reno.ui.components.traffic_chart import TrafficChart
from computer_vision_v2.reno.models.plate_record import PlateRecord


def layout():
    for _ in range(6):
        Clock.tick()


class WeeklyUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        theme.register_app_font()

    def test_jalali_new_year_and_leap_day(self):
        self.assertEqual(jalali_text(date(2025,3,20)), '۱۴۰۳/۱۲/۳۰')
        self.assertEqual(jalali_text(date(2025,3,21)), '۱۴۰۴/۰۱/۰۱')
        self.assertEqual(jalali_text('2026-10-02'), '۱۴۰۵/۰۷/۱۰')
        self.assertEqual(jalali_text('invalid'), '—')

    def test_every_day_selects_same_saturday_friday_week(self):
        saturday=date(2026,9,26)
        for i in range(7):
            self.assertEqual(week_bounds(saturday+timedelta(days=i)),(saturday,date(2026,10,2)))
        self.assertEqual(week_text(saturday),'۱۴۰۵/۰۷/۰۴ تا ۱۴۰۵/۰۷/۱۰')
        self.assertEqual(week_bounds(date(2027,1,1)),(date(2026,12,26),date(2027,1,1)))

    def test_week_picker_navigation_and_callback(self):
        selected=[]
        picker=WeekPicker(selected.append)
        picker.set_date(date(2026,9,28))
        self.assertEqual(selected[-1],date(2026,10,2))
        picker._open()
        try:
            picker._year,picker._month=1405,1
            picker._move(-1)
            self.assertEqual((picker._year,picker._month),(1404,12))
            self.assertEqual(len(picker._grid.children),49)
            picker._select(date(2025,3,20))
            self.assertEqual(selected[-1],date(2025,3,21))
        finally:
            picker._popup.dismiss()

    def test_plain_plate_keeps_physical_order_without_template(self):
        plate=PlainPlate('12ب34567',size_hint=(None,None),size=(160,40))
        layout()
        labels=list(reversed(plate.children))
        self.assertEqual([w.text for w in labels],[theme.rtl(s) for s in ('۱۲','ب','۳۴۵','|','۶۷')])
        self.assertEqual([w.x for w in labels],sorted(w.x for w in labels))
        self.assertFalse(any(isinstance(w,IranianPlate) for w in plate.walk()))

    def test_rows_keep_column_alignment_and_image_on_right(self):
        rows=[TrafficRecordRow(PlateRecord(plate,'2026-10-02','12:48:32',camera),
                              size_hint_x=None,width=500)
              for plate,camera in [('۱۲ب۳۴۵۶۷','دوربین ۱'),('۴۵ج۶۷۸۹۰','دوربین ۲')]]
        layout()
        for row in rows:
            self.assertGreater(row._thumbnail.x,row._plate.x)
            self.assertEqual(row._date_label.text,theme.rtl('۱۴۰۵/۰۷/۱۰'))
        self.assertEqual(rows[0]._thumbnail.width,rows[1]._thumbnail.width)
        self.assertEqual(rows[0]._plate.x,rows[1]._plate.x)
        self.assertEqual(rows[0]._camera.x,rows[1]._camera.x)

    def test_chart_weekday_order_and_both_series(self):
        chart=TrafficChart(size=(430,230),size_hint=(None,None))
        data=[((date(2026,9,26)+timedelta(days=i)).isoformat(),i+1,7-i) for i in range(7)]
        chart.set_data(list(reversed(data)))
        chart.set_metric('both')
        layout()
        self.assertEqual(chart.data,data)
        chart._draw()
        axes=chart._figure.axes[0]
        labels=axes.get_xticklabels()
        self.assertEqual([w.get_text() for w in labels],list(WEEKDAYS))
        self.assertEqual([w.get_position()[0] for w in labels],list(range(7)))
        self.assertEqual([line.get_label() for line in axes.lines],['ورود','خروج'])
        self.assertEqual(list(axes.lines[0].get_ydata()),list(range(1,8)))
        self.assertEqual(list(axes.lines[1].get_ydata()),list(range(7,0,-1)))
        self.assertEqual(chart._image.texture.size,(860,460))
        chart.set_metric('exit')
        chart._draw()
        self.assertEqual(len(chart._figure.axes[0].lines),1)
        self.assertEqual(chart._figure.axes[0].lines[0].get_color(),theme.COLORS['exit'])

    def test_chart_resize_and_empty_state(self):
        chart=TrafficChart(size=(300,180),size_hint=(None,None))
        chart._draw()
        self.assertEqual(chart._image.texture.size,(600,360))
        self.assertTrue(any(text.get_text()=='داده‌ای برای نمایش موجود نیست'
                            for text in chart._figure.axes[0].texts))
        chart.size=(640,300)
        chart._draw()
        self.assertEqual(chart._image.texture.size,(1280,600))
        chart.pos=(180,240)
        layout()
        self.assertEqual(chart._image.pos,chart.pos)
        self.assertEqual(chart._image.size,chart.size)
        figure_axes=chart._figure.axes[0]
        chart.set_data([])
        chart._draw()
        self.assertIs(chart._figure.axes[0],figure_axes)
        chart.set_data([('2026-10-02',0,0)])
        chart._draw()
        self.assertGreater(chart._figure.axes[0].get_ylim()[1],0)

if __name__=='__main__': unittest.main()
