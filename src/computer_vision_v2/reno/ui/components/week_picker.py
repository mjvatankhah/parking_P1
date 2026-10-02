"""Jalali month picker selecting whole Saturday–Friday weeks."""
from datetime import date, timedelta
from computer_vision_v2.reno.ui.vendor.jalaali import Jalaali
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.ui.components.common import Card, SecondaryButton, RTLLabel
from computer_vision_v2.reno.ui.components.jalali_calendar import MONTHS, WEEKDAYS, week_bounds, week_text


class WeekPicker(SecondaryButton):
    def __init__(self, on_select, **kwargs):
        self.selected = week_bounds(date.today())[0]
        self.on_select = on_select
        super().__init__(text=theme.rtl(week_text(self.selected)), **kwargs)
        self.bind(on_release=self._open)

    def set_date(self, value):
        self.selected = week_bounds(value or date.today())[0]
        self.text = theme.rtl(week_text(self.selected))
        self.on_select(week_bounds(self.selected)[1])

    def _open(self, *_):
        value = Jalaali.to_jalaali(self.selected.year,self.selected.month,self.selected.day)
        self._year, self._month = value["jy"], value["jm"]
        root = Card(orientation='vertical', padding=16, spacing=10, hover_effect=False)
        nav = BoxLayout(size_hint_y=None, height=36, spacing=8)
        for text, direction in [('ماه قبل', -1), ('ماه بعد', 1)]:
            button = SecondaryButton(text=theme.rtl(text), font_size=12, size_hint_x=None, width=78)
            button.bind(on_release=lambda _, d=direction: self._move(d))
            nav.add_widget(button)
        self._heading = RTLLabel(halign='center')
        nav.add_widget(self._heading)
        root.add_widget(nav)
        root.add_widget(RTLLabel(text='انتخاب یک روز، کل هفته را انتخاب می‌کند', font_size=12,
                                 size_hint_y=None, height=24, color=theme.rgba(theme.COLORS['text_secondary'])))
        self._grid = GridLayout(cols=7, spacing=4)
        root.add_widget(self._grid)
        current = SecondaryButton(text=theme.rtl('هفتهٔ جاری'), size_hint_y=None, height=36)
        current.bind(on_release=lambda *_: self._select(date.today()))
        root.add_widget(current)
        self._popup = Popup(title='', separator_height=0, background='', background_color=(0,0,0,0),
                            content=root, size_hint=(None,None), size=(460,420))
        self._render()
        self._popup.open()

    def _move(self, direction):
        index = self._year*12+self._month-1+direction
        self._year, self._month = index//12, index%12+1
        self._render()

    def _render(self):
        self._heading.set_text(f'{MONTHS[self._month-1]} {theme.fa_number(self._year)}')
        self._grid.clear_widgets()
        for name in WEEKDAYS:
            self._grid.add_widget(RTLLabel(text=name, font_size=10, halign='center', padding=[0,0]))
        value = Jalaali.to_gregorian(self._year,self._month,1)
        first = date(value["gy"],value["gm"],value["gd"])
        start = week_bounds(first)[0]
        selected_start, selected_end = week_bounds(self.selected)
        for offset in range(42):
            day = start+timedelta(days=offset)
            jalali = Jalaali.to_jalaali(day.year,day.month,day.day)
            active = selected_start <= day <= selected_end
            button = SecondaryButton(text=theme.fa_number(jalali["jd"]), font_size=13,
                color=theme.rgba(theme.COLORS['text_primary'] if jalali["jm"]==self._month else theme.COLORS['text_secondary']),
                bg_color_normal=theme.rgba(theme.COLORS['primary_light'] if active else theme.COLORS['surface']),
                border_color=theme.rgba(theme.COLORS['primary'] if active else theme.COLORS['border']))
            button.bind(on_release=lambda _, value=day: self._select(value))
            self._grid.add_widget(button)

    def _select(self, value):
        self.set_date(value)
        self._popup.dismiss()
