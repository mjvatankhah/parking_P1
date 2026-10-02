"""Multi-camera monitoring of unprocessed file and RTSP frames."""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen
from kivy.uix.togglebutton import ToggleButton

from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.ui.components.page_shell import PageShell
from computer_vision_v2.reno.ui.theme import COLORS, SPACING
from computer_vision_v2.reno.ui.components.common import (
    Card, RTLLabel, EmptyState, SecondaryButton,
)
from computer_vision_v2.reno.ui.components.raw_camera_card import RawCameraCard
from computer_vision_v2.reno.services.camera_service import camera_service


class CamerasScreen(Screen):
    def __init__(self, on_navigate=None, **kwargs):
        super().__init__(**kwargs)
        self.on_navigate = on_navigate
        self._selected = {camera.id for camera in camera_service.get_cameras()}
        self._cards = {}
        self._active = False
        content = BoxLayout(orientation='vertical', padding=0,
                            spacing=SPACING['md'])
        panel = Card(orientation='vertical', padding=SPACING['md'],
                     spacing=SPACING['sm'])
        panel.add_widget(RTLLabel(text='مانیتورینگ دوربین‌ها',
                                  size_hint_y=None, height=32, bold=True))
        toolbar = BoxLayout(size_hint_y=None, height=38, spacing=8)
        for label, callback in [('انتخاب همه', self._select_all),
                                ('لغو انتخاب', self._clear_selection)]:
            button = SecondaryButton(text=theme.rtl(label), font_size=13, size_hint_x=None, width=115)
            button.bind(on_release=lambda _button, action=callback: action())
            toolbar.add_widget(button)
        self._count = RTLLabel(text='', color=theme.rgba(COLORS['text_secondary']))
        toolbar.add_widget(self._count)
        panel.add_widget(toolbar)
        self._choices = GridLayout(cols=4, spacing=8, size_hint_y=None)
        self._choices.bind(minimum_height=self._choices.setter('height'))
        panel.add_widget(self._choices)
        self._holder = BoxLayout(orientation='vertical')
        panel.add_widget(self._holder)
        content.add_widget(panel)
        self._shell = PageShell('مانیتورینگ دوربین‌ها', 'cameras', content, self._handle_navigate,
                                subtitle='نمایش هم‌زمان یک یا چند دوربین')
        self.add_widget(self._shell)
        camera_service.subscribe(self._on_cameras_changed)
        self._rebuild_choices()
        self._rebuild_grid()

    def on_enter(self, *_args):
        self._active = True
        for card in self._cards.values():
            card.start_stream()

    def on_leave(self, *_args):
        self._active = False
        for card in self._cards.values():
            card.stop_stream()

    def _handle_navigate(self, key):
        if self.on_navigate:
            self.on_navigate(key)

    def _on_cameras_changed(self, cameras):
        available = {camera.id for camera in cameras}
        self._selected.intersection_update(available)
        self._rebuild_choices()
        self._rebuild_grid()

    def _select_all(self):
        self._selected = {camera.id for camera in camera_service.get_cameras()}
        self._rebuild_choices()
        self._rebuild_grid()

    def _clear_selection(self):
        self._selected.clear()
        self._rebuild_choices()
        self._rebuild_grid()

    def _toggle(self, camera_id, selected):
        if selected:
            self._selected.add(camera_id)
        else:
            self._selected.discard(camera_id)
        self._rebuild_grid()

    def _rebuild_choices(self):
        self._choices.clear_widgets()
        for camera in camera_service.get_cameras():
            choice = ToggleButton(text=camera.id, font_name=theme.APP_FONT_NAME,
                                  group=None, allow_no_selection=True,
                                  size_hint_y=None, height=38,
                                  background_normal='', background_down='',
                                  background_color=theme.rgba(COLORS['primary_light'] if camera.id in self._selected else COLORS['surface_alt']),
                                  color=theme.rgba(COLORS['text_primary']),
                                  state='down' if camera.id in self._selected else 'normal')
            choice.bind(state=lambda button, state: setattr(button, 'background_color',
                        theme.rgba(COLORS['primary_light'] if state == 'down' else COLORS['surface_alt'])))
            choice.bind(on_release=lambda button, cid=camera.id:
                        self._toggle(cid, button.state == 'down'))
            self._choices.add_widget(choice)
        self._choices.height = ((len(self._choices.children) + 3) // 4) * 46

    def _rebuild_grid(self):
        cameras = camera_service.get_cameras()
        wanted = [camera for camera in cameras if camera.id in self._selected]
        self._count.set_text(f'{len(wanted)} دوربین از {len(cameras)} انتخاب شده')
        for card in self._cards.values():
            card.stop_stream()
        self._cards.clear()
        self._holder.clear_widgets()
        if not cameras:
            self._holder.add_widget(EmptyState(
                icon_name='camera', title='هنوز دوربینی تنظیم نشده است',
                subtitle='از تنظیمات، دوربین و منبع تصویر آن را اضافه کنید',
                action_text='رفتن به تنظیمات',
                on_action=lambda: self._handle_navigate('camera_settings')))
            return
        if not wanted:
            self._holder.add_widget(EmptyState(
                icon_name='camera', title='دوربینی انتخاب نشده است',
                subtitle='یک یا چند دوربین را از بالا انتخاب کنید'))
            return
        grid = GridLayout(cols=1 if len(wanted) == 1 else 2,
                          size_hint_y=None, spacing=SPACING['sm'])
        grid.bind(minimum_height=grid.setter('height'))
        for camera in wanted:
            card = RawCameraCard(camera, size_hint_y=None, height=320)
            self._cards[camera.id] = card
            grid.add_widget(card)
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(grid)
        self._holder.add_widget(scroll)
        if self._active:
            for card in self._cards.values():
                card.start_stream()
