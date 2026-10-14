"""Recent-event presentation and detail dialog share the same event and plate image."""
from pathlib import Path
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.widget import Widget
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.image import Image
from kivy.uix.popup import Popup
from kivy.animation import Animation
from reno.ui import theme
from reno.ui.components.common import Card, RTLLabel, SecondaryButton, HoverBehavior
from reno.ui.components.iranian_plate import PlainPlate
from reno.ui.components.jalali_calendar import jalali_text


class TrafficRecordRow(HoverBehavior, ButtonBehavior, Card):
    def __init__(self, record, **kwargs):
        self.record = record
        super().__init__(size_hint_y=None, height=56, padding=[8, 8, 8, 8], spacing=8,
                         radius=5, bg_color=theme.rgba('#202832', .7),
                         border_color=theme.rgba(theme.COLORS['border'], .45), hover_effect=False, **kwargs)
        self.image_path = record.image_path if record.image_path and Path(record.image_path).is_file() else ''
        # Physical left-to-right insertion gives an RTL grid with image at far right.
        self._camera = RTLLabel(text=record.camera, font_size=11, halign='center',
                               padding=[0,0], size_hint_x=.14, shorten=True,
                               color=theme.rgba(theme.COLORS['text_secondary']))
        self.add_widget(self._camera)
        stamp = BoxLayout(orientation='vertical', spacing=1, size_hint_x=.22)
        self._date_label = RTLLabel(text=jalali_text(record.date), font_size=13, halign='center', padding=[0,0])
        stamp.add_widget(self._date_label)
        stamp.add_widget(RTLLabel(text=theme.fa_number(record.time), font_size=13, halign='center',
                                 padding=[0,0], color=theme.rgba(theme.COLORS['text_secondary'])))
        self.add_widget(stamp)
        event_color = 'entry' if record.direction == 'entry' else 'exit'
        self._event_label = RTLLabel(text=record.direction_label(), font_size=13,
                                     size_hint_x=.12,
                                     color=theme.rgba(theme.COLORS[event_color+'_text']),
                                     halign='center', padding=[0,0])
        self.add_widget(self._event_label)
        self._plate = PlainPlate(record.plate, size_hint_x=.26)
        self.add_widget(self._plate)
        self._thumbnail = Card(size_hint_x=.26, padding=1, radius=4, hover_effect=False,
            bg_color=theme.rgba(theme.COLORS['background']), border_color=theme.rgba(theme.COLORS['border'],.5))
        if self.image_path:
            image_holder = AnchorLayout()
            self._plate_image = Image(source=self.image_path, fit_mode='scale-down',
                                      size_hint=(None, None))
            def fit_thumbnail(holder, *_):
                self._plate_image.size = (min(160, max(0, holder.width)),
                                          min(40, max(0, holder.height)))
            image_holder.bind(size=fit_thumbnail)
            image_holder.add_widget(self._plate_image)
            fit_thumbnail(image_holder)
            self._thumbnail.add_widget(image_holder)
        else:
            self._thumbnail.add_widget(RTLLabel(text='بدون تصویر', font_size=10, halign='center', padding=[0,0],
                                                color=theme.rgba(theme.COLORS['text_secondary'])))
        self.add_widget(self._thumbnail)
        self.bind(hovered=self._hover, on_release=self._open_detail)

    def _hover(self, *_):
        Animation.cancel_all(self, 'bg_color', 'border_color')
        Animation(bg_color=theme.rgba('#293545', 1) if self.hovered else theme.rgba('#202832', .8),
                  border_color=theme.rgba('#45566C', .9) if self.hovered else (0, 0, 0, 0),
                  duration=.12).start(self)

    def _open_detail(self, *_):
        content = Card(orientation='vertical', padding=22, spacing=12, bg_color=theme.rgba('#191F27'))
        content.add_widget(RTLLabel(text='جزئیات رویداد تردد', font_size=19, size_hint_y=None, height=32))
        if self.image_path:
            content.add_widget(Image(source=self.image_path, fit_mode='contain'))
        else:
            content.add_widget(RTLLabel(text='تصویری برای این رویداد ثبت نشده است', halign='center'))
        if self.record.class_id != 0:
            content.add_widget(PlainPlate(self.record.plate))
        for text in [f'{self.record.class_label()} · {self.record.direction_label()}',
                     f'{jalali_text(self.record.date)}  ·  {theme.fa_number(self.record.time)}', self.record.camera]:
            content.add_widget(RTLLabel(text=text, font_size=13, size_hint_y=None, height=28))
        close = SecondaryButton(text=theme.rtl('بستن'), size_hint_y=None, height=38)
        content.add_widget(close)
        self.detail_dialog = Popup(title='', separator_height=0, background='', background_color=(0, 0, 0, 0),
                                   content=content, size_hint=(None, None), size=(460, 450))
        close.bind(on_release=lambda *_: self.detail_dialog.dismiss())
        self.detail_dialog.open()


def detection_header():
    row = BoxLayout(size_hint_y=None, height=26, padding=[8,0,8,0], spacing=8)
    for label, ratio in [('دوربین',.14),('تاریخ / ساعت',.22),('رویداد',.12),('شماره پلاک',.26),('تصویر',.26)]:
        row.add_widget(RTLLabel(text=label, font_size=10, size_hint_x=ratio, halign='center',
                               padding=[0,0], color=theme.rgba(theme.COLORS['text_secondary'])))
    return row
