"""Shared ASCII username policy for UI input and authentication services."""
USERNAME_LANGUAGE_ERROR = 'نام کاربری را با کیبورد انگلیسی وارد کنید'


def is_username_text(value: str) -> bool:
    """Allow visible ASCII letters, numbers and punctuation, without whitespace."""
    return bool(value) and all(33 <= ord(char) <= 126 for char in value)
