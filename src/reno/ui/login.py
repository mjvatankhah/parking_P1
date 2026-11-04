"""Reference-branded login; authentication stays behind the existing interface."""

from threading import Thread
from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.graphics import Color, Mesh, Line

from reno.ui import theme
from reno.ui.theme import COLORS, FONT_SIZE, rtl
from reno.ui.components.common import (
    Card, PrimaryButton, RoundedTextInput, RTLLabel,
)
from reno.ui.components.icons import Icon
from reno.ui.components.brand import BrandMark, Brand
from reno.ui.components.ambient_background import AmbientBackground
from reno.ui.components.app_header import WindowControls
from reno.ui.components.username_input import UsernameInput
from reno.services.auth_service import auth_service

APP_NAME = "PLAKINO"


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
        root.add_widget(AmbientBackground())
        self._root = root

        shell = BoxLayout(
            orientation="horizontal",
            size_hint=(None, None),
            size=(920, 560),
            pos_hint={"center_x": 0.5, "center_y": 0.5},
            spacing=18,
        )
        self._shell = shell
        root.bind(size=self._resize_shell)
        self._hero = _LoginHero()
        shell.add_widget(self._hero)

        card = Card(
            orientation="vertical",
            size_hint=(None, 1),
            width=400,
            padding=[36, 32, 36, 28],
            spacing=10,
            radius=10,
            hover_effect=False,
            bg_color=theme.rgba(COLORS["surface"]),
        )

        card.add_widget(self._build_brand())
        card.add_widget(self._build_field("نام کاربری :", "username"))
        card.add_widget(self._build_field("رمز عبور:", "password", is_password=True))

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

        login_button = self._login_button = PrimaryButton(text=rtl("ورود"), size_hint_y=None, height=48)
        login_button.bind(on_release=self._attempt_login)
        self._password_input.bind(on_text_validate=self._attempt_login)
        self._username_input.bind(on_text_validate=lambda *_: setattr(self._password_input, "focus", True))
        card.add_widget(login_button)

        shell.add_widget(card)
        root.add_widget(shell)
        root.add_widget(WindowControls(pos_hint={"right": 1, "top": 1}))
        self.add_widget(root)

    def _resize_shell(self, *_args):
        self._shell.size = (
            min(980, max(720, self._root.width - 80)),
            min(570, max(520, self._root.height - 60)),
        )

    def _build_brand(self):
        box = BoxLayout(orientation="vertical", size_hint_y=None, height=122, spacing=5)
        icon = BrandMark(size=(44, 44), pos_hint={"center_x": 0.5})
        title = Label(
            text=rtl("ورود به سامانه"),
            font_name=theme.APP_FONT_NAME,
            font_size=24,
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

        input_class = RoundedTextInput if is_password else UsernameInput
        text_input = input_class(password=is_password, size_hint_y=None, height=44,
                                 halign="right" if is_password else "left")
        if not is_password:
            text_input.bind(input_error=lambda _, error: setattr(self._error_label, 'text', rtl(error)))
        setattr(self, f"_{field_key}_input", text_input)

        box.add_widget(label)
        box.add_widget(text_input)
        return box

    # ------------------------------------------------------------------
    def _attempt_login(self, *_args):
        username = self._username_input.text
        password = self._password_input.text

        if self._login_button.disabled:
            return
        self._login_button.disabled = True
        self._error_label.text = rtl("در حال ورود…")

        def work():
            result = auth_service.login(username, password)
            Clock.schedule_once(lambda _: self._login_complete(result))
        Thread(target=work, daemon=True).start()

    def _login_complete(self, result):
        self._login_button.disabled = False
        if result.success:
            self._error_label.text = ""
            self._password_input.text = ""
            if self.on_login_success:
                self.on_login_success()
        else:
            self._error_label.text = rtl(result.error_message)


class _LoginHero(Card):
    """Quiet product introduction beside the existing authentication form."""

    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', padding=[34, 42, 34, 36], spacing=14,
                         gradient=('#222C39', '#191F27'), bg_color=theme.rgba(COLORS['surface']),
                         hover_effect=False, radius=10, **kwargs)
        with self.canvas.before:
            Color(*theme.rgba('#587398', .10))
            self._plane = Mesh(vertices=[], indices=[0,1,2,0,2,3], mode='triangles')
            Color(*theme.rgba('#90AACB', .13))
            self._contour = Line(width=.65)
            Color(*theme.rgba('#90AACB', .07))
            self._contour_inner = Line(width=.65)
        self.bind(pos=self._geometry, size=self._geometry)
        self._geometry()
        self.add_widget(Brand())
        self.add_widget(BoxLayout())
        self.add_widget(RTLLabel(text='پایش و مدیریت تردد', font_size=26,
                                size_hint_y=None, height=48, padding=[0, 0]))
        self.add_widget(RTLLabel(text='بررسی تشخیص زنده و رویدادهای ورود و خروج', font_size=13,
                                color=theme.rgba(COLORS['text_secondary']),
                                size_hint_y=None, height=52, padding=[0, 0]))
        self.add_widget(BoxLayout(size_hint_y=None, height=14))
        for icon, label in [('car', 'شناسایی و ثبت پلاک'), ('camera', 'تشخیص زنده'),
                            ('shield', 'بررسی وضعیت تردد')]:
            item = BoxLayout(size_hint_y=None, height=36, spacing=14)
            item.add_widget(RTLLabel(text=label, font_size=13, padding=[0, 0],
                                    color=theme.rgba(COLORS['text_secondary'])))
            item.add_widget(Icon(name=icon, color=theme.rgba(COLORS['primary']),
                                 size_hint=(None, None), size=(20, 20), pos_hint={'center_y': .5}))
            self.add_widget(item)
        self.add_widget(BoxLayout())

    def _geometry(self, *_):
        x,y,w,h=self.x,self.y,self.width,self.height
        points=[(.02,.14),(.32,.02),(.60,.02),(.02,.38)]
        self._plane.vertices=[v for px,py in points for v in (x+w*px,y+h*py,0,0)]
        self._contour.points=[x+w*.45,y+h*.98,x+w*.98,y+h*.68,x+w*.98,y+h*.84,x+w*.74,y+h*.98]
        self._contour_inner.points=[x+w*.59,y+h*.98,x+w*.98,y+h*.76]
