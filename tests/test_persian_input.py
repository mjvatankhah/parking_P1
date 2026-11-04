"""Persian alignment policy applies to shared inputs without rewriting user data."""
import unittest
from kivy.clock import Clock
from reno.ui import theme
from reno.ui.components.common import RoundedTextInput
from reno.ui.components.username_input import UsernameInput


class PersianInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        theme.register_app_font()

    def test_free_text_defaults_to_right_alignment(self):
        field = RoundedTextInput()
        field.text = 'گیت ورودی'
        Clock.tick()
        self.assertEqual(field.halign, 'right')
        self.assertEqual(field.text, 'گیت ورودی')

    def test_persian_overrides_left_alignment_and_latin_restores_it(self):
        field = RoundedTextInput(halign='left')
        field.text = 'دوربین شماره ۲'
        Clock.tick()
        self.assertEqual(field.halign, 'right')
        self.assertEqual(field.base_direction, 'rtl')
        field.text = 'rtsp://camera/live'
        Clock.tick()
        self.assertEqual(field.halign, 'left')
        self.assertEqual(field.base_direction, 'ltr')

    def test_numeric_and_username_inputs_keep_their_alignment(self):
        numeric = RoundedTextInput(input_filter='float', halign='center', text='0.5')
        self.assertEqual(numeric.halign, 'left')
        username = UsernameInput()
        Clock.tick()
        username.insert_text('guard_01')
        Clock.tick()
        self.assertEqual(username.halign, 'left')
        self.assertEqual(username.text, 'guard_01')
        username.insert_text('نگهبان')
        self.assertEqual(username.text, 'guard_01')

    def test_multiline_mixed_paste_is_right_aligned_and_keeps_raw_text(self):
        raw = 'شرح درخواست\nCamera 2: دوربین ورودی'
        field = RoundedTextInput(multiline=True)
        Clock.tick()
        field.insert_text(raw)
        Clock.tick()
        self.assertEqual(field.halign, 'right')
        self.assertEqual(field.text, raw)

    def test_actual_persian_texture_is_shaped_and_ordered(self):
        from kivy.uix.textinput import TextInput
        field = RoundedTextInput(size=(420, 48))
        Clock.tick()
        for char in 'گیت ورودی':
            field.insert_text(char)
            Clock.tick()
        expected = TextInput._create_line_label(field, theme.rtl(field.text))
        actual = field._create_line_label(field.text)
        self.assertEqual(actual.size, expected.size)
        self.assertEqual(actual.pixels, expected.pixels)
        self.assertEqual(field.text, 'گیت ورودی')

    def test_persian_end_cursor_is_at_visual_left(self):
        field = RoundedTextInput(text='گیت ورودی', size=(420, 48))
        Clock.tick()
        field.cursor = (len(field.text), 0)
        self.assertAlmostEqual(field.cursor_offset(), 0, delta=1)

    def test_click_and_arrow_follow_visual_persian_positions(self):
        field = RoundedTextInput(text='گیت ورودی', size=(420, 48))
        Clock.tick()
        field.cursor = (len(field.text), 0)
        field.do_cursor_movement('cursor_right')
        self.assertEqual(field.cursor_col, len(field.text) - 1)
        field.do_cursor_movement('cursor_left')
        self.assertEqual(field.cursor_col, len(field.text))
        for col in (0, 2, 5, len(field.text)):
            field.cursor = (col, 0)
            Clock.tick()
            x, y = field.cursor_pos
            self.assertEqual(field.get_cursor_from_xy(x, y - field.line_height / 2), (col, 0))

    def test_mid_text_edit_backspace_selection_and_undo_preserve_logical_unicode(self):
        field = RoundedTextInput(text='دوربین ورودی', size=(420, 48))
        Clock.tick()
        field.cursor = (6, 0)
        field.insert_text(' جدید')
        Clock.tick()
        self.assertEqual(field.text, 'دوربین جدید ورودی')
        field.do_undo()
        Clock.tick()
        self.assertEqual(field.text, 'دوربین ورودی')
        field.cursor = (len(field.text), 0)
        field.do_backspace()
        Clock.tick()
        self.assertEqual(field.text, 'دوربین ورود')
        field.select_text(0, 6)
        self.assertEqual(field.selection_text, 'دوربین')
        field.delete_selection()
        Clock.tick()
        self.assertEqual(field.text, ' ورود')

    def test_delete_key_removes_next_logical_character(self):
        field = RoundedTextInput(text='دوربین', size=(420, 48))
        Clock.tick()
        field.cursor = (2, 0)
        field._key_down(('', '', 'del', 1))
        Clock.tick()
        self.assertEqual(field.text, 'دوبین')

    def test_mixed_names_digits_half_spaces_and_multiline_render_without_mutation(self):
        from kivy.uix.textinput import TextInput
        samples = ('دوربین Camera 12', 'گیت شمالی ۱۲۳', 'می\u200cنویسم', 'سلام', 'نَام', 'متن \u2066Camera\u2069 فارسی')
        for raw in samples:
            with self.subTest(raw=raw):
                field = RoundedTextInput(text=raw, size=(420, 48))
                Clock.tick()
                texture = field._create_line_label(raw)
                self.assertGreater(texture.width, 0)
                self.assertEqual(field.text, raw)
                for col in range(len(raw)+1):
                    field.cursor = (col, 0)
                    self.assertGreaterEqual(field.cursor_offset(), 0)
                    self.assertLessEqual(field.cursor_offset(), texture.width)
        field = RoundedTextInput(text='گیت ورودی\nدوربین خروجی', multiline=True, size=(420, 140))
        Clock.tick()
        field.cursor = (len('دوربین خروجی'), 1)
        self.assertAlmostEqual(field.cursor_offset(), 0, delta=1)
        self.assertEqual(field.text, 'گیت ورودی\nدوربین خروجی')

    def test_password_uses_mask_without_shaping_or_changing_length(self):
        from kivy.uix.textinput import TextInput
        field = RoundedTextInput(text='رمز فارسی', password=True)
        Clock.tick()
        actual = field._create_line_label(field.text)
        expected = TextInput._create_line_label(field, field.text)
        self.assertEqual(actual.pixels, expected.pixels)
        self.assertEqual(field.text, 'رمز فارسی')

    def test_password_starts_at_left_and_grows_right_even_with_persian_characters(self):
        field = RoundedTextInput(password=True, halign='right', size=(420, 48))
        Clock.tick()
        self.assertEqual(field.halign, 'left')
        previous_x = field.cursor_pos[0]
        self.assertAlmostEqual(previous_x, field.x + field.padding[0], delta=1)
        for char in 'رمز12':
            field.insert_text(char)
            Clock.tick()
            self.assertEqual(field.base_direction, 'ltr')
            self.assertGreater(field.cursor_pos[0], previous_x)
            previous_x = field.cursor_pos[0]
        self.assertEqual(field.text, 'رمز12')

    def test_numeric_text_is_left_aligned_without_reordering_digits(self):
        field = RoundedTextInput(size=(420, 48))
        for value in ('12345', '۱۲۳۴۵', '-0.25', '۱۲٫۵'):
            field.text = value
            Clock.tick()
            self.assertEqual(field.halign, 'left')
            self.assertEqual(field.base_direction, 'ltr')
            self.assertEqual(field.text, value)
        field.text = 'گیت ۱۲'
        Clock.tick()
        self.assertEqual(field.halign, 'right')
        self.assertEqual(field.base_direction, 'rtl')
