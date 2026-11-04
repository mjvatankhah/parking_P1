"""Username entry that rejects non-English typing and pastes as a whole."""
from kivy.properties import StringProperty
from reno.models.username import is_username_text, USERNAME_LANGUAGE_ERROR
from reno.ui.components.common import RoundedTextInput


class UsernameInput(RoundedTextInput):
    input_error = StringProperty('')

    def __init__(self, **kwargs):
        kwargs.setdefault('halign', 'left')
        super().__init__(**kwargs)

    def insert_text(self, substring, from_undo=False):
        if substring and not is_username_text(substring):
            self.input_error = USERNAME_LANGUAGE_ERROR
            return
        self.input_error = ''
        return super().insert_text(substring, from_undo=from_undo)
