"""Recent-event presentation and detail dialog share the same event and plate image."""
from pathlib import Path
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.image import Image
from kivy.uix.popup import Popup
from kivy.animation import Animation
from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.ui.components.common import Card, RTLLabel, SecondaryButton, HoverBehavior
from computer_vision_v2.reno.ui.components.iranian_plate import IranianPlate


class TrafficRecordRow(HoverBehavior, ButtonBehavior, Card):
    def __init__(self, record, **kwargs):
        self.record = record
        super().__init__(size_hint_y=None, height=88, padding=[9, 10, 9, 10], spacing=11,
                         radius=6, bg_color=theme.rgba('#202832', .8),
                         border_color=(0, 0, 0, 0), hover_effect=False, **kwargs)
        self.image_path = record.image_path if record.image_path and Path(record.image_path).is_file() else ''
        if self.image_path:
            self.add_widget(Image(source=self.image_path, size_hint_x=None, width=61, fit_mode='contain'))
        else:
            self.add_widget(RTLLabel(text='بدون تصویر', font_size=11, halign='center',
                size_hint_x=None, width=61, color=theme.rgba(theme.COLORS['text_secondary']), padding=[0, 0]))
        details = BoxLayout(orientation='vertical', spacing=4)
        top = BoxLayout(size_hint_y=None, height=34, spacing=4)
        direction = record.direction_label()
        self._event_label = RTLLabel(text=f'{record.class_label()} · {direction}', font_size=11,
            color=theme.rgba(theme.COLORS['online'] if record.direction == 'entry' else '#91B4DF'),
            halign='left', padding=[0, 0], size_hint_x=None, width=78)
        top.add_widget(self._event_label)
        top.add_widget(Widget())
        self._plate = (IranianPlate(record.plate, size_hint_x=None, width=174, height=32)
                       if record.class_id != 0 else RTLLabel(text='انسان', font_size=13, padding=[0, 0]))
        top.add_widget(self._plate)
        if record.class_id != 0:
            top.bind(width=lambda w, width: setattr(self._plate, 'width', min(174, max(110, width-82))))
        details.add_widget(top)
        bottom = BoxLayout(size_hint_y=None, height=24, spacing=4)
        bottom.add_widget(RTLLabel(text=theme.fa_number(record.time), halign='left', font_size=11,
                                  color=theme.rgba(theme.COLORS['text_secondary']), padding=[0, 0]))
        bottom.add_widget(RTLLabel(text=record.camera, font_size=11,
                                  color=theme.rgba(theme.COLORS['text_secondary']), padding=[0, 0]))
        details.add_widget(bottom)
        self.add_widget(details)
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
            content.add_widget(IranianPlate(self.record.plate))
        for text in [f'{self.record.class_label()} · {self.record.direction_label()}',
                     f'{self.record.date}  ·  {self.record.time}', self.record.camera]:
            content.add_widget(RTLLabel(text=text, font_size=13, size_hint_y=None, height=28))
        close = SecondaryButton(text=theme.rtl('بستن'), size_hint_y=None, height=38)
        content.add_widget(close)
        self.detail_dialog = Popup(title='', separator_height=0, background='', background_color=(0, 0, 0, 0),
                                   content=content, size_hint=(None, None), size=(460, 450))
        close.bind(on_release=lambda *_: self.detail_dialog.dismiss())
        self.detail_dialog.open()
