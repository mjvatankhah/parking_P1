"""Shared in-app window chrome and page header for the desktop UI."""

from kivy.app import App
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.uix.behaviors import ButtonBehavior
from kivy.graphics import Color, RoundedRectangle, Line
from kivy.animation import Animation
from kivy.properties import ListProperty

from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.ui.theme import COLORS, FONT_SIZE, rtl
from computer_vision_v2.reno.ui.components.common import Card, SecondaryButton, RTLLabel, HoverBehavior
from computer_vision_v2.reno.ui.components.icons import Icon


class _WindowButton(HoverBehavior, ButtonBehavior, Label):
    _bg_rgba = ListProperty([0, 0, 0, 0])

    def __init__(self, symbol, action, danger=False, **kwargs):
        kwargs.setdefault("text", "")
        kwargs.setdefault("font_name", theme.APP_FONT_NAME)
        kwargs.setdefault("font_size", 18)
        kwargs.setdefault("halign", "center")
        kwargs.setdefault("valign", "middle")
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (36, 34))
        super().__init__(**kwargs)
        self._symbol = Icon(name={"−": "minus", "□": "maximize", "×": "close"}[symbol],
                            color=theme.rgba(COLORS["text_secondary"]),
                            size_hint=(None, None), size=(14, 14))
        self.add_widget(self._symbol)
        self._action = action
        self._danger = danger
        self.color = theme.rgba(COLORS["offline"] if danger else COLORS["text_primary"])
        self._normal_bg = theme.rgba(COLORS["surface_alt"])
        self._bg_rgba = self._normal_bg
        self.text_size = self.size
        with self.canvas.before:
            self._bg_color = Color(*self._normal_bg)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[7])
            self._border_color = Color(*theme.rgba(COLORS["border"], 0.55))
            self._border = Line(rounded_rectangle=(*self.pos, *self.size, 7), width=1)
        self.bind(pos=self._redraw, size=self._redraw, hovered=self._animate, state=self._animate,
                  _bg_rgba=self._sync_bg)
        self.bind(on_release=lambda *_: self._action())

    def _redraw(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._border.rounded_rectangle = (*self.pos, *self.size, 7)
        self.text_size = self.size
        self._symbol.center = self.center

    def _animate(self, *_):
        if self.state == "down":
            target = theme.rgba(COLORS["offline"] if self._danger else COLORS["primary"], 0.32)
        elif self.hovered:
            target = theme.rgba(COLORS["offline"] if self._danger else COLORS["primary_light"])
        else:
            target = self._normal_bg
        Animation.cancel_all(self, "_bg_rgba")
        Animation(_bg_rgba=target, duration=theme.ANIM_FAST, t="out_quad").start(self)

    def _sync_bg(self, _, value):
        self._bg_color.rgba = value


class WindowControls(BoxLayout):
    """Custom minimize, maximize, and close controls for borderless Kivy windows."""

    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (112, 42))
        kwargs.setdefault("spacing", 2)
        kwargs.setdefault("padding", [4, 4, 4, 4])
        super().__init__(**kwargs)
        self._maximized = False
        self.add_widget(_WindowButton("−", self._minimize))
        self.add_widget(_WindowButton("□", self._toggle_maximize))
        self.add_widget(_WindowButton("×", self._close, danger=True))

    def _minimize(self):
        minimize = getattr(Window, "minimize", None)
        if minimize:
            minimize()

    def _toggle_maximize(self):
        operation = "restore" if self._maximized else "maximize"
        callback = getattr(Window, operation, None)
        if callback:
            callback()
            self._maximized = not self._maximized

    def _close(self):
        app = App.get_running_app()
        if app:
            app.stop()
        close = getattr(Window, "close", None)
        if close:
            close()


class AppHeader(BoxLayout):
    """The HTML title hierarchy and a functional symbolic ticket action."""

    def __init__(self, title, subtitle='خلاصهٔ ترددها و وضعیت دوربین‌ها', **kwargs):
        kwargs.setdefault('size_hint_y', None)
        kwargs.setdefault('height', 64)
        kwargs.setdefault('spacing', 18)
        super().__init__(**kwargs)
        self.ticket_button = SecondaryButton(text=rtl('ثبت تیکت'), font_size=12,
            size_hint=(None, None), size=(114, 36), pos_hint={'center_y': .5},
            bg_color_normal=theme.rgba(COLORS['surface_alt']), border_color=theme.rgba(COLORS['border']),
            color=theme.rgba(COLORS['text_primary']), radius=5)
        self.ticket_button.bind(on_release=self._open_ticket)
        self.add_widget(self.ticket_button)
        heading = BoxLayout(orientation='vertical', spacing=1)
        heading.add_widget(RTLLabel(text=title, font_size=23, size_hint_y=None, height=34,
                          padding=[0, 0]))
        heading.add_widget(RTLLabel(text=subtitle, font_size=12,
                          color=theme.rgba(COLORS['text_secondary']), size_hint_y=None, height=25,
                          padding=[0, 0]))
        self.add_widget(heading)

    def _open_ticket(self, *_):
        from computer_vision_v2.reno.ui.components.ticket_dialog import TicketDialog
        self.ticket_dialog = TicketDialog()
        self.ticket_dialog.open()
