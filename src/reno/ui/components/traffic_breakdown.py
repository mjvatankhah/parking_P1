"""Today's event status distribution, with a readable zero-data state."""
from kivy.graphics import Color, Ellipse
from kivy.graphics.texture import Texture
from kivy.uix.image import Image
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import Wedge
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.widget import Widget
from reno.ui import theme
from reno.ui.components.common import Card, Divider, RTLLabel

PALETTE = theme.DASHBOARD_COLORS
STATUSES = (
    ('allowed', 'مجاز', PALETTE['green']),
    ('guest', 'میهمان', PALETTE['cyan']),
    ('unknown', 'ناشناس', PALETTE['amber']),
    ('blocked', 'لیست سیاه', PALETTE['red']),
)


class StatusDot(Widget):
    def __init__(self, color, **kwargs):
        super().__init__(size_hint=(None, None), size=(8, 8), **kwargs)
        with self.canvas:
            Color(*theme.rgba(color))
            self._dot = Ellipse(pos=self.pos, size=self.size)
        self.bind(pos=self._update, size=self._update)

    def _update(self, *_):
        self._dot.pos, self._dot.size = self.pos, self.size


class StatusRing(FloatLayout):
    """160px ring, 22px stroke, starting at three o'clock counterclockwise."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.counts = (0, 0, 0, 0)
        self._render_key = None
        self._image = Image(size_hint=(None, None), size=(160, 160),
                            pos_hint={'center_x': .5, 'center_y': .5})
        self.add_widget(self._image)
        self.total_label = RTLLabel(text='۰', font_size=20, bold=True, halign='center',
                                   size_hint=(1, None), height=28, pos_hint={'center_y': .55})
        self.add_widget(self.total_label)
        self.add_widget(RTLLabel(text='کل تردد', font_size=12, halign='center',
                                color=theme.rgba(PALETTE['muted']),
                                size_hint=(1, None), height=22, pos_hint={'center_y': .43}))
        self._draw()

    def set_data(self, counts):
        self.counts = tuple(counts)
        self.total_label.set_text(theme.fa_number(f'{sum(counts):,}'))
        self._draw()

    def _draw(self):
        if self.counts == self._render_key:
            return
        figure = Figure(figsize=(160 / 96, 160 / 96), dpi=192, facecolor='none')
        renderer = FigureCanvasAgg(figure)
        axes = figure.add_axes((0, 0, 1, 1), aspect='equal')
        axes.set(xlim=(-1, 1), ylim=(-1, 1))
        axes.set_axis_off()
        total = sum(self.counts)
        if not total:
            axes.add_patch(Wedge((0, 0), 1, 0, 360, width=22 / 80,
                                 facecolor=PALETTE['border'], linewidth=0))
        start = 0
        for count, (_, _, color) in zip(self.counts, STATUSES):
            if not count or not total:
                continue
            sweep = 360 * count / total
            gap = min(1.7, sweep * .15) if count < total else 0
            axes.add_patch(Wedge((0, 0), 1, start + gap / 2, start + sweep - gap / 2,
                                 width=22 / 80, facecolor=color, linewidth=0, antialiased=True))
            start += sweep
        renderer.draw()
        texture = Texture.create(size=renderer.get_width_height(), colorfmt='rgba')
        texture.flip_vertical()
        texture.mag_filter = texture.min_filter = 'linear'
        texture.blit_buffer(bytes(renderer.buffer_rgba()), colorfmt='rgba', bufferfmt='ubyte')
        self._image.texture = texture
        self._render_key = self.counts


class TrafficBreakdown(Card):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', padding=0, spacing=0, radius=14,
                         hover_effect=False, bg_color=theme.rgba(PALETTE['surface']),
                         border_color=theme.rgba(PALETTE['border']), **kwargs)
        self.add_widget(RTLLabel(text='تفکیک وضعیت خودروها', font_size=13, bold=True,
                                size_hint_y=None, height=36, padding=[16, 0]))
        self.add_widget(Divider(line_color=theme.rgba(PALETTE['border'])))
        body = BoxLayout(orientation='vertical', padding=[17, 25, 17, 16], spacing=24)
        self.ring = StatusRing()
        body.add_widget(self.ring)
        legend = GridLayout(cols=2, size_hint_y=None, height=72, spacing=8)
        self.values = {}
        for index in (1, 0, 3, 2):
            key, title, color = STATUSES[index]
            row = Card(padding=[12, 0, 12, 0], spacing=8, radius=13, hover_effect=False,
                       bg_color=theme.rgba(PALETTE['inset']), border_color=(0, 0, 0, 0))
            value = RTLLabel(text='۰', font_size=12, bold=True, halign='left', padding=[0, 0])
            self.values[key] = value
            row.add_widget(value)
            row.add_widget(RTLLabel(text=title, font_size=12, padding=[0, 0]))
            row.add_widget(StatusDot(color, pos_hint={'center_y': .5}))
            legend.add_widget(row)
        body.add_widget(legend)
        self.add_widget(body)

    def set_data(self, counts):
        """Counts in allowed, guest, unknown, blocked order; all are event counts."""
        self.ring.set_data(counts)
        for count, (key, _, _) in zip(counts, STATUSES):
            self.values[key].set_text(theme.fa_number(f'{count:,}'))
