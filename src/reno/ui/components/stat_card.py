"""HTML statistic layout: caption, number beside outline icon, explanatory line."""
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.anchorlayout import AnchorLayout
from kivy.properties import NumericProperty
from kivy.animation import Animation
from reno.ui import theme
from reno.ui.components.common import Card, RTLLabel
from reno.ui.components.icons import Icon

GRADIENT_TEAL = ('#39F5D0', '#247DAD')
GRADIENT_CYAN = ('#40E8FF', '#3566C7')
GRADIENT_BLUE = ('#B78AFF', '#435ED6')
GRADIENT_ORANGE = ('#FFD16A', '#D46B32')
GRADIENT_CRIMSON = ('#FF718F', '#AA386B')


class StatCard(Card):
    _display_value = NumericProperty(0)

    def __init__(self, title, value, subtitle='', icon_name='reports', gradient=GRADIENT_TEAL,
                 value_color=None, **kwargs):
        kwargs.setdefault('orientation', 'vertical')
        kwargs.setdefault('padding', [18, 16, 18, 14])
        kwargs.setdefault('spacing', 8)
        kwargs.setdefault('size_hint_y', None)
        kwargs.setdefault('height', 118)
        kwargs.setdefault('radius', 14)
        kwargs['border_gradient'] = gradient
        kwargs['animated_border'] = True
        kwargs['hover_effect'] = True
        kwargs['bg_color'] = theme.rgba(theme.DASHBOARD_COLORS['surface'])
        kwargs['border_color'] = theme.rgba(theme.DASHBOARD_COLORS['border'])
        super().__init__(**kwargs)
        self._total = None
        self._target_value = value
        heading = BoxLayout(size_hint_y=None, height=36, spacing=12)
        badge = Card(size_hint=(None, None), size=(36, 36), radius=11, padding=0,
                     hover_effect=False, bg_color=theme.rgba(gradient[0], .13),
                     border_color=(0, 0, 0, 0))
        icon_holder = AnchorLayout()
        icon_holder.add_widget(Icon(name=icon_name, color=theme.rgba(gradient[0]),
                                   size_hint=(None, None), size=(18, 18)))
        badge.add_widget(icon_holder)
        heading.add_widget(badge)
        self._title_label = RTLLabel(text=title, font_size=12, padding=[0, 0],
                                    color=theme.rgba(theme.DASHBOARD_COLORS['muted']))
        heading.add_widget(self._title_label)
        self.add_widget(heading)
        self._value_label = Label(text=theme.fa_number(value), markup=True,
            font_name=theme.APP_FONT_NAME, font_size=28, bold=True,
            color=theme.rgba(value_color or theme.COLORS['text_primary']),
            halign='right', valign='middle')
        self._value_label.bind(size=lambda w, *_: setattr(w, 'text_size', w.size))
        self.add_widget(self._value_label)
        self._subtitle_label = RTLLabel(text=subtitle, font_size=11, padding=[0, 0],
            color=theme.rgba(theme.COLORS['text_secondary']), size_hint_y=None, height=23)
        if subtitle:
            self.add_widget(self._subtitle_label)
        self.bind(_display_value=self._update_number)
        self._display_value = value

    def set_value(self, value, total=None):
        self._total = total
        self._target_value = value
        Animation.cancel_all(self, '_display_value')
        self._update_number()
        Animation(_display_value=value, duration=.18, t='out_quad').start(self)

    def set_subtitle(self, text):
        self._subtitle_label.set_text(text)

    def _update_number(self, *_):
        text = theme.fa_number(f'{int(round(self._display_value)):,}')
        if self._total is not None:
            text += f' [size=14][color=8c9eab]/ {theme.fa_number(self._total)}[/color][/size]'
        self._value_label.text = text
