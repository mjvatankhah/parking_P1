"""A raw file/RTSP preview. No detector, tracker or preview bridge is involved."""

from kivy.clock import Clock
from kivy.graphics.texture import Texture
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
import cv2

from computer_vision_v2.reno.models.camera import STATUS_OFFLINE, STATUS_ONLINE
from computer_vision_v2.reno.services.camera_service import camera_service
from computer_vision_v2.reno.services.video_stream import VideoStream
from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.ui.components.camera_card import _RoundedArea, _VideoSurface
from computer_vision_v2.reno.ui.components.common import Card, RTLLabel


class RawCameraCard(Card):
    def __init__(self, camera, **kwargs):
        kwargs.setdefault('orientation', 'vertical')
        kwargs.setdefault('padding', [10, 10, 10, 10])
        kwargs.setdefault('spacing', 8)
        super().__init__(**kwargs)
        self.camera = camera
        self._stream = None
        self._poll = None
        self._generation = 0
        self._state = None

        heading = BoxLayout(size_hint_y=None, height=27)
        heading.add_widget(RTLLabel(text=camera.id, bold=True))
        self.status = RTLLabel(text='آماده اتصال', font_size=12,
                               color=theme.rgba(theme.COLORS['text_secondary']),
                               size_hint_x=None, width=148)
        heading.add_widget(self.status)
        self.add_widget(heading)

        area = _RoundedArea(bg_color=theme.rgba('#071018'))
        self.surface = _VideoSurface(pos_hint={'x': 0, 'y': 0})
        self.surface.opacity = 0
        area.add_widget(self.surface)
        self.message = Label(text=theme.rtl('در انتظار تصویر خام…'),
                             font_name=theme.APP_FONT_NAME,
                             font_size=13, color=theme.rgba(theme.COLORS['text_secondary']),
                             size_hint=(1, None), height=32,
                             pos_hint={'center_x': .5, 'center_y': .5})
        area.add_widget(self.message)
        self.add_widget(area)
        self.bind(parent=self._on_parent)

    def start_stream(self):
        if self._stream is not None or not self.parent:
            return
        self._generation += 1
        generation = self._generation
        self._set_state('connecting')
        self._stream = VideoStream(
            self.camera,
            on_state=lambda state: Clock.schedule_once(
                lambda _dt: self._on_state(generation, state), 0),
        )
        self._poll = Clock.schedule_interval(self._draw_latest, 1 / 15)
        self._stream.start()

    def stop_stream(self):
        self._generation += 1
        if self._poll is not None:
            self._poll.cancel()
            self._poll = None
        if self._stream is not None:
            self._stream.stop()
            self._stream = None
        self.surface.opacity = 0
        self.message.opacity = 1
        self._set_state('offline', publish=False)
        camera_service.set_status(self.camera.id, STATUS_OFFLINE)

    def _on_parent(self, _widget, parent):
        if parent is None:
            self.stop_stream()

    def _on_state(self, generation, state):
        if generation == self._generation and self._stream is not None:
            self._set_state(state)

    def _set_state(self, state, *, publish=True):
        if self._state == state:
            return
        self._state = state
        labels = {'connecting': 'در حال اتصال', 'online': 'تصویر خام',
                  'offline': 'بدون تصویر'}
        colors = {'connecting': 'warning', 'online': 'online', 'offline': 'offline'}
        self.status.set_text(labels[state])
        self.status.color = theme.rgba(theme.COLORS[colors[state]])
        if state != 'online':
            self.surface.opacity = 0
            self.message.opacity = 1
            self.message.text = theme.rtl(
                'منبع ویدیو در دسترس نیست' if state == 'offline'
                else 'در حال دریافت تصویر خام…'
            )
        if publish:
            camera_service.set_status(self.camera.id,
                                      STATUS_ONLINE if state == 'online' else STATUS_OFFLINE)

    def _draw_latest(self, _dt):
        if self._stream is None:
            return
        frame = self._stream.latest_frame()
        if frame is None:
            return
        rgb = cv2.flip(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), 0)
        texture = Texture.create(size=(rgb.shape[1], rgb.shape[0]), colorfmt='rgb')
        texture.blit_buffer(rgb.tobytes(), colorfmt='rgb', bufferfmt='ubyte')
        self.surface.set_texture(texture)
        self.surface.opacity = 1
        self.message.opacity = 0
