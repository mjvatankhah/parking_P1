"""An empty reports page with the application's shared navigation and branding."""
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from reno.ui.components.page_shell import PageShell


class PlaceholderScreen(Screen):
    def __init__(self, page_key, title, on_navigate=None, **kwargs):
        super().__init__(**kwargs)
        self._shell = PageShell(title, page_key, BoxLayout(), on_navigate,
                                subtitle='گزارش‌های تردد')
        self.add_widget(self._shell)
