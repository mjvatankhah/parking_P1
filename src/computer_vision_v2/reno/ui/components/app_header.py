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
        kwargs.setdefault("text", symbol)
        kwargs.setdefault("font_name", theme.APP_FONT_NAME)
        kwargs.setdefault("font_size", 18)
        kwargs.setdefault("halign", "center")
        kwargs.setdefault("valign", "middle")
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (36, 34))
        super().__init__(**kwargs)
        self._action = action
        self._danger = danger
        self.color = theme.rgba(COLORS["offline"] if danger else COLORS["text_primary"])
        self._normal_bg = theme.rgba("#FDECEF" if danger else COLORS["surface_alt"])
        self._bg_rgba = self._normal_bg
        self.text_size = self.size
        with self.canvas.before:
            self._bg_color = Color(*self._normal_bg)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[7])
            self._border_color = Color(*theme.rgba(COLORS["offline"] if danger else COLORS["border_strong"], 0.55))
            self._border = Line(rounded_rectangle=(*self.pos, *self.size, 7), width=1)
        self.bind(pos=self._redraw, size=self._redraw, hovered=self._animate, state=self._animate,
                  _bg_rgba=self._sync_bg)
        self.bind(on_release=lambda *_: self._action())

    def _redraw(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._border.rounded_rectangle = (*self.pos, *self.size, 7)
        self.text_size = self.size

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


class _HelpIcon(HoverBehavior, ButtonBehavior, BoxLayout):
    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (38, 38))
        super().__init__(**kwargs)
        with self.canvas.before:
            self._color = Color(*theme.rgba(COLORS["primary_light"]))
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[10])
        self.bind(pos=self._redraw, size=self._redraw, hovered=self._animate, state=self._animate)
        self.add_widget(Icon(name="help", color=theme.rgba(COLORS["primary_dark"]),
                             size_hint=(None, None), size=(18, 18),
                             pos_hint={"center_x": .5, "center_y": .5}))

    def _redraw(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def _animate(self, *_):
        alpha = 0.85 if self.hovered else 1
        if self.state == "down":
            alpha = 0.6
        Animation.cancel_all(self, "opacity")
        Animation(opacity=alpha, duration=theme.ANIM_FAST, t="out_quad").start(self)


class AppHeader(Card):
    """Header order follows the supplied wireframe: ticket/help, user, title, controls."""

    def __init__(self, title, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", 64)
        kwargs.setdefault("padding", [16, 0, 8, 0])
        kwargs.setdefault("radius", 0)
        super().__init__(**kwargs)

        ticket_group = BoxLayout(size_hint_x=None, width=168, spacing=8)
        ticket_group.add_widget(SecondaryButton(text=rtl("ثبت تیکت"), size_hint=(None, None), size=(112, 38),
                                                pos_hint={"center_y": .5}))
        ticket_group.add_widget(_HelpIcon(pos_hint={"center_y": .5}))

        profile = BoxLayout(size_hint_x=None, width=188, spacing=8, padding=[4, 0, 4, 0])
        avatar = BoxLayout(size_hint=(None, None), size=(30, 30), pos_hint={"center_y": .5})
        with avatar.canvas.before:
            Color(*theme.rgba(COLORS["primary"]))
            circle = RoundedRectangle(pos=avatar.pos, size=avatar.size, radius=[15])
        avatar.bind(pos=lambda widget, *_: setattr(circle, "pos", widget.pos),
                    size=lambda widget, *_: setattr(circle, "size", widget.size))
        avatar.add_widget(Label(text="A", font_name=theme.APP_FONT_NAME, bold=True,
                                color=(1, 1, 1, 1), font_size=13))
        profile.add_widget(avatar)
        profile.add_widget(RTLLabel(text="سلام، ادمین", font_size=FONT_SIZE["caption"],
                                    halign="center", valign="middle", size_hint_y=None,
                                    height=30, pos_hint={"center_y": .5}))

        page_title = RTLLabel(text=title, font_size=FONT_SIZE["title"], bold=True,
                              valign="middle", size_hint_x=None, width=295)

        self.add_widget(ticket_group)
        self.add_widget(Widget())
        self.add_widget(profile)
        self.add_widget(page_title)
        self.add_widget(WindowControls(pos_hint={"center_y": .5}))
