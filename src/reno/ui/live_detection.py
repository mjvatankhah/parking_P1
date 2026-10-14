"""Live frames annotated by the recognition pipeline."""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen

from reno.services.camera_service import camera_service
from reno.ui.components.camera_card import CameraCard
from reno.ui.components.common import EmptyState
from reno.ui.components.page_shell import PageShell


class LiveDetectionScreen(Screen):
    def __init__(self, on_navigate=None, **kwargs):
        super().__init__(**kwargs)
        self.on_navigate = on_navigate
        self._active = False
        self._cards = {}
        self._holder = BoxLayout(orientation='vertical')
        self.add_widget(PageShell(
            'تشخیص زنده', 'live_detection', self._holder, self._navigate,
            subtitle='تصویر پردازش‌شده با کادر اشیای تشخیص‌داده‌شده',
        ))
        camera_service.subscribe(self._on_cameras_changed)
        self._show_cameras(camera_service.get_cameras())

    def on_enter(self, *_args):
        self._active = True
        for card in self._cards.values():
            card.ensure_stream_started()

    def on_leave(self, *_args):
        self._active = False
        for card in self._cards.values():
            card.stop_stream()

    def _navigate(self, key):
        if self.on_navigate:
            self.on_navigate(key)

    def _on_cameras_changed(self, cameras):
        self._show_cameras(cameras)

    def _show_cameras(self, cameras):
        for card in self._cards.values():
            card.stop_stream()
        self._cards.clear()
        self._holder.clear_widgets()
        if not cameras:
            self._holder.add_widget(EmptyState(
                icon_name='camera', title='هنوز دوربینی تنظیم نشده است',
                subtitle='منبع تصویر را در تنظیمات دوربین اضافه کنید',
                action_text='رفتن به تنظیمات',
                on_action=lambda: self._navigate('camera_settings'),
            ))
            return

        grid = GridLayout(cols=1 if len(cameras) == 1 else 2,
                          size_hint_y=None, spacing=12)
        grid.bind(minimum_height=grid.setter('height'))
        for camera in cameras:
            card = CameraCard(camera, size_hint_y=None, height=320)
            self._cards[camera.id] = card
            grid.add_widget(card)
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(grid)
        self._holder.add_widget(scroll)
        if self._active:
            for card in self._cards.values():
                card.ensure_stream_started()
