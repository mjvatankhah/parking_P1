"""A local, explicitly symbolic ticket interaction; no external submission."""
from itertools import count
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.ui.components.common import Card, RTLLabel, RoundedTextInput, PrimaryButton, SecondaryButton

_RECEIPTS = count(1)


class TicketDialog(Popup):
    def __init__(self, **kwargs):
        super().__init__(title='', separator_height=0, background='', background_color=(0, 0, 0, 0),
                         size_hint=(None, None), size=(500, 480), auto_dismiss=False, **kwargs)
        self.receipt = None
        panel = Card(orientation='vertical', padding=24, spacing=10,
                     bg_color=theme.rgba(theme.COLORS['surface']), hover_effect=False)
        panel.add_widget(RTLLabel(text='ثبت تیکت', font_size=20, size_hint_y=None, height=32))
        panel.add_widget(RTLLabel(text='ثبت نمایشی؛ تیکت برای پشتیبانی ارسال نمی‌شود.', font_size=11,
                                 color=theme.rgba(theme.COLORS['text_secondary']), size_hint_y=None, height=28))
        self.subject = RoundedTextInput(hint_text=theme.rtl('موضوع تیکت'), halign='right',
                                        size_hint_y=None, height=44)
        self.description = RoundedTextInput(hint_text=theme.rtl('شرح درخواست…'), multiline=True,
                                            halign='right', size_hint_y=None, height=132)
        panel.add_widget(self.subject)
        panel.add_widget(self.description)
        self.status = RTLLabel(text='', font_size=12, size_hint_y=None, height=42)
        panel.add_widget(self.status)
        buttons = BoxLayout(size_hint_y=None, height=42, spacing=10)
        close = SecondaryButton(text=theme.rtl('بستن'))
        close.bind(on_release=lambda *_: self.dismiss())
        self.submit_button = PrimaryButton(text=theme.rtl('ثبت تیکت'))
        self.submit_button.bind(on_release=self.submit)
        buttons.add_widget(close)
        buttons.add_widget(self.submit_button)
        panel.add_widget(buttons)
        self.content = panel

    def submit(self, *_):
        if self.receipt:
            return False
        if not self.subject.text.strip() or not self.description.text.strip():
            self.status.color = theme.rgba(theme.COLORS['warning'])
            self.status.set_text('موضوع و شرح درخواست را وارد کنید.')
            return False
        self.receipt = f'DEMO-{next(_RECEIPTS):04d}'
        self.status.color = theme.rgba(theme.COLORS['online'])
        self.status.set_text(f'تیکت نمایشی ثبت شد · {self.receipt}')
        self.submit_button.disabled = True
        self.subject.readonly = self.description.readonly = True
        self.subject.text = theme.rtl(self.subject.text)
        self.description.text = theme.rtl(self.description.text)
        return True
