"""
ui/theme.py

One place for every color, spacing value and font used across RENO.
Every screen and component imports from here instead of hard-coding
its own colors, so the whole app stays visually consistent and a
future color change only has to happen once.

This file also solves the two Persian-text problems mentioned in the
project brief:

1. "Persian text renders as squares."
   That happens when the active font has no Arabic/Persian glyphs at
   all (Kivy's bundled default font, Roboto, is one such font). The
   fix is to register a font that DOES contain those glyphs - see
   `register_app_font()` below.

2. Persian letters need to be joined together (reshaped) and the
   whole line needs to be laid out right-to-left. Kivy's Label does
   not do this by itself. The fix is the `rtl()` helper below: run
   every piece of Persian text through `rtl(text)` before putting it
   into a Label's `.text`.
"""

import os

# ---------------------------------------------------------------------
# 1. COLOR PALETTE
# ---------------------------------------------------------------------
# Restrained graphite surfaces and accessible semantic accents.
COLORS = {
    "action": "#3F6695",
    "action_hover": "#4B75A5",
    "primary": "#91B4DF",
    "primary_dark": "#345780",
    "primary_light": "#26364B",

    # Neutral surfaces keep the dense desktop UI readable.
    "background": "#101419",
    "surface": "#191F27",
    "surface_alt": "#202832",
    "sidebar": "#141920",
    "border": "#303B49",
    "border_strong": "#91B4DF",

    "text_primary": "#E8EDF3",
    "text_secondary": "#A5B1C0",
    "text_on_primary": "#FFFFFF",
    "placeholder": "#98A7B9",

    "online": "#8DC8AF",
    "offline": "#DF9A9F",
    "warning": "#DABB89",
    "info": "#91B4DF",

    # Shared entry/exit accents for event chips and chart series.
    "entry": "#57C595",
    "entry_surface": "#214D3C",
    "entry_border": "#39795D",
    "entry_text": "#4A9672",
    "exit": "#E47D87",
    "exit_surface": "#592D36",
    "exit_border": "#91505D",
    "exit_text": "#B4627C",

    "accent_teal": "#83B6BA",
    "accent_blue": "#8AAED6",
    "accent_purple": "#B0A5D1",
    "accent_orange": "#C5A583",
    "accent_red": "#D4969F",

    "hover_overlay": "#91B4DF10",
    "pressed_overlay": "#91B4DF20",
    "disabled_bg": "#252D38",
    "disabled_text": "#91A0B3",
    "focus_ring": "#91B4DF",

    "shadow": "#00000044",
    "overlay": "#061620BB",

    # Decorative background washes.
    "glow_teal": "#91B4DF14",
    "glow_blue": "#8AAED612",
}

PAGE_BG_TOP = "#141920"
PAGE_BG_BOTTOM = "#101419"



def rgba(hex_color: str, alpha: float = 1.0):
    """Convert '#RRGGBB' into a Kivy-style (r, g, b, a) tuple of floats
    in the 0..1 range."""
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return (r, g, b, alpha)


# ---------------------------------------------------------------------
# 2. SPACING / SIZING
# ---------------------------------------------------------------------
SPACING = {
    "xs": 6,
    "sm": 10,
    "md": 16,
    "lg": 24,
    "xl": 32,
}

RADIUS = {
    "sm": 8,
    "md": 12,
    "lg": 16,
}

FONT_SIZE = {
    "caption": 13,
    "body": 15,
    "subtitle": 17,
    "title": 22,
    "display": 30,
}

# Persian text needs more breathing room between lines than Latin text
# (taller glyphs, diacritics). Multi-line Persian labels should set
# line_height=LINE_HEIGHT_FA instead of Kivy's default of 1.0.
LINE_HEIGHT_FA = 1.35

# Every animation in the app (button feedback, hover, sidebar active
# state, dialogs) uses one of these two durations, so motion feels
# consistent instead of every screen inventing its own timing.
ANIM_FAST = 0.07   # micro-feedback: button press, checkbox
ANIM_NORMAL = 0.18  # state changes: sidebar selection, card hover

SIDEBAR_WIDTH = 188


# ---------------------------------------------------------------------
# 3. FONT REGISTRATION (fixes "Persian shows as squares")
# ---------------------------------------------------------------------
APP_FONT_NAME = "Vazirmatn"

# Where we look for a bundled Persian font, in priority order.
# The first one that exists on disk is used.
_ASSETS_FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")

_FONT_CANDIDATES_REGULAR = [
    os.path.join(_ASSETS_FONTS_DIR, "Vazirmatn-Regular.ttf"),
    os.path.join(_ASSETS_FONTS_DIR, "Vazirmatn-Regular.otf"),
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/tahoma.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Tahoma.ttf",
]

_FONT_CANDIDATES_BOLD = [
    os.path.join(_ASSETS_FONTS_DIR, "Vazirmatn-Bold.ttf"),
    os.path.join(_ASSETS_FONTS_DIR, "Vazirmatn-Bold.otf"),
]


def _first_existing(paths):
    for path in paths:
        if os.path.isfile(path):
            return path
    return None


def register_app_font():
    """Register the bundled Vazirmatn font under the app-wide font name.

    Call this once, before any Kivy widget is created (main.py does
    this first thing). After this call, every component in this
    project uses the same font name and Persian text renders with
    real glyphs instead of little squares.

    If no Persian-capable font can be found at all (a bare Linux
    machine with none of the fallbacks installed), Kivy's default
    font is used and a warning is printed - the app still runs, only
    Persian text will look wrong until a font is installed. See
    assets/fonts/README.md for how to add the recommended font.
    """
    from kivy.core.text import LabelBase

    regular = _first_existing(_FONT_CANDIDATES_REGULAR)
    bold = _first_existing(_FONT_CANDIDATES_BOLD) or regular

    if regular is None:
        print(
            "[RENO] WARNING: no Persian-capable font was found. "
            "Persian text may not render correctly. "
            "See assets/fonts/README.md to install one."
        )
        return

    LabelBase.register(
        name=APP_FONT_NAME,
        fn_regular=regular,
        fn_bold=bold,
        fn_italic=regular,
        fn_bolditalic=bold,
    )


# ---------------------------------------------------------------------
# 4. PERSIAN / RTL TEXT HELPER (fixes "letters aren't joined/reordered")
# ---------------------------------------------------------------------
try:
    import arabic_reshaper
except ImportError:
    arabic_reshaper = None

# python-bidi has changed where get_display() lives between versions:
#   - versions <= 0.4.x and >= 0.6.0 : bidi.algorithm.get_display
#   - version 0.5.x (and the "new" API in 0.6+)  : bidi.get_display
# Try both so this works no matter which version pip installed.
get_display = None
try:
    from bidi.algorithm import get_display
except ImportError:
    try:
        from bidi import get_display
    except ImportError:
        get_display = None

_RTL_LIBS_AVAILABLE = arabic_reshaper is not None and get_display is not None

if not _RTL_LIBS_AVAILABLE:
    print(
        "[RENO] WARNING: arabic_reshaper / python-bidi could not be "
        "imported. Persian text will show as disconnected letters in "
        "the wrong order until this is fixed. Run:\n"
        "    pip install --upgrade arabic-reshaper python-bidi\n"
        "then restart the app."
    )


def rtl(text: str) -> str:
    """Prepare Persian/Arabic text for display in a Kivy Label.

    Kivy draws each character left-to-right with no shaping, so raw
    Persian text looks disconnected and in the wrong order. This
    function:
      1. "reshapes" the text so letters join the way they do in
         normal handwriting/print (arabic_reshaper).
      2. reorders it for correct right-to-left display (python-bidi).

    Every Label/Button/TextInput in this project that shows Persian
    text should wrap it with rtl(...), e.g.:

        Label(text=rtl("داشبورد"), font_name=theme.APP_FONT_NAME)

    If the two helper libraries aren't installed yet (see
    requirements.txt), the original text is returned unchanged so the
    app still runs - the Persian text just won't be shaped/reordered.
    """
    if not text:
        return text
    if not _RTL_LIBS_AVAILABLE:
        return text
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)


def rtl_map(labels_by_key: dict):
    """Turn a {key: "persian label"} dict (as used throughout models/)
    into the two things every dropdown/spinner in this app needs:

        display_values, value_by_display = rtl_map(SOURCE_TYPE_LABELS)
        spinner.values = display_values          # what the user sees
        chosen_key = value_by_display[spinner.text]   # back to the real key

    This exists because a raw dict value handed straight to a Spinner
    is never reshaped/reordered, which was a real bug found during the
    UI audit: dropdown text showed disconnected Persian letters even
    though every Label elsewhere used rtl(). Routing every dropdown
    through this one function means that class of bug can only be
    fixed (or reintroduced) in one place.
    """
    value_by_display = {}
    display_values = []
    for key, label in labels_by_key.items():
        display = rtl(label)
        display_values.append(display)
        value_by_display[display] = key
    return display_values, value_by_display


def fa_number(value):
    """Persian digits for visual numbers; stored identifiers remain untouched."""
    return str(value).translate(str.maketrans('0123456789,', '۰۱۲۳۴۵۶۷۸۹٬'))
