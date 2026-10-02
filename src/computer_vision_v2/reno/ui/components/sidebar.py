"""Reference-width sidebar with inline icons, four destinations and logout."""
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget
from kivy.uix.behaviors import ButtonBehavior
from kivy.graphics import Color, RoundedRectangle, Line
from kivy.properties import StringProperty, BooleanProperty, ObjectProperty, ListProperty
from kivy.animation import Animation
from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.ui.components.icons import Icon
from computer_vision_v2.reno.ui.components.brand import Brand
from computer_vision_v2.reno.ui.components.common import RTLLabel, HoverBehavior, make_gradient_texture

_ITEMS = [
    ('dashboard', 'dashboard', 'داشبورد'),
    ('cameras', 'camera', 'مانیتورینگ'),
    ('reports', 'reports', 'گزارش‌ها'),
    ('camera_settings', 'settings', 'تنظیمات'),
]


class _SidebarItem(HoverBehavior, ButtonBehavior, BoxLayout):
    active = BooleanProperty(False)
    key = StringProperty('')
    _bg_rgba = ListProperty([0, 0, 0, 0])

    def __init__(self, icon_name, label_text, **kwargs):
        super().__init__(orientation='horizontal', size_hint_y=None, height=43,
                         padding=[10, 0, 8, 0], spacing=11, **kwargs)
        with self.canvas.before:
            self._bg_color = Color(0, 0, 0, 0)
            self._bg = RoundedRectangle(radius=[7])
            self._border_color = Color(0, 0, 0, 0)
            self._border = Line(width=.65)
            self._active_color = Color(0, 0, 0, 0)
            self._active_line = Line(width=1)
        self._icon = Icon(name=icon_name, color=theme.rgba('#A4B4C0'),
                          size_hint=(None, None), size=(20, 20), pos_hint={'center_y': .5})
        self._label = RTLLabel(text=label_text, font_size=12, halign='left', padding=[0, 0],
                               color=theme.rgba('#A4B4C0'))
        self.add_widget(self._icon)
        self.add_widget(self._label)
        self.bind(pos=self._redraw, size=self._redraw, active=self._style,
                  hovered=self._style, state=self._style, _bg_rgba=self._sync_color)
        self._style()
        self._redraw()

    def _redraw(self, *_):
        self._bg.pos, self._bg.size = self.pos, self.size
        self._border.rounded_rectangle = (*self.pos, *self.size, 7)
        self._active_line.points = [self.x+1, self.y+9, self.x+1, self.top-9]

    def _sync_color(self, _, color):
        self._bg_color.rgba = color

    def _style(self, *_):
        target = theme.rgba('#004A6B', .4 if self.active else (.22 if self.hovered else 0))
        Animation.cancel_all(self, '_bg_rgba')
        Animation(_bg_rgba=target, duration=theme.ANIM_FAST, t='out_quad').start(self)
        self._icon.color = theme.rgba(theme.COLORS['primary'] if self.active or self.hovered else '#A4B4C0')
        self._label.color = theme.rgba('#F2FCFF' if self.active or self.hovered else '#A4B4C0')
        self._border_color.rgba = theme.rgba('#136382', .4 if self.active else 0)
        self._active_color.rgba = theme.rgba(theme.COLORS['primary'], 1 if self.active else 0)


class Sidebar(BoxLayout):
    active = StringProperty('dashboard')
    on_navigate = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        # Kivy interprets on_* constructor keywords as event bindings.
        # Assign this callback explicitly so menu clicks reach the app.
        on_navigate = kwargs.pop('on_navigate', None)
        super().__init__(orientation='vertical', size_hint_x=None, width=theme.SIDEBAR_WIDTH,
                         padding=[16, 22, 16, 22], spacing=7, **kwargs)
        self.on_navigate = on_navigate
        self._items = {}
        with self.canvas.before:
            Color(1, 1, 1, .88)
            self._surface = RoundedRectangle(texture=make_gradient_texture('#0C1A24', '#080E13'), radius=[0])
            Color(*theme.rgba('#1A2C36'))
            self._edge = Line(width=.65)
        self.bind(pos=self._redraw, size=self._redraw, active=self._set_active)
        self.add_widget(Brand())
        self.add_widget(Widget(size_hint_y=None, height=12))
        for key, icon, label in _ITEMS:
            item = _SidebarItem(icon, label, key=key, active=key == self.active)
            item.bind(on_release=lambda _, destination=key: self._navigate(destination))
            self._items[key] = item
            self.add_widget(item)
        self.add_widget(Widget())
        self.add_widget(RTLLabel(text='مرکز کنترل تردد', font_size=12, size_hint_y=None, height=24))
        self.add_widget(RTLLabel(text='VISION IN CONTROL', font_size=8,
                                color=theme.rgba(theme.COLORS['text_secondary']), size_hint_y=None, height=18))
        self.add_widget(Widget(size_hint_y=None, height=12))
        logout = _SidebarItem('logout', 'خروج', key='logout')
        logout.bind(on_release=lambda *_: self._navigate('logout'))
        self._items['logout'] = logout
        self.add_widget(logout)
        self._redraw()

    def _redraw(self, *_):
        self._surface.pos, self._surface.size = self.pos, self.size
        self._edge.points = [self.x+self.width, self.y, self.x+self.width, self.y+self.height]

    def _navigate(self, key):
        if self.on_navigate:
            self.on_navigate(key)

    def _set_active(self, *_):
        for key, item in self._items.items():
            item.active = key == self.active

    def set_active(self, key):
        self.active = key
