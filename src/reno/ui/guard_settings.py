"""Admin-only guard registration and account list; DB work stays off the UI thread."""
from threading import Thread
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from reno.ui import theme
from reno.ui.components.common import (
    Card, RTLLabel, RoundedTextInput, PrimaryButton, DangerButton, SecondaryButton,
)
from reno.ui.components.jalali_calendar import jalali_text
from reno.ui.components.icons import Icon
from reno.ui.components.page_shell import PageShell
from reno.ui.components.username_input import UsernameInput
from reno.services.auth_service import auth_service


class DeleteGuardButton(ButtonBehavior, Card):
    """Compact, keyboard-focus-independent trash action with a full 40px hit area."""
    def __init__(self, **kwargs):
        super().__init__(size_hint=(None, None), size=(40, 40), padding=0,
                         radius=8, hover_effect=True,
                         bg_color=theme.rgba('#35252C'), **kwargs)
        slot = FloatLayout()
        slot.add_widget(Icon(name='guard_delete', size_hint=(None, None), size=(21, 21),
                             pos_hint={'center_x': .5, 'center_y': .5},
                             color=theme.rgba(theme.COLORS['offline'])))
        self.add_widget(slot)


def guard_date(value):
    if value is None:
        return 'ثبت نشده'
    local = value.astimezone()
    return f"{jalali_text(local.date().isoformat())}  ·  {theme.fa_number(local.strftime('%H:%M'))}"


class GuardSettingsScreen(Screen):
    def __init__(self, on_navigate=None, **kwargs):
        super().__init__(**kwargs)
        self._on_navigate = on_navigate
        self._generation = 0
        self._busy = False
        self._popup = None
        self._popup_timer = None
        self._confirmation = None
        scroll = ScrollView(do_scroll_x=False)
        self.content = BoxLayout(orientation='vertical', size_hint_y=None, spacing=18)
        self.content.bind(minimum_height=self.content.setter('height'))
        scroll.add_widget(self.content)
        card = Card(orientation='vertical', size_hint_y=None, height=390,
                    padding=24, spacing=10, hover_effect=False)
        self.fields = []
        for title, secret in [('نام کاربری نگهبان', False), ('رمز عبور', True), ('تکرار رمز عبور', True)]:
            card.add_widget(RTLLabel(text=title, size_hint_y=None, height=24))
            input_class = RoundedTextInput if secret else UsernameInput
            field = input_class(password=secret, size_hint_y=None, height=44)
            self.fields.append(field)
            card.add_widget(field)
        self.message = RTLLabel(text='', size_hint_y=None, height=30,
                                color=theme.rgba('#F87171'))
        self.fields[0].bind(input_error=lambda _, error: setattr(self.message, 'text', theme.rtl(error)))
        card.add_widget(self.message)
        self.submit = PrimaryButton(text=theme.rtl('ثبت نگهبان'), size_hint_y=None, height=44)
        self.submit.bind(on_release=self._save)
        card.add_widget(self.submit)
        self.content.add_widget(card)
        list_card = Card(orientation='vertical', size_hint_y=None, padding=18,
                         spacing=10, hover_effect=False)
        list_card.bind(minimum_height=list_card.setter('height'))
        heading = BoxLayout(size_hint_y=None, height=44, spacing=12)
        self.refresh = PrimaryButton(text=theme.rtl('به‌روزرسانی'), size_hint_x=None, width=140,
                                     bg_color_normal=theme.rgba('#237A54'),
                                     bg_color_hover=theme.rgba('#2B9165'),
                                     bg_color_down=theme.rgba('#195A3D'),
                                     border_color=theme.rgba('#31966C'))
        self.refresh.bind(on_release=self._load_guards)
        heading.add_widget(self.refresh)
        heading.add_widget(RTLLabel(text='نگهبان‌های ثبت‌شده'))
        list_card.add_widget(heading)
        header = Card(size_hint_y=None, height=42, padding=[12, 0], spacing=12,
                      radius=8, hover_effect=False, bg_color=theme.rgba(theme.COLORS['surface_alt']))
        header.add_widget(RTLLabel(text='حذف', size_hint_x=None, width=48, halign='center'))
        header.add_widget(RTLLabel(text='تاریخ ثبت', size_hint_x=.48, halign='center'))
        header.add_widget(RTLLabel(text='نام کاربری', size_hint_x=.52))
        list_card.add_widget(header)
        self.rows = BoxLayout(orientation='vertical', size_hint_y=None, spacing=6)
        self.rows.bind(minimum_height=self.rows.setter('height'))
        list_card.add_widget(self.rows)
        self.content.add_widget(list_card)
        self.add_widget(PageShell('مدیریت نگهبان‌ها', 'guard_settings', scroll, on_navigate,
                                  subtitle='ثبت، مشاهده و حذف حساب نگهبان'))

    def _visible(self):
        return auth_service.is_admin and self.manager and self.manager.current == self.name

    def on_pre_enter(self, *_):
        if not auth_service.is_admin:
            if self._on_navigate:
                Clock.schedule_once(lambda _: self._on_navigate('dashboard'))
            return
        self._load_guards()

    def on_leave(self, *_):
        self._generation += 1
        self._set_busy(False)
        for field in self.fields:
            field.text = ''
        self.rows.clear_widgets()
        if self._confirmation:
            self._confirmation.dismiss()
            self._confirmation = None
        self.message.text = ''
        if self._popup_timer:
            self._popup_timer.cancel()
            self._popup_timer = None
        if self._popup:
            self._popup.dismiss()
            self._popup = None

    def _set_busy(self, busy):
        self._busy = busy
        self.submit.disabled = busy
        self.refresh.disabled = busy
        self.rows.disabled = busy

    def _run(self, operation, complete):
        if self._busy or not auth_service.is_admin:
            return
        generation = self._generation
        self._set_busy(True)

        def finish(result):
            if generation != self._generation:
                return
            self._set_busy(False)
            if self._visible():
                complete(result)

        def work():
            result = operation()
            Clock.schedule_once(lambda _: finish(result))
        Thread(target=work, daemon=True).start()

    def _load_guards(self, *_):
        self._run(auth_service.list_guards, self._listed)

    def _listed(self, result):
        self.rows.clear_widgets()
        if not result.success:
            self.rows.add_widget(RTLLabel(text=result.error_message, size_hint_y=None, height=50))
            return
        if not result.usernames:
            self.rows.add_widget(RTLLabel(text='هنوز نگهبانی ثبت نشده است', size_hint_y=None, height=48))
        for index, guard in enumerate(result.guards):
            row = Card(size_hint_y=None, height=58, padding=[12, 8], spacing=12,
                       radius=8, hover_effect=False,
                       bg_color=theme.rgba(theme.COLORS['surface_alt' if index % 2 == 0 else 'surface']))
            action = BoxLayout(size_hint_x=None, width=48)
            delete = DeleteGuardButton(pos_hint={'center_y': .5})
            delete.bind(on_release=lambda _, name=guard.username: self._confirm_delete(name))
            action.add_widget(delete)
            row.add_widget(action)
            row.add_widget(RTLLabel(text=guard_date(guard.created_at), size_hint_x=.48,
                                    halign='center', font_size=13,
                                    color=theme.rgba(theme.COLORS['text_secondary'])))
            row.add_widget(RTLLabel(text=guard.username, size_hint_x=.52,
                                    shorten=True, shorten_from='right'))
            self.rows.add_widget(row)

    def _save(self, *_):
        values = tuple(field.text for field in self.fields)
        self._run(lambda: auth_service.create_guard(*values), self._saved)

    def _saved(self, result):
        self.message.text = '' if result.success else theme.rtl(result.error_message)
        if result.success:
            for field in self.fields:
                field.text = ''
            self._notify('نگهبان با موفقیت اضافه شد', 'guard_add')
            self._load_guards()

    def _confirm_delete(self, username):
        if self._busy or not self._visible() or self._confirmation:
            return
        generation = self._generation
        body = BoxLayout(orientation='vertical', padding=20, spacing=16)
        body.add_widget(Icon(name='guard_delete', size_hint=(None, None), size=(44, 44),
                             pos_hint={'center_x': .5}, color=theme.rgba(theme.COLORS['offline'])))
        body.add_widget(RTLLabel(text=f'آیا از حذف نگهبان «{username}» مطمئن هستید؟', halign='center'))
        actions = BoxLayout(size_hint_y=None, height=44, spacing=12)
        cancel = SecondaryButton(text=theme.rtl('انصراف'))
        confirm = DangerButton(text=theme.rtl('بله، حذف شود'))
        actions.add_widget(cancel)
        actions.add_widget(confirm)
        body.add_widget(actions)
        popup = Popup(title='', separator_height=0, content=body, auto_dismiss=False,
                      size_hint=(None, None), size=(440, 260),
                      background='', background_color=theme.rgba(theme.COLORS['surface']))
        self._confirmation = popup

        def clear(*_):
            if self._confirmation is popup:
                self._confirmation = None

        def approve(*_):
            if confirm.disabled:
                return
            confirm.disabled = True
            popup.dismiss()
            if generation == self._generation and self._visible():
                self._delete(username)

        popup.bind(on_dismiss=clear)
        cancel.bind(on_release=lambda *_: popup.dismiss())
        confirm.bind(on_release=approve)
        popup.open()

    def _delete(self, username):
        self._run(lambda: auth_service.delete_guard(username), self._deleted)

    def _deleted(self, result):
        self.message.text = '' if result.success else theme.rtl(result.error_message)
        if result.success:
            self._notify('نگهبان با موفقیت حذف شد', 'guard_remove')
            self._load_guards()

    def _notify(self, message, icon):
        if self._popup_timer:
            self._popup_timer.cancel()
        if self._popup:
            self._popup.dismiss()
        body = BoxLayout(orientation='vertical', padding=20, spacing=16)
        symbol = Icon(name=icon, color=theme.rgba(theme.COLORS['online']),
                      size_hint=(None, None), size=(64, 64), pos_hint={'center_x': .5}, opacity=0)
        body.add_widget(symbol)
        body.add_widget(RTLLabel(text=message, halign='center'))
        popup = Popup(title='', separator_height=0, content=body,
                      size_hint=(None, None), size=(360, 210),
                      background='', background_color=theme.rgba(theme.COLORS['surface']))
        self._popup = popup
        popup.open()
        Animation(opacity=1, duration=.25).start(symbol)
        self._popup_timer = Clock.schedule_once(lambda _: popup.dismiss(), 2)
