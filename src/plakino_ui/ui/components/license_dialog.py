"""Offline activation through the backend; file operations never block Kivy."""
import json
from datetime import datetime
from pathlib import Path
from threading import Thread

from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup

from computer_vision_v2.runtime.control import BackendClient
from computer_vision_v2.site_time import TEHRAN
from plakino_ui.ui import theme
from plakino_ui.ui.components.common import RTLLabel, SecondaryButton

MESSAGES = {
    'device_unavailable': 'شناسه‌های پایدار دستگاه در دسترس نیست؛ با پشتیبانی تماس بگیرید',
    'valid': 'لایسنس فعال است', 'missing': 'لایسنس وارد نشده است',
    'expired': 'لایسنس منقضی شده؛ فایل تمدید را وارد کنید',
    'clock_rollback': 'ساعت سیستم عقب رفته؛ تاریخ و ساعت صحیح را تنظیم کنید',
    'not_yet_valid': 'زمان شروع اعتبار نرسیده؛ ساعت سیستم را بررسی کنید',
    'wrong_device': 'این لایسنس متعلق به دستگاه دیگری است',
    'invalid': 'فایل لایسنس معتبر نیست',
    'issuer_not_configured': 'کلید صادرکننده نصب نشده؛ با پشتیبانی تماس بگیرید',
    'state_invalid': 'سابقهٔ لایسنس ناقص یا دست‌کاری شده؛ با پشتیبانی تماس بگیرید',
    'storage_error': 'خطا در ذخیرهٔ لایسنس؛ دسترسی فایل‌ها را بررسی کنید',
}


def license_message(status):
    message = MESSAGES.get(status.get('code'), 'وضعیت لایسنس در دسترس نیست')
    if status.get('expires_at'):
        end = datetime.fromtimestamp(status['expires_at'], TEHRAN).strftime('%Y-%m-%d %H:%M')
        message += f' | پایان اعتبار: {end}'
    return message


class LicenseDialog(Popup):
    def __init__(self, client=None, **kwargs):
        self.client = client or BackendClient(timeout=15)
        self.busy = False
        panel = BoxLayout(orientation='vertical', padding=16, spacing=10)
        panel.add_widget(RTLLabel(text='درخواست دستگاه را ذخیره و برای صادرکننده ارسال کنید؛ سپس فایل دریافتی را انتخاب و وارد کنید.',
                                  size_hint_y=None, height=60, font_size=14))
        self.status = RTLLabel(text='در حال دریافت وضعیت…', size_hint_y=None, height=64, font_size=13)
        panel.add_widget(self.status)
        self.chooser = FileChooserListView(path=str(Path.home()), filters=['*.json', '*.plakino'])
        panel.add_widget(self.chooser)
        actions = BoxLayout(size_hint_y=None, height=46, spacing=8)
        self.export_button = SecondaryButton(text=theme.rtl('ذخیره درخواست در این پوشه'))
        self.import_button = SecondaryButton(text=theme.rtl('ورود فایل لایسنس'))
        close = SecondaryButton(text=theme.rtl('بستن'))
        self.export_button.bind(on_release=self._export)
        self.import_button.bind(on_release=self._import)
        close.bind(on_release=lambda *_: self.dismiss())
        for button in (self.export_button, self.import_button, close):
            actions.add_widget(button)
        panel.add_widget(actions)
        super().__init__(title=theme.rtl('فعال‌سازی آفلاین'), title_font=theme.APP_FONT_NAME,
                         title_align='right', content=panel, size_hint=(.9, .85), **kwargs)
        self._work(self._load_status)

    def _load_status(self):
        self.client.ensure_host()
        return license_message(self.client.status().get('license', {}))

    def _work(self, operation):
        if self.busy:
            return
        self.busy = True
        self.export_button.disabled = self.import_button.disabled = True
        def work():
            try:
                message = operation()
            except FileExistsError:
                message = 'فایل درخواست در این پوشه وجود دارد؛ پوشهٔ دیگری انتخاب کنید'
            except Exception:
                message = 'عملیات انجام نشد؛ فایل، دسترسی پوشه و ارتباط با بک‌اند را بررسی کنید'
            Clock.schedule_once(lambda _: self._done(message), 0)
        Thread(target=work, name='license-ui', daemon=True).start()

    def _done(self, message):
        self.busy = False
        self.export_button.disabled = self.import_button.disabled = False
        self.status.set_text(message)
        self.chooser._update_files()

    def _export(self, *_):
        directory = Path(self.chooser.path)
        def export():
            request = self.client.license_request()
            path = directory / ('device-request-' + request['device_id'][:12] + '.json')
            with path.open('x', encoding='utf-8') as stream:
                json.dump(request, stream, indent=2)
            return 'درخواست دستگاه ذخیره شد: ' + path.name
        self._work(export)

    def _import(self, *_):
        if not self.chooser.selection:
            self.status.set_text('ابتدا فایل لایسنس را انتخاب کنید')
            return
        path = Path(self.chooser.selection[0])
        def install():
            with path.open('rb') as stream:
                raw = stream.read(65537)
            if len(raw) > 65536:
                return MESSAGES['invalid']
            return license_message(self.client.install_license(json.loads(raw)))
        self._work(install)
