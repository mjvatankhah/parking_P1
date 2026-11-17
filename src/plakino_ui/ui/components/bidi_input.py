"""Editable logical Unicode with shaped visual lines for Kivy's SDL2 provider.

Only display textures and visual coordinates are transformed. TextInput retains
its original Unicode for insertion, deletion, selection, undo and persistence.
Pango already shapes text, so the fallback is disabled for that provider.
"""
from functools import lru_cache
from unicodedata import bidirectional

from arabic_reshaper import ArabicReshaper
from bidi import algorithm as bidi
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Rectangle
from kivy.uix.textinput import TextInput

_RESHAPER = ArabicReshaper(configuration={
    'support_ligatures': False, 'delete_harakat': False,
    'shift_harakat_position': False, 'delete_tatweel': False,
})
_NATIVE_BIDI = 'pango' in CoreLabel.__module__


def needs_bidi(text):
    return not _NATIVE_BIDI and any(bidirectional(c) in ('R', 'AL') for c in text)


@lru_cache(maxsize=256)
def visual_line(text, tab_width=4):
    """Return visual glyphs plus their logical character indices and directions."""
    expanded, indices = [], []
    for index, char in enumerate(text):
        if char == '\n':
            continue
        chars = ' ' * tab_width if char == '\t' else char
        expanded.extend(chars)
        indices.extend([index] * len(chars))
    shaped = _RESHAPER.reshape(''.join(expanded))
    # Reshaper consumes ZWJ after using it to choose joining forms.
    indices = [index for char, index in zip(expanded, indices) if char != '\u200d']
    # python-bidi's Python implementation handles embeddings but not isolates.
    # Keep their direction in the display copy; logical text remains unchanged.
    shaped = shaped.translate(str.maketrans({'\u2066': '\u202a', '\u2067': '\u202b',
                                            '\u2068': '\u202b', '\u2069': '\u202c'}))
    storage = bidi.get_empty_storage()
    storage['base_level'] = bidi.get_base_level(text)
    storage['base_dir'] = ('L', 'R')[storage['base_level']]
    bidi.get_embedding_levels(shaped, storage)
    for char, index in zip(storage['chars'], indices):
        char['logical_index'] = index
    bidi.explicit_embed_and_overrides(storage)
    bidi.resolve_weak_types(storage)
    bidi.resolve_neutral_types(storage, False)
    bidi.resolve_implicit_levels(storage, False)
    bidi.reorder_resolved_levels(storage, False)
    bidi.apply_mirroring(storage, False)
    chars = storage['chars']
    return (''.join(char['ch'] for char in chars),
            tuple(char['logical_index'] for char in chars),
            tuple(char['level'] % 2 for char in chars))


class BidiTextInput(TextInput):
    def _display_line(self, text, tab_width):
        return visual_line(text, tab_width)

    def _visual(self, text):
        return not self.password and needs_bidi(text)

    def _create_line_label(self, text, hint=False):
        # Existing hint strings are already formatted by theme.rtl().
        if not hint and self._visual(text):
            text = self._display_line(text, self.tab_width)[0]
        return super()._create_line_label(text, hint=hint)

    def _get_text_width(self, text, tab_width, label_cached):
        if self._visual(text):
            text = self._display_line(text, tab_width)[0]
        return super()._get_text_width(text, tab_width, label_cached)

    def _visual_geometry(self, row):
        line = self._lines[row]
        display, order, directions = self._display_line(line, self.tab_width)
        # Measure the shaped full line rather than reshaping isolated prefixes:
        # Persian letter widths depend on the adjacent letters.
        edges = [super(BidiTextInput, self)._get_text_width(
            display[:i], self.tab_width, self._label_cached) for i in range(len(display) + 1)]
        stops = [None] * (len(line) + 1)
        for visual, (logical, rtl) in enumerate(zip(order, directions)):
            leading = edges[visual + 1] if rtl else edges[visual]
            trailing = edges[visual] if rtl else edges[visual + 1]
            if logical == 0:
                stops[0] = leading
            stops[logical + 1] = trailing
        # Invisible controls such as ZWNJ share their neighbour's caret stop.
        previous = stops[0] if stops[0] is not None else (edges[-1] if bidi.get_base_level(line) else 0)
        for index, stop in enumerate(stops):
            if stop is None:
                stops[index] = previous
            else:
                previous = stop
        return stops, edges, order

    def cursor_offset(self):
        row = int(self.cursor_row)
        if row < len(self._lines) and self._visual(self._lines[row]):
            stops, _, _ = self._visual_geometry(row)
            return stops[min(int(self.cursor_col), len(stops) - 1)]
        return super().cursor_offset()

    def _line_origin(self, row):
        width = self.width - self.padding[0] - self.padding[2]
        extra = max(0, width - self._get_row_width(row))
        offset = extra if self.halign == 'right' else extra / 2 if self.halign == 'center' else 0
        return self.x + self.padding[0] + offset - self.scroll_x

    def get_cursor_from_xy(self, x, y):
        col, row = super().get_cursor_from_xy(x, y)
        if self._visual(self._lines[row]):
            stops, _, _ = self._visual_geometry(row)
            target = x - self._line_origin(row)
            col = min(range(len(stops)), key=lambda i: abs(stops[i] - target))
        return col, row

    def do_cursor_movement(self, action, control=False, alt=False):
        col, row = self.cursor
        if self._lines and self._visual(self._lines[row]) and action in ('cursor_left', 'cursor_right'):
            if control:
                if bidi.get_base_level(self._lines[row]):
                    action = 'cursor_right' if action == 'cursor_left' else 'cursor_left'
            elif not alt:
                stops, _, _ = self._visual_geometry(row)
                offset = stops[col]
                candidates = [i for i, stop in enumerate(stops)
                              if (stop < offset if action == 'cursor_left' else stop > offset)]
                if candidates:
                    self.cursor = min(candidates, key=lambda i: (abs(stops[i] - offset), abs(i-col))), row
                    return
                # At the visual edge, preserve Kivy's logical line crossing.
                if bidi.get_base_level(self._lines[row]):
                    action = 'cursor_right' if action == 'cursor_left' else 'cursor_left'
        return super().do_cursor_movement(action, control=control, alt=alt)

    def _key_down(self, key, repeat=False):
        # Kivy implements Delete by moving right then backspacing. That move
        # must remain logical even when arrow keys move visually through RTL.
        if key[2] == 'del' and not self._selection and self._lines and self._visual(self._lines[self.cursor_row]):
            cursor = self.cursor
            TextInput.do_cursor_movement(self, 'cursor_right')
            if cursor != self.cursor:
                self.do_backspace(mode='del')
            return
        return super()._key_down(key, repeat=repeat)

    def _draw_selection(self, pos, size, line_num, selection_start, selection_end,
                        lines, get_text_width, tab_width, label_cached,
                        width_minus_padding, padding_left, padding_right, x,
                        canvas_add, selection_color):
        if not self._visual(lines[line_num]):
            return super()._draw_selection(pos, size, line_num, selection_start, selection_end,
                                           lines, get_text_width, tab_width, label_cached,
                                           width_minus_padding, padding_left, padding_right,
                                           x, canvas_add, selection_color)
        if not selection_start[1] <= line_num <= selection_end[1]:
            return
        start = selection_start[0] if line_num == selection_start[1] else 0
        end = selection_end[0] if line_num == selection_end[1] else len(lines[line_num])
        _, edges, order = self._visual_geometry(line_num)
        origin = self._line_origin(line_num)
        left, right = self.x + padding_left, self.right - padding_right
        for visual, logical in enumerate(order):
            if start <= logical < end:
                a, b = max(left, origin + edges[visual]), min(right, origin + edges[visual + 1])
                if b > a:
                    canvas_add(Color(*selection_color, group='selection'))
                    canvas_add(Rectangle(pos=(a, pos[1]), size=(b-a, size[1]), group='selection'))
