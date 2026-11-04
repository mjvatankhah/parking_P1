"""Three-step Kivy drawing dialog backed by select_line_points geometry logic."""
from threading import Thread

import cv2
from kivy.clock import Clock
from kivy.graphics.texture import Texture
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.popup import Popup

from computer_vision_v2.Line_Manager.select_line_points import GuidedSelection, Stage, annotated_frame
from reno.services.geometry_service import capture_frame, persist_selection
from reno.ui import theme
from reno.ui.components.common import RTLLabel, PrimaryButton, SecondaryButton


def frame_texture(frame):
    texture = Texture.create(size=(frame.shape[1], frame.shape[0]), colorfmt='rgb')
    texture.blit_buffer(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).tobytes(), colorfmt='rgb', bufferfmt='ubyte')
    texture.flip_vertical()
    return texture


class DrawingImage(Image):
    """Translate clicks through Image's letterboxing into source pixel coordinates."""
    def source_point(self, x, y):
        if not self.texture:
            return None
        width, height = self.norm_image_size
        if width <= 0 or height <= 0:
            return None
        left, bottom = self.center_x - width / 2, self.center_y - height / 2
        if not (left <= x <= left + width and bottom <= y <= bottom + height):
            return None
        sw, sh = self.texture.size
        return min(sw-1, max(0, round((x-left) / width * sw))), min(sh-1, max(0, round((bottom+height-y) / height * sh)))

    def on_touch_down(self, touch):
        if getattr(touch, 'is_mouse_scrolling', False) or getattr(touch, 'button', 'left') != 'left':
            return super().on_touch_down(touch)
        if self.disabled or not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        point = self.source_point(*touch.pos)
        if point is not None and getattr(self, 'on_point', None):
            self.on_point(point)
        return True


class GeometryDialog(Popup):
    def __init__(self, camera, config_path, on_saved, **kwargs):
        self.camera = dict(camera)
        self.config_path = config_path
        self.on_saved = on_saved
        self.selection = None
        self.frame = None
        self._closed = False
        self._saving = False
        body = BoxLayout(orientation='vertical', padding=18, spacing=12)
        self.steps = RTLLabel(text='۱ خط مرجع    /    ۲ محدوده پردازش    /    ۳ داخل پارکینگ',
                              size_hint_y=None, height=28, halign='center', font_size=13)
        body.add_widget(self.steps)
        self.instruction = RTLLabel(text='در حال دریافت تصویر دوربین…', size_hint_y=None, height=32)
        body.add_widget(self.instruction)
        self.image = DrawingImage(fit_mode='contain')
        self.image.on_point = self._point
        body.add_widget(self.image)
        self.error = RTLLabel(text='', color=theme.rgba(theme.COLORS['offline']), size_hint_y=None, height=44)
        body.add_widget(self.error)
        buttons = BoxLayout(size_hint_y=None, height=44, spacing=10)
        cancel = SecondaryButton(text=theme.rtl('انصراف'), size_hint_x=None, width=100)
        cancel.bind(on_release=lambda *_: self.dismiss() if not self._saving else None)
        self.reset = SecondaryButton(text=theme.rtl('رسم مجدد'), size_hint_x=None, width=120, disabled=True)
        self.reset.bind(on_release=self._reset)
        self.back = SecondaryButton(text=theme.rtl('مرحله قبل'), size_hint_x=None, width=120, disabled=True)
        self.back.bind(on_release=self._back)
        self.next = PrimaryButton(text=theme.rtl('مرحله بعد'), size_hint_x=None, width=140, disabled=True)
        self.next.bind(on_release=self._advance)
        for widget in (cancel, self.reset, self.back, BoxLayout(), self.next):
            buttons.add_widget(widget)
        body.add_widget(buttons)
        super().__init__(title=theme.rtl('ثبت خط مرجع و محدوده'), title_font=theme.APP_FONT_NAME,
                         title_align='right', content=body, size_hint=(.92, .92), auto_dismiss=False,
                         background='', background_color=theme.rgba(theme.COLORS['surface']), **kwargs)
        self.bind(on_open=self._load, on_dismiss=self._dismissed)

    def _dismissed(self, *_):
        self._closed = True

    def _load(self, *_):
        def work():
            try:
                frame, error = capture_frame(self.camera), ''
            except Exception as exc:
                frame, error = None, str(exc)
            Clock.schedule_once(lambda _: self._loaded(frame, error))
        Thread(target=work, daemon=True).start()

    def _loaded(self, frame, error=''):
        if self._closed:
            return
        if frame is None:
            self.instruction.text = theme.rtl('دریافت تصویر ناموفق بود')
            self.error.text = theme.rtl(error)
            return
        self.frame = frame
        self.selection = GuidedSelection(frame.shape[1], frame.shape[0])
        self._refresh()

    def _refresh(self):
        stage = self.selection.stage
        instructions = {
            Stage.LINE: 'خط مرجع را با دو نقطه رسم کنید؛ برای خط شکسته، نقطه سوم را انتخاب کنید.',
            Stage.ROI: 'چهار گوشه ROI را به‌ترتیب انتخاب کنید؛ شکل با نقطه چهارم بسته می‌شود.',
            Stage.SIDE: 'روی سمت داخل پارکینگ کلیک کنید، سپس «ثبت» را بزنید.',
        }
        self.instruction.text = theme.rtl(instructions[stage])
        self.steps.text = theme.rtl({Stage.LINE: 'مرحله ۱ از ۳ · خط مرجع', Stage.ROI: 'مرحله ۲ از ۳ · محدوده پردازش', Stage.SIDE: 'مرحله ۳ از ۳ · داخل پارکینگ'}[stage])
        self.next.text = theme.rtl('ثبت' if stage == Stage.SIDE else 'مرحله بعد')
        self.next.disabled = False
        self.reset.disabled = False
        self.back.disabled = stage == Stage.LINE
        self.image.texture = frame_texture(annotated_frame(self.frame, self.selection))
        self.error.text = ''

    def _point(self, point):
        if self.selection is None or self._saving:
            return
        try:
            self.selection.click(point)
            self._refresh()
        except ValueError as exc:
            self.error.text = theme.rtl(str(exc))

    def _reset(self, *_):
        if self.selection is not None:
            self.selection.reset_stage()
            self._refresh()

    def _back(self, *_):
        self.selection.back()
        self._refresh()

    def _advance(self, *_):
        if self.selection is None or self._saving:
            return
        try:
            if self.selection.stage != Stage.SIDE:
                self.selection.confirm()
                self._refresh()
                return
            self.selection.geometry()
        except ValueError as exc:
            self.error.text = theme.rtl(str(exc))
            return
        self._saving = True
        self.content.disabled = True
        self.error.text = theme.rtl('در حال ذخیره…')

        def work():
            try:
                preview = persist_selection(self.config_path, self.camera, self.selection, self.frame)
                error = ''
            except Exception:
                preview, error = '', 'ذخیره انجام نشد؛ تنظیمات دوربین ممکن است تغییر کرده باشد. دوباره باز کنید.'
            Clock.schedule_once(lambda _: self._saved(preview, error))
        Thread(target=work, daemon=True).start()

    def _saved(self, preview, error):
        if self._closed:
            return
        self._saving = False
        self.content.disabled = False
        if error:
            self.error.text = theme.rtl(error)
            return
        self.on_saved(preview)
        self.dismiss()
