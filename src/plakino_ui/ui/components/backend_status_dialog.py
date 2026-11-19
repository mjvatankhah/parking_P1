"""Live processing details with a fixed header and stable, scrollable camera cards."""
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from plakino_ui.ui import theme
from plakino_ui.ui.components.app_header import _WindowButton
from plakino_ui.ui.components.common import Card, Divider, RTLLabel

STATES = {'stopped': 'پردازش متوقف است', 'starting': 'در حال راه‌اندازی پردازش',
          'running': 'پردازش فعال است', 'stopping': 'در حال توقف و ذخیرهٔ نتایج',
          'error': 'خطای پردازش؛ جزئیات را بررسی کنید',
          'unavailable': 'ارتباط با پردازش برقرار نیست'}
CAMERA_STATES = {'processing': 'در حال پردازش', 'disconnected': 'قطع اتصال دوربین',
                 'no_frames': 'تصویری دریافت نمی‌شود', 'stalled': 'پردازش فریم پیشرفت ندارد',
                 'waiting': 'در انتظار فریم', 'ended': 'پایان فایل ویدیو', 'error': 'خطای دوربین'}
BAD_STATES = {'disconnected', 'no_frames', 'stalled', 'error'}


def state_color(state):
    key = ('offline' if state in BAD_STATES or state == 'unavailable' else
           'online' if state in ('running', 'processing') else
           'warning' if state in ('starting', 'stopping', 'waiting') else 'text_secondary')
    return theme.rgba(theme.COLORS[key])


class CameraStatusCard(Card):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', size_hint_y=None, height=116,
                         padding=[14, 8], spacing=2, hover_effect=False,
                         bg_color=theme.rgba(theme.COLORS['surface_alt']), **kwargs)
        self.heading = RTLLabel(font_size=14, bold=True)
        self.metrics = RTLLabel(font_size=13, color=theme.rgba(theme.COLORS['text_secondary']))
        self.age = RTLLabel(font_size=12, color=theme.rgba(theme.COLORS['text_secondary']))
        for label in (self.heading, self.metrics, self.age):
            self.add_widget(label)

    def update(self, camera, backend_state):
        state = camera.get('state', 'waiting')
        if backend_state != 'running':
            state = backend_state
        status = CAMERA_STATES.get(state, STATES.get(state, state))
        self.heading.set_text(f"{camera['id']}  ·  {status}")
        self.heading.color = state_color(state)
        self.metrics.set_text(
            f"دریافت: {theme.fa_number(camera.get('received', 0))}   |   "
            f"پردازش: {theme.fa_number(camera.get('processed', 0))}   |   "
            f"نرخ: {theme.fa_number(camera.get('fps', 0))} فریم/ثانیه")
        age = camera.get('processed_age')
        age_text = 'هنوز پردازش نشده' if age is None else f'{theme.fa_number(int(age))} ثانیه پیش'
        self.age.set_text(f'آخرین پردازش: {age_text}')


class BackendStatusDialog(Popup):
    def __init__(self, **kwargs):
        super().__init__(title='', separator_height=0, background='',
                         background_color=(0, 0, 0, 0), size_hint=(None, None),
                         auto_dismiss=False, **kwargs)
        panel = Card(orientation='vertical', padding=20, spacing=12,
                     radius=16, hover_effect=False)
        header = BoxLayout(size_hint_y=None, height=38, spacing=12)
        self.close_button = _WindowButton('×', self.dismiss, danger=True, size=(38, 38))
        header.add_widget(self.close_button)
        header.add_widget(RTLLabel(text='وضعیت پردازش', font_size=20, bold=True))
        panel.add_widget(header)
        panel.add_widget(Divider())
        self.summary = RTLLabel(size_hint_y=None, height=34, font_size=16, bold=True)
        panel.add_widget(self.summary)
        self.description = RTLLabel(size_hint_y=None, height=40, font_size=12,
                                    color=theme.rgba(theme.COLORS['text_secondary']))
        panel.add_widget(self.description)
        self.rows = BoxLayout(orientation='vertical', size_hint_y=None, spacing=10, padding=[0, 2, 8, 2])
        self.rows.bind(minimum_height=self.rows.setter('height'))
        self.scroll = ScrollView(do_scroll_x=False, bar_width=4, scroll_type=['bars', 'content'])
        self.scroll.add_widget(self.rows)
        panel.add_widget(self.scroll)
        panel.add_widget(Divider())
        panel.add_widget(RTLLabel(text='بستن این پنجره، پردازش را متوقف نمی‌کند.\n'
                                 'تغییر تنظیمات دوربین با توقف و اجرای مجدد اعمال می‌شود.',
                                 size_hint_y=None, height=64, font_size=12,
                                 color=theme.rgba(theme.COLORS['text_secondary'])))
        self.content = panel
        self._camera_cards = {}
        self._camera_ids = None
        self._fit_window()

    def _fit_window(self, *_):
        self.size = (min(720, Window.width - 40), min(620, Window.height - 48))

    def on_open(self):
        Window.bind(size=self._fit_window)
        self._fit_window()

    def on_dismiss(self):
        Window.unbind(size=self._fit_window)

    def update(self, snapshot):
        state = snapshot['state']
        cameras = snapshot.get('cameras', [])
        self.summary.set_text(STATES.get(state, state))
        self.summary.color = state_color(state)
        if state == 'error':
            description = 'پردازش با خطا متوقف شد؛ برای تلاش مجدد ابتدا توقف را بزنید.'
        elif state == 'unavailable':
            description = 'وضعیت در دسترس نیست؛ برای راه‌اندازی یا اتصال دوباره، اجرا را بزنید.'
        elif state in ('starting', 'stopping'):
            description = 'لطفاً صبر کنید؛ وضعیت به‌صورت خودکار به‌روز می‌شود.'
        else:
            active = sum(c.get('state') == 'processing' for c in cameras) if state == 'running' else 0
            description = (f'{theme.fa_number(active)} از {theme.fa_number(len(cameras))} دوربین در حال پردازش'
                           '  ·  به‌روزرسانی خودکار')
        self.description.set_text(description)
        ids = tuple(str(camera['id']) for camera in cameras)
        if ids != self._camera_ids:
            self.rows.clear_widgets()
            self._camera_cards = {key: self._camera_cards.get(key) or CameraStatusCard() for key in ids}
            for key in ids:
                self.rows.add_widget(self._camera_cards[key])
            if not ids:
                self.rows.add_widget(RTLLabel(text='هنوز اطلاعاتی از دوربین‌ها دریافت نشده است.',
                                             halign='center', size_hint_y=None, height=100,
                                             color=theme.rgba(theme.COLORS['text_secondary'])))
            self._camera_ids = ids
        for camera in cameras:
            self._camera_cards[str(camera['id'])].update(camera, state)
