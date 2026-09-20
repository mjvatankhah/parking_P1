"""
ui/login.py

The Login screen: RENO branding, username, password, "remember me",
a login button and a "forgot password" link, matching the Balsamiq
wireframe.

This screen never decides whether a username/password is correct -
it only calls services.auth_service.auth_service.login(...) and reacts
to the result. That is what "keep authentication behind a service
interface" (from the brief) means in practice.
"""

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.label import Label
from kivy.uix.checkbox import CheckBox
from kivy.uix.popup import Popup
from kivy.graphics import Color, Rectangle, RoundedRectangle, Ellipse, Line
from kivy.animation import Animation

from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.ui.theme import COLORS, FONT_SIZE, SPACING, RADIUS, rtl, PAGE_BG_TOP, PAGE_BG_BOTTOM
from computer_vision_v2.reno.ui.components.common import (
    Card, make_gradient_texture, PrimaryButton, RoundedTextInput, RTLLabel, HoverBehavior,
)
from computer_vision_v2.reno.ui.components.icons import Icon
from computer_vision_v2.reno.ui.components.app_header import WindowControls
from computer_vision_v2.reno.services.auth_service import auth_service

APP_NAME = "KALPINO"


class LoginScreen(Screen):
    """`on_login_success` is set by main.py to a function with no
    arguments; it is called once the demo credentials check out."""

    def __init__(self, on_login_success=None, **kwargs):
        super().__init__(**kwargs)
        self.on_login_success = on_login_success
        self._build()

    # ------------------------------------------------------------------
    def _build(self):
        root = FloatLayout()
        with root.canvas.before:
            Color(1, 1, 1, 1)
            self._bg_rect = Rectangle(
                pos=root.pos,
                size=root.size,
                texture=make_gradient_texture(PAGE_BG_TOP, PAGE_BG_BOTTOM),
            )
        root.bind(pos=self._redraw_bg, size=self._redraw_bg)
        self._root = root

        shell = BoxLayout(
            orientation="horizontal",
            size_hint=(None, None),
            size=(920, 560),
            pos_hint={"center_x": 0.5, "center_y": 0.5},
            spacing=0,
        )
        self._shell = shell
        root.bind(size=self._resize_shell)
        shell.add_widget(_LoginHero())

        card = Card(
            orientation="vertical",
            size_hint=(None, 1),
            width=400,
            padding=[36, 32, 36, 28],
            spacing=10,
            radius=0,
        )

        card.add_widget(self._build_brand())
        card.add_widget(self._build_field("نام کاربری :", "username"))
        card.add_widget(self._build_field("رمز عبور:", "password", is_password=True))
        card.add_widget(self._build_remember_row())

        self._error_label = Label(
            text="",
            font_name=theme.APP_FONT_NAME,
            font_size=FONT_SIZE["caption"],
            color=theme.rgba(COLORS["offline"]),
            size_hint_y=None,
            height=20,
            halign="center",
            valign="middle",
        )
        self._error_label.bind(size=lambda widget, *_: setattr(widget, "text_size", widget.size))
        card.add_widget(self._error_label)

        login_button = PrimaryButton(text=rtl("ورود"), size_hint_y=None, height=48)
        login_button.bind(on_release=self._attempt_login)
        card.add_widget(login_button)

        forgot = _LinkLabel(text=rtl("رمز عبور را فراموش کرده‌اید؟"))
        forgot.bind(on_release=self._show_forgot_password_popup)
        card.add_widget(forgot)

        shell.add_widget(card)
        root.add_widget(shell)
        root.add_widget(WindowControls(pos_hint={"right": 1, "top": 1}))
        self.add_widget(root)

    def _redraw_bg(self, *_args):
        self._bg_rect.pos = self._root.pos
        self._bg_rect.size = self._root.size

    def _resize_shell(self, *_args):
        self._shell.size = (
            min(940, max(760, self._root.width - 80)),
            min(570, max(520, self._root.height - 60)),
        )

    def _build_brand(self):
        box = BoxLayout(orientation="vertical", size_hint_y=None, height=122, spacing=5)
        icon = Icon(name="camera", color=theme.rgba(COLORS["primary"]),
                    size_hint=(None, None), size=(44, 44), pos_hint={"center_x": 0.5})
        title = Label(
            text=APP_NAME,
            font_name=theme.APP_FONT_NAME,
            font_size=FONT_SIZE["display"],
            bold=True,
            color=theme.rgba(COLORS["text_primary"]),
            size_hint_y=None,
            height=42,
        )
        subtitle = Label(
            text=rtl("سامانه هوشمند شناسایی پلاک پارکینگ"),
            font_name=theme.APP_FONT_NAME,
            font_size=FONT_SIZE["caption"],
            color=theme.rgba(COLORS["text_secondary"]),
            size_hint_y=None,
            height=22,
            halign="center",
            valign="middle",
        )
        subtitle.bind(size=lambda widget, *_: setattr(widget, "text_size", widget.size))
        box.add_widget(icon)
        box.add_widget(title)
        box.add_widget(subtitle)
        return box

    def _build_field(self, label_text, field_key, is_password=False):
        box = BoxLayout(orientation="vertical", size_hint_y=None, height=72, spacing=4)
        label = Label(
            text=rtl(label_text),
            font_name=theme.APP_FONT_NAME,
            font_size=FONT_SIZE["caption"],
            color=theme.rgba(COLORS["text_secondary"]),
            halign="right",
            size_hint_y=None,
            height=22,
            padding=[8, 2],
        )
        label.bind(size=lambda w, *_: setattr(w, "text_size", w.size))

        text_input = RoundedTextInput(password=is_password, size_hint_y=None, height=44,
                                       halign="right")
        setattr(self, f"_{field_key}_input", text_input)

        box.add_widget(label)
        box.add_widget(text_input)
        return box

    def _build_remember_row(self):
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=32, spacing=6)
        self._remember_checkbox = CheckBox(size_hint=(None, None), size=(24, 24),
                                            color=theme.rgba(COLORS["primary"]))
        label = Label(
            text=rtl("مرا به خاطر بسپار"),
            font_name=theme.APP_FONT_NAME,
            font_size=FONT_SIZE["caption"],
            color=theme.rgba(COLORS["text_secondary"]),
        )
        row.add_widget(label)
        row.add_widget(self._remember_checkbox)
        return row

    # ------------------------------------------------------------------
    def _attempt_login(self, *_args):
        username = self._username_input.text
        password = self._password_input.text

        result = auth_service.login(username, password)
        if result.success:
            self._error_label.text = ""
            self._password_input.text = ""
            if self.on_login_success:
                self.on_login_success()
        else:
            self._error_label.text = rtl(result.error_message)

    def _show_forgot_password_popup(self, *_args):
        content = Label(
            text=rtl("این قابلیت به‌زودی اضافه می‌شود"),
            font_name=theme.APP_FONT_NAME,
            font_size=FONT_SIZE["body"],
            color=theme.rgba(COLORS["text_primary"]),
        )
        Popup(
            title=rtl("فراموشی رمز عبور"),
            title_font=theme.APP_FONT_NAME,
            content=content,
            size_hint=(None, None),
            size=(300, 160),
        ).open()


class _LinkLabel(HoverBehavior, Label):
    """A Label that behaves like a clickable text link (used for
    'forgot password'). Kept in this file since it's only used here."""

    def __init__(self, **kwargs):
        kwargs.setdefault("font_name", theme.APP_FONT_NAME)
        kwargs.setdefault("font_size", FONT_SIZE["caption"])
        kwargs.setdefault("color", theme.rgba(COLORS["primary"]))
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", 24)
        super().__init__(**kwargs)
        self._normal_color = theme.rgba(COLORS["primary"])
        self.bind(on_touch_down=self._on_touch_down)
        self.register_event_type("on_release")

    def _on_touch_down(self, widget, touch):
        if self.collide_point(*touch.pos):
            self.dispatch("on_release")
            return True
        return False

    def on_release(self, *_args):
        pass

    def on_hovered(self, *_args):
        target = theme.rgba(COLORS["primary_dark"]) if self.hovered else self._normal_color
        Animation.cancel_all(self, "color")
        Animation(color=target, duration=theme.ANIM_FAST, t="out_quad").start(self)


class _LoginHero(FloatLayout):
    """Brand panel drawn with Kivy primitives, so it stays crisp offline."""

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint", (1, 1))
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*theme.rgba(COLORS["primary_dark"]))
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[22])
            Color(*theme.rgba("#76B38F"), 0.22)
            self._orb_one = Ellipse(pos=self.pos, size=(360, 360))
            Color(1, 1, 1, 0.08)
            self._orb_two = Ellipse(pos=self.pos, size=(220, 220))
            Color(1, 1, 1, 0.13)
            self._line_one = Line(points=[], width=22)
            self._line_two = Line(points=[], width=9)
        self.bind(pos=self._redraw, size=self._redraw)

        content = BoxLayout(
            orientation="vertical", spacing=12,
            size_hint=(0.76, None), height=260,
            pos_hint={"center_x": 0.5, "center_y": 0.5},
        )
        badge = AnchorLayout(size_hint_y=None, height=72)
        badge.add_widget(Icon(name="camera", color=(1, 1, 1, 1),
                              size_hint=(None, None), size=(60, 60)))
        content.add_widget(badge)
        content.add_widget(Label(text=APP_NAME, font_name=theme.APP_FONT_NAME,
                                 font_size=42, bold=True, color=(1, 1, 1, 1),
                                 size_hint_y=None, height=58))
        content.add_widget(RTLLabel(text="سامانه یکپارچه مدیریت تردد و پلاک‌خوانی",
                                    font_size=18, color=(1, 1, 1, 0.88),
                                    halign="center", size_hint_y=None, height=44))
        content.add_widget(RTLLabel(text="کنترل دوربین‌ها، مشاهده زنده و گزارش تردد در یک نگاه",
                                    font_size=13, color=(1, 1, 1, 0.62),
                                    halign="center", size_hint_y=None, height=46))
        self.add_widget(content)
        self._redraw()

    def _redraw(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._orb_one.pos = (self.x - 150, self.top - 235)
        self._orb_two.pos = (self.right - 105, self.y - 80)
        self._line_one.points = [self.x - 20, self.y + 95, self.x + 150, self.y + 265]
        self._line_two.points = [self.right - 190, self.top - 30, self.right + 20, self.top - 240]
