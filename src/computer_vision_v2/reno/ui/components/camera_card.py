"""
ui/components/camera_card.py

One live backend preview tile inside the Cameras screen.
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.widget import Widget
from kivy.graphics import Color, RoundedRectangle, Rectangle
from kivy.graphics.texture import Texture
from kivy.clock import Clock
import cv2

from computer_vision_v2.reno.models.camera import Camera, STATUS_ONLINE, STATUS_OFFLINE
from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.ui.theme import COLORS, FONT_SIZE, SPACING, rtl
from computer_vision_v2.reno.ui.components.common import Card, StatusDot
from computer_vision_v2.preview import PREVIEW_FPS, preview_path, read_preview
from computer_vision_v2.reno.services.camera_service import camera_service


class CameraCard(Card):
    def __init__(self, camera: Camera, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("padding", [SPACING["sm"], SPACING["sm"], SPACING["sm"], SPACING["sm"]])
        kwargs.setdefault("spacing", SPACING["xs"])
        super().__init__(**kwargs)
        self.camera = camera
        self._preview_path = preview_path(camera.id, camera.source)
        self._version = None
        self._poll_event = None
        self._state = None
        self.add_widget(self._build_header(camera))
        self.add_widget(self._build_video_area(camera))
        self.bind(parent=self._on_parent)

    def _build_header(self, camera: Camera):
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=24, spacing=6)

        name_label = Label(
            text=camera.id,
            font_name=theme.APP_FONT_NAME,
            font_size=FONT_SIZE["body"],
            bold=True,
            color=theme.rgba(COLORS["text_primary"]),
            halign="right",
            valign="middle",
            size_hint_x=1,
        )
        name_label.bind(size=lambda w, *_: setattr(w, "text_size", w.size))

        self._dot = StatusDot(dot_color=theme.rgba(COLORS["warning"]), pulse=False)
        self._status_label = Label(
            text=rtl("در حال اتصال"),
            font_name=theme.APP_FONT_NAME,
            font_size=FONT_SIZE["caption"],
            color=theme.rgba(COLORS["warning"]),
            size_hint_x=None,
            width=100,
        )

        row.add_widget(name_label)
        row.add_widget(self._status_label)
        row.add_widget(self._dot)
        return row

    def _build_video_area(self, camera: Camera):
        area = _RoundedArea(bg_color=theme.rgba("#10261F"))
        self._video_surface = _VideoSurface()
        self._message = Label(
            text=rtl("در حال اتصال به دوربین…"),
            font_name=theme.APP_FONT_NAME,
            font_size=FONT_SIZE["caption"],
            color=(1, 1, 1, 0.78),
            pos_hint={"center_x": 0.5, "center_y": 0.5},
            size_hint=(1, None),
            height=18,
        )
        area.add_widget(self._video_surface)
        area.add_widget(self._message)
        return area

    def ensure_stream_started(self, *_):
        if self._poll_event is not None or self.parent is None:
            return
        self._apply_state("connecting")
        self._poll_event = Clock.schedule_interval(self._update_frame, 1 / PREVIEW_FPS)
        self._update_frame(0)

    def stop_stream(self):
        if self._poll_event is not None:
            self._poll_event.cancel()
            self._poll_event = None
        self._version = None
        self._video_surface.opacity = 0

    def _apply_state(self, state):
        if self._state == state:
            return
        self._state = state
        labels = {"connecting": "در انتظار تصویر", "online": "تصویر زنده", "offline": "بدون تصویر"}
        colors = {"connecting": COLORS["warning"], "online": COLORS["online"], "offline": COLORS["offline"]}
        color = colors[state]
        self._status_label.text = rtl(labels[state])
        self._status_label.color = theme.rgba(color)
        self._dot.dot_color = theme.rgba(color)
        if state != "online":
            self._video_surface.opacity = 0
            self._message.opacity = 1
            self._message.text = rtl("منتظر تصویر دوربین؛ بک‌اند باید در حال اجرا باشد")
        camera_service.set_status(
            self.camera.id, STATUS_ONLINE if state == "online" else STATUS_OFFLINE,
        )

    def _update_frame(self, _dt):
        frame, version = read_preview(self._preview_path, self._version)
        self._version = version
        if version is None:
            self._apply_state("offline")
        elif frame is not None:
            self._render_frame(frame)
            self._apply_state("online")

    def _render_frame(self, frame):
        # OpenCV delivers BGR pixels, while RGB is the most portable format
        # for Kivy's OpenGL texture (especially through WSLg).
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb_frame = cv2.flip(rgb_frame, 0)
        frame_size = (rgb_frame.shape[1], rgb_frame.shape[0])
        # تا اندازهٔ تصویر ثابت است، همان Texture قبلی را به‌روزرسانی می‌کنیم.
        texture = self._video_surface.texture
        if texture is None or texture.size != frame_size:
            texture = Texture.create(size=frame_size, colorfmt="rgb")
        texture.blit_buffer(
            rgb_frame.tobytes(), colorfmt="rgb", bufferfmt="ubyte"
        )
        self._video_surface.set_texture(texture)
        self._video_surface.opacity = 1
        self._message.text = ""
        self._message.opacity = 0

    def _on_parent(self, _widget, parent):
        if parent is None:
            self.stop_stream()


class _VideoSurface(Widget):
    """Draw a live Texture directly, avoiding Image provider/cache behavior."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._texture = None
        with self.canvas:
            Color(1, 1, 1, 1)
            self._frame_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._redraw, size=self._redraw)

    @property
    def texture(self):
        return self._texture

    @property
    def has_texture(self):
        return self._texture is not None

    def set_texture(self, texture):
        self._texture = texture
        self._frame_rect.texture = texture
        self._redraw()
        self.canvas.ask_update()

    def _redraw(self, *_):
        if self._texture is None:
            self._frame_rect.pos = self.pos
            self._frame_rect.size = self.size
            return

        texture_width, texture_height = self._texture.size
        if not texture_width or not texture_height or not self.width or not self.height:
            return
        scale = min(self.width / texture_width, self.height / texture_height)
        draw_width = texture_width * scale
        draw_height = texture_height * scale
        self._frame_rect.size = (draw_width, draw_height)
        self._frame_rect.pos = (
            self.x + (self.width - draw_width) / 2,
            self.y + (self.height - draw_height) / 2,
        )


class _RoundedArea(FloatLayout):

    def __init__(self, bg_color, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            self._color = Color(*bg_color)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[12])
        self.bind(pos=self._redraw, size=self._redraw)

    def _redraw(self, *args):
        self._rect.pos = self.pos
        self._rect.size = self.size
