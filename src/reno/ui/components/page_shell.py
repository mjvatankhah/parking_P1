"""Reference page geometry shared by every signed-in destination."""
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from reno.ui.components.ambient_background import AmbientBackground
from reno.ui.components.common import Card
from reno.ui.components.sidebar import Sidebar
from reno.ui.components.app_header import AppHeader, WindowControls
from reno.ui import theme


class PageShell(FloatLayout):
    def __init__(self, title, active, content, on_navigate, subtitle=None, **kwargs):
        super().__init__(**kwargs)
        self.background = AmbientBackground()
        self.add_widget(self.background)
        self.frame = Card(size_hint=(None, None), padding=0, radius=8, hover_effect=False,
                          bg_color=theme.rgba(theme.COLORS['background']), border_color=theme.rgba(theme.COLORS['border']))
        self.sidebar = Sidebar(active=active, on_navigate=on_navigate)
        self.main = BoxLayout(orientation='vertical', padding=[30, 26, 30, 20], spacing=20)
        self.header = AppHeader(title, **({'subtitle': subtitle} if subtitle is not None else {}))
        self.main.add_widget(self.header)
        self.main.add_widget(content)
        self.frame.add_widget(self.main)
        self.frame.add_widget(self.sidebar)
        self.add_widget(self.frame)
        controls = WindowControls(pos_hint={'right': 1, 'top': 1})
        controls.height = 32
        for button in controls.children:
            button.size = (32, 26)
        self.add_widget(controls)
        self.bind(pos=self._layout_frame, size=self._layout_frame)
        self._layout_frame()

    def _layout_frame(self, *_):
        margin = 20 if self.width >= 1200 else 16
        width = min(1380, max(0, self.width-2*margin))
        self.frame.size = (width, max(0, self.height-68))
        self.frame.pos = (self.x+(self.width-width)/2, self.y+24)
        compact = self.width < 1100
        self.sidebar.width = 165 if compact else 188
        self.sidebar.padding = [10 if compact else 16, 22, 10 if compact else 16, 22]
        self.main.padding = [18 if compact else 24, 24, 18 if compact else 24, 18]
