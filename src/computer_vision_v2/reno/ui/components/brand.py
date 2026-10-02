"""One reference logo and wordmark for the sidebar, login and application."""
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.ui.components.icons import APP_ICON


class BrandMark(Image):
    def __init__(self, **kwargs):
        kwargs.setdefault('source', APP_ICON)
        kwargs.setdefault('size_hint', (None, None))
        kwargs.setdefault('size', (35, 35))
        kwargs.setdefault('fit_mode', 'contain')
        super().__init__(**kwargs)


class Brand(BoxLayout):
    def __init__(self, **kwargs):
        kwargs.setdefault('size_hint_y', None)
        kwargs.setdefault('height', 50)
        kwargs.setdefault('spacing', 10)
        super().__init__(**kwargs)
        self.add_widget(BrandMark(pos_hint={'center_y': .5}))
        words = BoxLayout(orientation='vertical', size_hint_y=None, height=38,
                          pos_hint={'center_y': .5}, spacing=3)
        for text, size, color in [('PLAKINO', 18, 'text_primary'),
                                   (theme.rtl('کنترل تردد'), 10, 'text_secondary')]:
            label = Label(text=text, font_size=size, font_name=theme.APP_FONT_NAME,
                          color=theme.rgba(theme.COLORS[color]), halign='left', valign='middle')
            label.bind(size=lambda w, *_: setattr(w, 'text_size', w.size))
            words.add_widget(label)
        self.add_widget(words)
