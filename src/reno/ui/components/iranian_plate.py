"""Render Iranian plate segments in physical order, independent of page RTL."""
import re
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from reno.ui import theme
from reno.ui.components.common import Card, RTLLabel


def plate_segments(text):
    """Return left digits, letter, serial and optional region; never invent digits."""
    compact = re.sub(r'[\s\-\u200c]', '', text or '')
    match = re.fullmatch(r'(\d{2})([ء-غف-يپچژکگۀهی]+)(\d{3})(\d{2})?', compact)
    return match.groups() if match else None


class IranianPlate(Card):
    def __init__(self, text, **kwargs):
        kwargs.setdefault('size_hint_y', None)
        kwargs.setdefault('height', 32)
        kwargs.setdefault('padding', 2)
        kwargs.setdefault('hover_effect', False)
        kwargs.setdefault('border_color', theme.rgba('#B6C6D1'))
        kwargs.setdefault('spacing', 1)
        kwargs.setdefault('radius', 5)
        kwargs.setdefault('bg_color', theme.rgba('#D8E5ED'))
        super().__init__(**kwargs)
        segments = plate_segments(text)
        if not segments:
            self.add_widget(RTLLabel(text=text or 'پلاک خوانده نشد', font_size=12,
                                     color=theme.rgba('#122038'), halign='center'))
            return
        left, letter, serial, region = segments
        flag = Card(size_hint_x=None, width=12, radius=2, padding=0,
                    bg_color=theme.rgba('#1554A0'))
        flag.add_widget(Label(text='IR', font_size=6, color=(1, 1, 1, 1)))
        self.add_widget(flag)
        for segment in (left, letter, serial):
            self.add_widget(RTLLabel(text=segment, font_size=12, bold=True,
                                     padding=[0, 0], halign='center', color=theme.rgba('#122038')))
        if region:
            box = BoxLayout(orientation='vertical', size_hint_x=.8)
            box.add_widget(RTLLabel(text='ایران', font_size=6, halign='center', padding=[0, 0],
                                     color=theme.rgba('#122038')))
            box.add_widget(RTLLabel(text=region, font_size=12, bold=True, halign='center',
                                     padding=[0, 0], color=theme.rgba('#122038')))
            self.add_widget(box)


class PlainPlate(BoxLayout):
    """Plain, physically ordered plate segments immune to surrounding RTL bidi."""
    def __init__(self, text, **kwargs):
        kwargs.setdefault('spacing', 2)
        super().__init__(**kwargs)
        segments = plate_segments(text)
        self.segments = segments
        if not segments:
            self.add_widget(RTLLabel(text=text or '—', font_size=13, halign='center', padding=[0,0]))
            return
        left, letter, serial, region = segments
        parts = [(left, 2), (letter, 1.3), (serial, 3)]
        if region:
            parts.extend([('|', .5), (region, 2)])
        for part, width in parts:
            self.add_widget(RTLLabel(text=theme.fa_number(part), font_size=15, bold=part!='|',
                size_hint_x=width, halign='center', padding=[0,0],
                color=theme.rgba(theme.COLORS['text_secondary'] if part=='|' else theme.COLORS['text_primary'])))
