"""Generate a diagnostic document off the UI thread and open it locally."""
from threading import Thread
from pathlib import Path, PureWindowsPath
import platform
import shutil
import subprocess
import webbrowser

from kivy.clock import Clock
from kivy.uix.popup import Popup

from plakino_ui.services.auth_service import auth_service
from plakino_ui.services.diagnostic_report_service import diagnostic_report_service, eligible
from plakino_ui.ui import theme
from plakino_ui.ui.components.common import Card, RTLLabel, SecondaryButton


def open_document(path):
    path = path.resolve()
    if 'microsoft' not in platform.release().lower():
        return webbrowser.open(path.as_uri())
    # gio/xdg-open can claim success before failing in WSL. Explorer also
    # depends on file associations. Launch an installed browser with a Windows
    # file URI directly, including UNC paths and escaped spaces.
    converter = shutil.which('wslpath')
    browser = shutil.which('msedge.exe') or shutil.which('chrome.exe')
    if not browser:
        browser = next((str(candidate) for candidate in (
            Path('/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'),
            Path('/mnt/c/Program Files/Microsoft/Edge/Application/msedge.exe'),
            Path('/mnt/c/Program Files/Google/Chrome/Application/chrome.exe'),
        ) if candidate.is_file()), None)
    if not converter or not browser:
        return False
    windows_path = subprocess.run([converter, '-w', str(path)], check=True,
                                 capture_output=True, text=True, timeout=3).stdout.strip()
    if not windows_path:
        return False
    process = subprocess.Popen([browser, PureWindowsPath(windows_path).as_uri()],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        return process.wait(timeout=1) == 0
    except subprocess.TimeoutExpired:
        # A newly started browser remains alive; an existing browser normally
        # accepts the URL and exits the launcher immediately.
        return True


class DiagnosticReportDialog(Popup):
    def __init__(self, record, **kwargs):
        self.record = record
        self._session = auth_service.session_version
        self._closed = False
        self.document = None
        content = Card(orientation='vertical', padding=22, spacing=12)
        content.add_widget(RTLLabel(text='گزارش تشخیص', font_size=20, size_hint_y=None, height=36))
        self.message = RTLLabel(text='در حال آماده‌سازی تصاویر و خوانش‌ها…', halign='center')
        content.add_widget(self.message)
        self.open_button = SecondaryButton(text=theme.rtl('باز کردن گزارش'), size_hint_y=None, height=38, disabled=True)
        self.open_button.bind(on_release=self._open_document)
        content.add_widget(self.open_button)
        close = SecondaryButton(text=theme.rtl('بستن'), size_hint_y=None, height=38)
        content.add_widget(close)
        super().__init__(title='', separator_height=0, background='', background_color=(0, 0, 0, 0),
                         content=content, size_hint=(.75, None), height=320, **kwargs)
        close.bind(on_release=lambda *_: self.dismiss())

    def _allowed(self):
        return (not self._closed and auth_service.is_superadmin
                and auth_service.session_version == self._session and eligible(self.record))

    def on_open(self):
        if not self._allowed():
            self.dismiss()
            return
        def work():
            path, error = None, ''
            try:
                path = diagnostic_report_service.prepare(self.record)
            except (PermissionError, FileNotFoundError, ValueError) as exc:
                error = str(exc)
            except Exception:
                error = 'ساخت گزارش انجام نشد؛ دسترسی به آرشیو و فضای ذخیره‌سازی را بررسی کنید'
            Clock.schedule_once(lambda _: self._ready(path, error))
        Thread(target=work, name='diagnostic-document', daemon=True).start()

    def on_dismiss(self):
        self._closed = True

    def _ready(self, path, error):
        if not self._allowed():
            return
        if error:
            self.message.set_text(error)
            return
        self.document = path
        self.open_button.disabled = False
        self.message.set_text('گزارش همراه تصاویر آماده است و در مرورگر باز می‌شود. برای PDF از چاپ مرورگر استفاده کنید.')
        self._open_document()

    def _open_document(self, *_):
        if not self._allowed() or self.document is None:
            return
        try:
            opened = open_document(self.document)
        except Exception:
            opened = False
        if not opened:
            self.message.set_text(f'مرورگر باز نشد. سند در این مسیر ذخیره شده است:\n{self.document}')
