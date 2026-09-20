"""
ui/components/stat_card.py

The Dashboard's two headline statistic cards (today / this week
entry-exit counts). These are the one deliberate exception to "every
card is a flat neutral surface": each gets a subtle two-tone vertical
gradient (dark shade of the accent -> the accent itself), giving the
dashboard a bit of premium depth on its most-looked-at numbers without
turning the whole app into a colorful template. Every other card in
the app (camera panel, records table, forms, Settings, Search/Reports)
stays flat and neutral - see ui/components/common.py's Card.

Both gradient stops are chosen dark/mid-toned on purpose so white text
stays readable across the whole card, not just one end of it.

The number animates with a quick count-up whenever set_value() is
called, instead of snapping instantly - a small, purposeful motion
that draws the eye to "this number just changed."
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.graphics import Color, RoundedRectangle
from kivy.properties import NumericProperty
from kivy.animation import Animation

from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.ui.theme import COLORS, FONT_SIZE, SPACING
from computer_vision_v2.reno.ui.components.common import Card, RTLLabel
from computer_vision_v2.reno.ui.components.icons import Icon

# (gradient top, gradient bottom) per stat - dark-to-medium so white
# text reads clearly everywhere on the card.
GRADIENT_TEAL = ("#23B99B", "#65CF89")
GRADIENT_BLUE = ("#587FCE", "#52C8D7")
GRADIENT_ORANGE = ("#F06B35", "#FFC43D")
GRADIENT_CRIMSON = ("#B41342", "#DE2943")


class StatCard(Card):
    _display_value = NumericProperty(0)

    def __init__(self, title: str, value, subtitle: str = "", icon_name: str = "reports",
                 gradient=GRADIENT_TEAL, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("padding", [SPACING["md"], SPACING["md"], SPACING["md"], SPACING["md"]])
        kwargs.setdefault("spacing", SPACING["md"])
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", 104)
        kwargs["gradient"] = gradient
        kwargs["border_color"] = theme.rgba(gradient[1], 0.6)
        super().__init__(**kwargs)

        icon_wrap = _IconBadge(icon_name=icon_name)

        text_col = BoxLayout(orientation="vertical", spacing=2)
        self._value_label = Label(
            text=str(value),
            font_name=theme.APP_FONT_NAME,
            font_size=FONT_SIZE["display"],
            bold=True,
            color=(1, 1, 1, 1),
            halign="right",
            valign="middle",
            size_hint_y=None,
            height=36,
        )
        self._value_label.bind(size=lambda w, *_: setattr(w, "text_size", w.size))

        title_label = RTLLabel(
            text=title,
            font_size=FONT_SIZE["caption"],
            color=(1, 1, 1, 0.85),
            valign="top",
            size_hint_y=None,
            height=18,
        )

        text_col.add_widget(self._value_label)
        text_col.add_widget(title_label)

        if subtitle:
            subtitle_label = RTLLabel(
                text=subtitle,
                font_size=FONT_SIZE["caption"],
                color=(1, 1, 1, 0.65),
                valign="top",
                size_hint_y=None,
                height=16,
            )
            text_col.add_widget(subtitle_label)

        self.add_widget(text_col)
        self.add_widget(icon_wrap)

        self._display_value = value
        self.bind(_display_value=self._on_display_value_changed)

    def set_value(self, value):
        """Update the number with a short count-up animation instead
        of an instant snap."""
        Animation.cancel_all(self, "_display_value")
        Animation(_display_value=value, duration=0.5, t="out_quad").start(self)

    def _on_display_value_changed(self, _widget, value):
        self._value_label.text = str(int(round(value)))


class _IconBadge(BoxLayout):
    """A translucent-white rounded square holding the stat's icon,
    sitting on top of the card's own gradient."""

    def __init__(self, icon_name, **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (48, 48))
        super().__init__(**kwargs)
        with self.canvas.before:
            self._color = Color(1, 1, 1, 0.16)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[10])
        self.bind(pos=self._redraw, size=self._redraw)
        self.add_widget(Icon(name=icon_name, color=(1, 1, 1, 1), size_hint=(None, None), size=(22, 22),
                              pos_hint={"center_x": 0.5, "center_y": 0.5}))

    def _redraw(self, *args):
        self._rect.pos = self.pos
        self._rect.size = self.size
