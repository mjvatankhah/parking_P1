"""Gregorian calendar picker with an explicit calendar label and clear action."""
import calendar
from datetime import date
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from reno.ui import theme
from reno.ui.components.common import SecondaryButton, RTLLabel


class DatePicker(SecondaryButton):
    def __init__(self, on_select, **kwargs):
        super().__init__(text=theme.rtl('همه تاریخ‌ها · میلادی'), **kwargs)
        self.selected = None
        self.on_select = on_select
        self.bind(on_release=self._open)

    def _open(self, *_):
        current = self.selected or date.today()
        self._month = current.replace(day=1)
        root = BoxLayout(orientation='vertical', spacing=8, padding=10)
        nav = BoxLayout(size_hint_y=None, height=40)
        for text, direction in [('<', -1), ('>', 1)]:
            button = SecondaryButton(text=text)
            button.bind(on_release=lambda _, d=direction: self._move(d))
            nav.add_widget(button)
        self._heading = RTLLabel(halign='center')
        nav.add_widget(self._heading)
        root.add_widget(nav)
        self._grid = GridLayout(cols=7, spacing=4)
        root.add_widget(self._grid)
        clear = SecondaryButton(text=theme.rtl('همه تاریخ‌ها'), size_hint_y=None, height=40)
        clear.bind(on_release=lambda *_: self._select(None))
        root.add_widget(clear)
        self._popup = Popup(title=theme.rtl('انتخاب تاریخ میلادی'), title_font=theme.APP_FONT_NAME,
                            content=root, size_hint=(None, None), size=(420, 410))
        self._render()
        self._popup.open()

    def _move(self, direction):
        month = self._month.year*12 + self._month.month-1 + direction
        self._month = date(month//12, month%12+1, 1)
        self._render()

    def _render(self):
        self._heading.set_text(self._month.strftime('%Y-%m')+' · میلادی')
        self._grid.clear_widgets()
        for label in ['د', 'س', 'چ', 'پ', 'ج', 'ش', 'ی']:
            self._grid.add_widget(RTLLabel(text=label, halign='center'))
        for week in calendar.monthcalendar(self._month.year, self._month.month):
            for day in week:
                button = SecondaryButton(text=str(day) if day else '', disabled=not day)
                button.bind(on_release=lambda _, d=day: self._select(self._month.replace(day=d)))
                self._grid.add_widget(button)

    def set_date(self, value):
        self.selected = value
        self.text = theme.rtl(f'{value.isoformat()} · میلادی' if value else 'همه تاریخ‌ها · میلادی')
        self.on_select(value)

    def _select(self, value):
        self.set_date(value)
        self._popup.dismiss()
