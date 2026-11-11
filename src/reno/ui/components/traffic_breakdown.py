"""Today's event status distribution, with a readable zero-data state."""
import numpy as np

from kivy.animation import Animation
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
from reno.ui.components.background_raster import BackgroundRaster
from reno.ui import theme
from reno.ui.components.common import Card, Divider, RTLLabel

PALETTE = theme.DASHBOARD_COLORS
STATUSES = (
    ('allowed', 'مجاز', '#168447'),
    ('guest', 'میهمان', '#E5B72F'),
    ('blocked', 'لیست سیاه', '#B94E3C'),
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


def render_ring(counts):
    """CPU-only snapshot, serialized with the other Matplotlib charts."""
    figure = Figure(figsize=(200 / 96, 200 / 96), dpi=192, facecolor='none')
    renderer = FigureCanvasAgg(figure)
    axes = figure.add_axes((0, 0, 1, 1), aspect='equal')
    axes.set(xlim=(-1.08, 1.08), ylim=(-1.08, 1.08))
    axes.set_axis_off()
    total = sum(counts)
    axes.add_patch(Wedge((0, 0), 1, 0, 360, width=.23,
                         facecolor=PALETTE['inset'], linewidth=0))
    axes.add_patch(Wedge((0, 0), .68, 0, 360, width=.008,
                         facecolor=PALETTE['border'], linewidth=0))
    start = 90
    for count, (_, _, color) in zip(counts, STATUSES):
        if not count or not total:
            continue
        sweep = 360 * count / total
        gap = min(3.2, sweep * .18) if count < total else 0
        # One clipped gradient avoids seams between concentric raster bands.
        coordinates = np.linspace(-1.08, 1.08, 512)
        x, y = np.meshgrid(coordinates, coordinates)
        shade = np.clip(.82 + .18 * (np.hypot(x, y) - .77) / .23, .82, 1)
        rgba = np.ones((512, 512, 4))
        rgba[:, :, :3] = shade[:, :, None] * np.array(theme.rgba(color)[:3])
        arc = Wedge((0, 0), 1, start + gap / 2, start + sweep - gap / 2,
                    width=.23, transform=axes.transData)
        gradient = axes.imshow(rgba, extent=(-1.08, 1.08, -1.08, 1.08),
                               origin='lower', interpolation='bilinear', zorder=2)
        gradient.set_clip_path(arc)
        start += sweep
    renderer.draw()
    return renderer.get_width_height(), bytes(renderer.buffer_rgba())


class StatusRing(FloatLayout):
    """Shaded status arcs with a centered text overlay and data-change animation."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.counts = (0, 0, 0)
        self._render_key = None
        self._image = Image(size_hint=(None, None), size=(200, 200),
                            pos_hint={'center_x': .5, 'center_y': .5})
        self.add_widget(self._image)
        self.center_text = BoxLayout(orientation='vertical', size_hint=(None, None),
                                     size=(132, 54),
                                     pos_hint={'center_x': .5, 'center_y': .5})
        self.total_label = RTLLabel(text='۰', font_size=24, bold=True, halign='center',
                                   padding=[0, 0], size_hint_y=None, height=32)
        self.center_text.add_widget(self.total_label)
        self.center_text.add_widget(RTLLabel(
            text='مجموع سه وضعیت', font_size=12, halign='center', padding=[0, 0],
            color=theme.rgba(PALETTE['muted']), size_hint_y=None, height=22))
        self.add_widget(self.center_text)
        self._raster = BackgroundRaster(render_ring, self._apply_raster)
        self._draw()

    def set_data(self, counts):
        if tuple(counts) == self.counts:
            return
        self.counts = tuple(counts)
        self.total_label.set_text(theme.fa_number(f'{sum(counts):,}'))
        self._draw()

    def _draw(self):
        if self.counts == self._render_key:
            return
        self._raster.request(self.counts)

    def _apply_raster(self, counts, result):
        if counts != self.counts:
            return
        size, pixels = result
        texture = Texture.create(size=size, colorfmt='rgba')
        texture.flip_vertical()
        texture.mag_filter = texture.min_filter = 'linear'
        texture.blit_buffer(pixels, colorfmt='rgba', bufferfmt='ubyte')
        self._image.texture = texture
        self._render_key = counts
        # Identical polling updates do not restart the animation or render textures.
        Animation.cancel_all(self._image)
        self._image.opacity = .35
        self._image.size = (188, 188)
        Animation(opacity=1, size=(200, 200), duration=.45,
                  t='out_cubic').start(self._image)


class TrafficBreakdown(Card):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', padding=0, spacing=0, radius=14,
                         hover_effect=False, bg_color=theme.rgba(PALETTE['surface']),
                         border_color=theme.rgba(PALETTE['border']), **kwargs)
        self.add_widget(RTLLabel(text='تفکیک وضعیت خودروها', font_size=13, bold=True,
                                size_hint_y=None, height=36, padding=[16, 0]))
        self.add_widget(Divider(line_color=theme.rgba(PALETTE['border'])))
        body = BoxLayout(orientation='vertical', padding=[17, 12, 17, 16], spacing=12)
        self.ring = StatusRing()
        body.add_widget(self.ring)
        legend_host = FloatLayout(size_hint_y=None, height=66)
        self.legend = GridLayout(cols=3, size_hint=(None, None), height=66,
                                 spacing=18, pos_hint={'center_x': .5, 'center_y': .5})
        def fit_legend(host, _):
            self.legend.width = min(540, max(0, host.width - 24))
        legend_host.bind(size=fit_legend)
        fit_legend(legend_host, legend_host.size)
        self.values = {}
        for key, title, color in reversed(STATUSES):
            row = Card(orientation='vertical', padding=[12, 8, 12, 8], spacing=2,
                       radius=12, hover_effect=False,
                       bg_color=theme.rgba(PALETTE['inset']),
                       border_color=(*theme.rgba(color)[:3], .28))
            heading = BoxLayout(size_hint=(None, None), size=(100, 22), spacing=6,
                                pos_hint={'center_x': .5})
            heading.add_widget(RTLLabel(text=title, font_size=14, halign='center',
                                       padding=[0, 0]))
            heading.add_widget(StatusDot(color, pos_hint={'center_y': .5}))
            row.add_widget(heading)
            value = RTLLabel(text='۰', font_size=20, bold=True, halign='center',
                             padding=[0, 0], size_hint_y=None, height=26)
            self.values[key] = value
            row.add_widget(value)
            self.legend.add_widget(row)
        legend_host.add_widget(self.legend)
        body.add_widget(legend_host)
        self.add_widget(body)

    def set_data(self, counts):
        """Adapt service counts (allowed, guest, unclassified, blocked) for display.

        Unclassified events are not a vehicle role and must not be relabelled as
        permitted or blocked. Both the ring and its total use only known statuses.
        """
        allowed, guest, _unclassified, blocked = counts
        visible_counts = (allowed, guest, blocked)
        self.ring.set_data(visible_counts)
        for count, (key, _, _) in zip(visible_counts, STATUSES):
            self.values[key].set_text(theme.fa_number(f'{count:,}'))
