"""Shared processing controls and persistent per-camera fault visibility."""
import logging
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout

from plakino_ui.services.auth_service import auth_service
from plakino_ui.ui.components.common import RTLLabel, SecondaryButton
from plakino_ui.ui.components.backend_status_dialog import (
    BackendStatusDialog, STATES, CAMERA_STATES, BAD_STATES,
)
from plakino_ui.ui import theme

logger = logging.getLogger(__name__)


class BackendBar(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=44, spacing=10, **kwargs)
        self.snapshot = dict(state='unavailable', cameras=[])
        self.start_button = SecondaryButton(text=theme.rtl('اجرا'), size_hint_x=None, width=92,
            bg_color_normal=theme.rgba('#216345'), bg_color_hover=theme.rgba('#2B7B56'),
            bg_color_down=theme.rgba('#194D35'), border_color=theme.rgba(theme.COLORS['entry_border']),
            color=theme.rgba(theme.COLORS['text_on_primary']))
        self.stop_button = SecondaryButton(text=theme.rtl('توقف'), size_hint_x=None, width=92,
            bg_color_normal=theme.rgba('#923D49'), bg_color_hover=theme.rgba('#A94B58'),
            bg_color_down=theme.rgba('#78323C'), border_color=theme.rgba(theme.COLORS['exit_border']),
            color=theme.rgba(theme.COLORS['text_on_primary']))
        self.details_button = SecondaryButton(text=theme.rtl('وضعیت'), size_hint_x=None, width=88,
            bg_color_normal=theme.rgba(theme.COLORS['action']), bg_color_hover=theme.rgba(theme.COLORS['action_hover']),
            bg_color_down=theme.rgba(theme.COLORS['primary_dark']), border_color=theme.rgba(theme.COLORS['action']),
            color=theme.rgba(theme.COLORS['text_on_primary']))
        self.label = RTLLabel(text='', font_size=12)
        self.add_widget(self.start_button)
        self.add_widget(self.stop_button)
        self.add_widget(self.details_button)
        self.add_widget(self.label)
        self.start_button.bind(on_release=lambda *_: self._command('start'))
        self.stop_button.bind(on_release=lambda *_: self._command('stop'))
        self.details_button.bind(on_release=self._details)
        self._popup = None
        self.update(self.snapshot)

    def _command(self, action):
        button = self.start_button if action == 'start' else self.stop_button
        if button.disabled:
            return
        app = App.get_running_app()
        if auth_service.current_role and app is not None:
            app.backend_monitor.command(action)

    def update(self, snapshot, busy=False):
        self.snapshot = snapshot
        state = snapshot['state']
        cameras = snapshot.get('cameras', [])
        message = STATES.get(state, state)
        bad = [c for c in cameras if c['state'] in BAD_STATES] if state == 'running' else []
        if bad:
            message = f"{bad[0]['id']}: {CAMERA_STATES[bad[0]['state']]}"
            if len(bad) > 1:
                message += f' (+{len(bad)-1})'
        elif state == 'running':
            count = sum(c['state'] == 'processing' for c in cameras)
            message += f' — {count}/{len(cameras)} دوربین در حال پردازش'
        self.label.set_text(message)
        self.label.color = theme.rgba(theme.COLORS['offline' if bad or state in ('error', 'unavailable') else 'text_primary'])
        signed_in = bool(auth_service.current_role)
        self.start_button.disabled = busy or not signed_in or state not in ('stopped', 'unavailable')
        self.stop_button.disabled = busy or not signed_in or state not in ('running', 'starting', 'error')
        self.start_button.text = theme.rtl('راه‌اندازی…' if state == 'starting' else 'اجرا')
        self.stop_button.text = theme.rtl('توقف…' if state == 'stopping' else 'توقف')
        if self._popup is not None:
            self._refresh_details()

    def _details(self, *_):
        if self._popup is not None:
            return
        popup = None
        try:
            popup = BackendStatusDialog()
            popup.update(self.snapshot)
            popup.bind(on_dismiss=self._dismissed)
            popup.open()
        except Exception:
            logger.exception('Cannot open backend status dialog')
            if popup is not None:
                popup.dismiss(animation=False)
            self.label.set_text('نمایش وضعیت انجام نشد؛ دوباره تلاش کنید')
            return
        self._popup = popup
        self._rows = popup.rows

    def _dismissed(self, *_):
        self._popup = None

    def _refresh_details(self):
        self._popup.update(self.snapshot)
