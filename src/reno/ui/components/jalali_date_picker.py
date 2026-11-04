"""Single-day Jalali picker; selected values are Gregorian date objects."""
from datetime import date, timedelta
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from reno.ui import theme
from reno.ui.vendor.jalaali import Jalaali
from reno.ui.components.common import Card, SecondaryButton, RTLLabel
from reno.ui.components.jalali_calendar import MONTHS, WEEKDAYS, week_bounds, jalali_text


class JalaliDatePicker(SecondaryButton):
    def __init__(self, **kwargs):
        self.selected = None
        super().__init__(text=theme.rtl('انتخاب تاریخ'), **kwargs)
        self.bind(on_release=self._open)

    def _open(self, *_):
        day = self.selected or date.today()
        value = Jalaali.to_jalaali(day.year,day.month,day.day)
        self._year,self._month = value['jy'],value['jm']
        root = Card(orientation='vertical',padding=16,spacing=8,hover_effect=False)
        nav = BoxLayout(size_hint_y=None,height=36,spacing=8)
        for title,delta in [('ماه قبل',-1),('ماه بعد',1)]:
            button=SecondaryButton(text=theme.rtl(title),size_hint_x=None,width=90,font_size=12)
            button.bind(on_release=lambda _,d=delta:self._move(d))
            nav.add_widget(button)
        self.heading=RTLLabel(halign='center')
        nav.add_widget(self.heading)
        root.add_widget(nav)
        self.grid=GridLayout(cols=7,spacing=4)
        root.add_widget(self.grid)
        clear=SecondaryButton(text=theme.rtl('حذف محدودیت تاریخ'),size_hint_y=None,height=38)
        clear.bind(on_release=lambda *_:self._select(None))
        root.add_widget(clear)
        self.popup=Popup(title='',separator_height=0,content=root,background='',
                         background_color=theme.rgba(theme.COLORS['surface']),size_hint=(None,None),size=(460,420))
        self._render()
        self.popup.open()

    def _move(self,delta):
        value=self._year*12+self._month-1+delta
        self._year,self._month=value//12,value%12+1
        self._render()

    def _render(self):
        self.heading.set_text(f'{MONTHS[self._month-1]} {theme.fa_number(self._year)}')
        self.grid.clear_widgets()
        for name in WEEKDAYS:
            self.grid.add_widget(RTLLabel(text=name,font_size=10,halign='center',padding=[0,0]))
        first=Jalaali.to_gregorian(self._year,self._month,1)
        start=week_bounds(date(first['gy'],first['gm'],first['gd']))[0]
        for offset in range(42):
            day=start+timedelta(days=offset)
            value=Jalaali.to_jalaali(day.year,day.month,day.day)
            button=SecondaryButton(text=theme.fa_number(value['jd']),font_size=13,
                bg_color_normal=theme.rgba(theme.COLORS['primary_light'] if day==self.selected else theme.COLORS['surface']),
                color=theme.rgba(theme.COLORS['text_primary'] if value['jm']==self._month else theme.COLORS['text_secondary']))
            button.bind(on_release=lambda _,d=day:self._select(d))
            self.grid.add_widget(button)

    def _select(self,day):
        self.selected=day
        self.text=theme.rtl(jalali_text(day) if day else 'انتخاب تاریخ')
        self.popup.dismiss()
