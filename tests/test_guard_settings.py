"""Guard management UI contracts with no live DB or account mutations."""
import unittest
from unittest.mock import patch
from pathlib import Path
from kivy.uix.screenmanager import ScreenManager, NoTransition
from kivy.clock import Clock
from reno.ui.theme import register_app_font
from reno.ui.guard_settings import GuardSettingsScreen, DeleteGuardButton, guard_date
from reno.ui.components.icons import APP_ICON, Icon
from reno.ui.components.common import DangerButton
from reno.services.auth_service import auth_service, GuardListResult, LoginResult, GuardAccount


class GuardSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        register_app_font()

    def setUp(self):
        auth_service.current_role = 'admin'
        self.manager = ScreenManager(transition=NoTransition())
        self.screen = GuardSettingsScreen(name='guard_settings')
        with patch.object(self.screen, '_load_guards'):
            self.manager.add_widget(self.screen)

    def tearDown(self):
        self.screen.on_leave()
        auth_service.logout()

    def test_list_has_a_delete_button_for_each_guard(self):
        self.screen._listed(GuardListResult(True, (GuardAccount('guard1'), GuardAccount('guard2'))))
        self.assertEqual(len(self.screen.rows.children), 2)
        buttons = [w for w in self.screen.rows.walk() if isinstance(w, DeleteGuardButton)]
        self.assertEqual(len(buttons), 2)
        with patch.object(self.screen, '_delete') as delete:
            buttons[0].dispatch('on_release')
            delete.assert_not_called()
            self.assertIsNotNone(self.screen._confirmation)
            confirm = next(w for w in self.screen._confirmation.content.walk() if isinstance(w, DangerButton))
            confirm.dispatch('on_release')
            self.assertIn(delete.call_args.args[0], ('guard1', 'guard2'))

    def test_success_shows_visual_popup_and_refreshes(self):
        for callback, icon in [(self.screen._saved, 'guard_add'), (self.screen._deleted, 'guard_remove')]:
            with patch.object(self.screen, '_load_guards') as refresh:
                callback(LoginResult(True))
                refresh.assert_called_once()
                self.assertIsNotNone(self.screen._popup)
                symbols = [w for w in self.screen._popup.content.walk() if isinstance(w, Icon)]
                self.assertEqual(symbols[0].name, icon)
                self.assertIsNotNone(symbols[0]._texture)
                self.assertIsNotNone(self.screen._popup_timer)
        self.screen.on_leave()
        self.assertIsNone(self.screen._popup)
        self.assertIsNone(self.screen._popup_timer)
        self.assertFalse(self.screen.rows.children)

    def test_failure_does_not_show_success_or_refresh(self):
        with patch.object(self.screen, '_notify') as notify, patch.object(self.screen, '_load_guards') as refresh:
            self.screen._deleted(LoginResult(False, 'خطا'))
            notify.assert_not_called()
            refresh.assert_not_called()
            self.assertTrue(self.screen.message.text)

    def test_guard_cannot_request_list_or_mutations(self):
        auth_service.current_role = 'guard'
        with patch.object(auth_service, 'list_guards') as listing, patch.object(auth_service, 'delete_guard') as delete:
            self.screen._load_guards()
            self.screen._delete('g')
            listing.assert_not_called()
            delete.assert_not_called()

    def test_app_icon_exists(self):
        self.assertTrue(Path(APP_ICON).is_file())

    def test_cancel_does_not_delete_and_leaving_closes_confirmation(self):
        from reno.ui.components.common import SecondaryButton
        with patch.object(self.screen, '_delete') as delete:
            self.screen._confirm_delete('guard1')
            popup = self.screen._confirmation
            cancel = next(w for w in popup.content.walk() if isinstance(w, SecondaryButton))
            cancel.dispatch('on_release')
            delete.assert_not_called()
            self.screen.on_leave()
            self.assertIsNone(self.screen._confirmation)

    def test_unknown_dates_and_green_refresh_above_table_left(self):
        self.assertEqual(guard_date(None), 'ثبت نشده')
        self.assertGreater(self.screen.refresh.bg_color_normal[1], self.screen.refresh.bg_color_normal[0])
        self.assertIs(self.screen.refresh.parent.children[-1], self.screen.refresh)
        self.assertIs(self.screen.rows.parent.children[-1], self.screen.refresh.parent)

    def test_password_mismatch_is_red(self):
        from reno.ui import theme
        self.screen._saved(LoginResult(False, 'تکرار رمز عبور یکسان نیست'))
        self.assertEqual(tuple(self.screen.message.color), theme.rgba('#F87171'))
        self.assertEqual(self.screen.message.text, theme.rtl('تکرار رمز عبور یکسان نیست'))

    def test_username_rejects_persian_typing_and_mixed_paste_then_accepts_english(self):
        from reno.ui.login import LoginScreen
        from reno.ui.components.username_input import UsernameInput
        login = LoginScreen(name='login')
        for field in (login._username_input, self.screen.fields[0]):
            self.assertIsInstance(field, UsernameInput)
            field.insert_text('نگهبان')
            self.assertEqual(field.text, '')
            self.assertTrue(field.input_error)
            field.insert_text('guard_۱۲')
            self.assertEqual(field.text, '')
            Clock.tick()
            field.insert_text('guard_01')
            self.assertEqual(field.text, 'guard_01')
            self.assertEqual(field.input_error, '')
            Clock.tick()
            field.insert_text('ف')
            self.assertEqual(field.text, 'guard_01')
