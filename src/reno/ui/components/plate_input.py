"""Editable Iranian plate groups in physical left-to-right order."""
import re
from computer_vision_v2.database.plate_access import normalize_plate
from reno.ui.components.common import RoundedTextInput
from reno.ui.components.bidi_input import visual_line
from reno.ui.theme import rtl


# Hints are already display-ready in BidiTextInput. Shape only the letter:
# applying RTL to the entire example would reorder the physical plate groups.
PLATE_HINT = '۱۲ ' + rtl('ب') + ' ۳۴۵ | ۶۷'


def format_plate(value):
    raw = normalize_plate(value)
    match = re.fullmatch(r'([0-9]{0,2})([\u0621-\u063a\u0641-\u064a\u067e\u0686\u0698\u06a9\u06af\u06cc]*)([0-9]{0,5})', raw)
    if not match:
        return None
    first, letter, tail = match.groups()
    if letter and (len(first) != 2 or (len(letter) > 1 and letter not in ('ال', 'الف'))):
        return None
    if tail and (not letter or letter == 'ال'):
        return None
    return ' '.join(part for part in (first, letter, tail[:3], tail[3:]) if part)


class PlateSearchInput(RoundedTextInput):
    def _sync_text_direction(self, *_):
        self.halign = 'left'
        self.base_direction = 'ltr'
        self.text_language = None

    def _display_line(self, text, tab_width):
        # Shape each Persian letter group independently, keeping numeric groups
        # in their physical plate order. Preserve logical indices for editing.
        glyphs, indices, directions = [], [], []
        for match in re.finditer(r'\S+|\s+', text):
            display, order, levels = visual_line(match.group(), tab_width)
            glyphs.append(display)
            indices.extend(match.start() + index for index in order)
            directions.extend(levels)
        return ''.join(glyphs), tuple(indices), tuple(directions)

    def _replace(self, start, end, replacement):
        prefix = self.text[:start] + replacement
        candidate = prefix + self.text[end:]
        formatted = format_plate(candidate)
        if formatted is None:
            return
        count = len(normalize_plate(prefix))
        self.cancel_selection()
        self.text = formatted
        # Locate the logical caret by counting non-separator characters.
        position = 0
        while position < len(formatted) and count:
            if formatted[position] != ' ':
                count -= 1
            position += 1
        self.cursor = self.get_cursor_from_index(position)

    def insert_text(self, substring, from_undo=False):
        if self.readonly:
            return
        if self.selection_text:
            start, end = sorted((self.selection_from, self.selection_to))
        else:
            start = end = self.cursor_index()
        self._replace(start, end, substring)

    def do_backspace(self, from_undo=False, mode='bkspc'):
        if self.readonly:
            return
        if self.selection_text:
            start, end = sorted((self.selection_from, self.selection_to))
        else:
            end = self.cursor_index()
            start = end - 1
            while start >= 0 and self.text[start] == ' ':
                start -= 1
            if start < 0:
                return
        self._replace(start, end, '')

    def _key_down(self, key, repeat=False):
        if key[2] == 'del' and not self.selection_text:
            start = self.cursor_index()
            end = start
            while end < len(self.text) and self.text[end] == ' ':
                end += 1
            self._replace(start, min(end + 1, len(self.text)), '')
            return
        return super()._key_down(key, repeat=repeat)
