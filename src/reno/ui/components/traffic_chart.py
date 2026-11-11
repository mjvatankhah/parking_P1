"""Agg charts with a horizontally scrollable hourly viewport."""
import numpy as np
from matplotlib.colors import to_rgba
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch
from datetime import date
from pathlib import Path

from kivy.clock import Clock
from kivy.graphics.texture import Texture
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FuncFormatter, MaxNLocator

from reno.ui.components.background_raster import BackgroundRaster, render_locked
from reno.ui import theme
from reno.ui.components.jalali_calendar import WEEKDAYS


def smooth_series(x_values, values, samples=32):
    """Shape-preserving cubic Hermite curve through the actual measurements.

    Flat tangents at peaks/valleys avoid sharp corners; monotone slope limits
    prevent invented extrema, overshoot and negative traffic counts.
    """
    x,y=np.asarray(x_values,dtype=float),np.asarray(values,dtype=float)
    if len(x)<3 or np.any(np.diff(x)<=0):
        return x,y
    h=np.diff(x)
    delta=np.diff(y)/h
    slopes=np.zeros(len(x))
    for i in range(1,len(x)-1):
        if delta[i-1]*delta[i]>0:
            a,b=2*h[i]+h[i-1],h[i]+2*h[i-1]
            slopes[i]=(a+b)/(a/delta[i-1]+b/delta[i])
    def endpoint(h0,h1,d0,d1):
        slope=((2*h0+h1)*d0-h0*d1)/(h0+h1)
        if slope*d0<=0:
            return 0.
        return min(abs(slope),3*abs(d0))*np.sign(d0)
    slopes[0]=endpoint(h[0],h[1],delta[0],delta[1])
    slopes[-1]=endpoint(h[-1],h[-2],delta[-1],delta[-2])
    xx,yy=[],[]
    for i,width in enumerate(h):
        t=np.linspace(0,1,samples,endpoint=False)
        xx.extend(x[i]+t*width)
        yy.extend((2*t**3-3*t**2+1)*y[i]+(t**3-2*t**2+t)*width*slopes[i]
                  +(-2*t**3+3*t**2)*y[i+1]+(t**3-t**2)*width*slopes[i+1])
    return np.append(xx,x[-1]),np.append(yy,y[-1])


def render_chart(key):
    """Render an immutable snapshot; no Kivy widgets or textures in this worker."""
    width, height, period, metric, data = key
    font_path = Path(__file__).resolve().parents[2] / 'assets/fonts/Vazirmatn-Regular.ttf'
    font = FontProperties(fname=str(font_path))
    figure = Figure(dpi=192, facecolor='none')
    agg = FigureCanvasAgg(figure)
    # Logical pixels at 96 DPI, rasterized at 192 DPI for clean downsampling.
    hourly = period == 'hourly'
    left, right, top = (44, 26, 26) if hourly else (38, 20, 36)
    bottom = 48 if hourly else 32
    # Rasterize the full day once at the same pixels-per-hour as the viewport.
    plot_width = width - left - right
    raster_width = width + plot_width if hourly else width
    figure.set_size_inches(raster_width / 96, height / 96, forward=False)
    axes = figure.add_axes((left / raster_width, bottom / height,
                                 max(.1, (raster_width - left - right) / raster_width),
                                 max(.1, 1 - (top + bottom) / height)))
    axes.set_facecolor('none')
    for spine in axes.spines.values():
        spine.set_visible(False)
    axes.set_axisbelow(True)
    axes.grid(axis='y', color=(theme.DASHBOARD_COLORS['border'] if hourly else theme.COLORS['border']),
              linewidth=.6 if hourly else .55, alpha=.75)
    axes.tick_params(axis='both', length=0, pad=7, colors=theme.COLORS['text_secondary'])
    # Matplotlib 3.11+ shapes and orders Persian through HarfBuzz/Raqm.
    # Kivy's pre-reversed theme.rtl() would reverse these labels twice.
    if period == 'hourly':
        ticks = list(range(24))
        axes.set_xticks(ticks, [theme.fa_number(f'{hour:02}:00') for hour in ticks])
    else:
        axes.set_xticks(range(7), WEEKDAYS)
    # Set after ticks, which otherwise expand Matplotlib's view limits.
    axes.set_xlim((-.5, 23.5) if hourly else (-.15, 6.15))
    axes.yaxis.set_major_locator(MaxNLocator(nbins=4, integer=True, min_n_ticks=3))
    axes.yaxis.set_major_formatter(FuncFormatter(lambda value, _: theme.fa_number(f'{value:,.0f}')))
    columns = (1, 2) if metric == 'both' else (2,) if metric == 'exit' else (1,)
    peak = max([0] + [row[column] for row in data for column in columns])
    if hourly:
        locator = MaxNLocator(nbins=4, integer=True, steps=[1, 2, 2.5, 3, 4, 5, 6, 8, 10])
        ticks = locator.tick_values(0, max(4, peak * 1.03))
        axes.set_ylim(0, ticks[-1])
        axes.set_yticks(ticks)
    else:
        axes.set_ylim(0, max(4, peak * 1.15))
    x_values = [(int(row[0]) if hourly else (date.fromisoformat(row[0]).weekday()+2) % 7) for row in data]
    for column in columns:
        entry = column == 1
        values = [row[column] for row in data]
        color = (theme.DASHBOARD_COLORS['cyan' if entry else 'exit'] if period == 'hourly'
                 else theme.COLORS['entry' if entry else 'exit'])
        curve_x, curve_y = smooth_series(x_values, values)
        if len(values)>1 and any(values):
            vertices = [(x_values[0],0),*zip(curve_x,curve_y),(x_values[-1],0),(x_values[0],0)]
            clip=PathPatch(MplPath(vertices),facecolor='none',edgecolor='none')
            axes.add_patch(clip)
            gradient=np.zeros((256,1,4))
            gradient[:,:,:3]=to_rgba(color)[:3]
            gradient[:,:,3]=np.linspace(0,.18 if hourly else .24,256)[:,None]
            fill=axes.imshow(gradient,extent=(min(x_values),max(x_values),0,max(values)),
                             origin='lower',aspect='auto',zorder=1,interpolation='bilinear')
            fill.set_clip_path(clip)
        axes.plot(curve_x, curve_y,
                  label='ورود' if entry else 'خروج',
                  color=color,
                  linewidth=1.5, linestyle='-',
                  marker=None if period == 'hourly' else 'o', markersize=3.3, markeredgewidth=0,
                  markevery=[index for index,value in enumerate(curve_x) if value in x_values],
                  solid_capstyle='round', antialiased=True, clip_on=hourly)
    font_size = 8.2 if width >= 340 else 7.2
    for label in axes.get_xticklabels() + axes.get_yticklabels():
        label.set_fontproperties(font)
        label.set_fontsize(font_size)
    legend_font = font.copy()
    legend_font.set_size(8.5)
    if data and not hourly:
        axes.legend(loc='lower left', bbox_to_anchor=(0, 1.03), ncol=len(columns),
                    frameon=False, prop=legend_font, labelcolor='linecolor',
                    handlelength=2, handletextpad=.6, columnspacing=1.6, borderaxespad=0)
    elif not data:
        axes.text(.5, .5, 'داده‌ای برای نمایش موجود نیست',
                  transform=axes.transAxes, ha='center', va='center',
                  fontproperties=legend_font, color=theme.COLORS['text_secondary'])
    agg.draw()
    size = agg.get_width_height()
    return figure, agg, bytes(agg.buffer_rgba()), size


class TrafficChart(FloatLayout):
    """Keep the existing data/filter interface; no pyplot window or mouse tools."""

    def __init__(self, period='weekly', **kwargs):
        super().__init__(**kwargs)
        self.period = period
        self.data = []
        self.metric = 'entry'
        self._figure = Figure(dpi=192, facecolor='none')
        self._agg = FigureCanvasAgg(self._figure)
        self._image = Image(fit_mode='fill', pos_hint={'x': 0, 'y': 0})
        self.add_widget(self._image)
        self._render_key = None
        # Coalesce resize events; moving the panel never requires a new render.
        self._raster = BackgroundRaster(render_chart, self._apply_raster)
        self._render_trigger = Clock.create_trigger(self._request_render, .12)
        if period == 'hourly':
            self._image.size_hint = (None, None)
            self._image.pos_hint = {}
            self._left_margin = Image(size_hint=(None, None), fit_mode='fill')
            self._right_margin = Image(size_hint=(None, None), fit_mode='fill')
            self.add_widget(self._left_margin)
            self.add_widget(self._right_margin)
            self.bind(pos=self._position_hourly_images, size=self._position_hourly_images)
            self._position_hourly_images()
            # Keep the vertical scale fixed while panning the 24-hour timeline.
            # Twelve visible hourly buckets: initially 07:00 through 18:00.
            self.hour_scroll = ScrollView(
                pos_hint={'x': 0, 'y': 0},
                do_scroll_x=True, do_scroll_y=False, scroll_x=7 / 12,
                bar_width=12, bar_margin=3, scroll_type=['bars', 'content'],
                bar_color=theme.rgba(theme.DASHBOARD_COLORS['muted']),
                bar_inactive_color=(*theme.rgba(theme.DASHBOARD_COLORS['muted'])[:3], .65))
            timeline = Widget(size_hint_x=None)
            self.hour_scroll.add_widget(timeline)
            self.hour_scroll.bind(width=lambda view, width: setattr(timeline, 'width', 2 * width),
                                  scroll_x=self._pan_hourly)
            timeline.width = 2 * self.hour_scroll.width
            self.add_widget(self.hour_scroll)
        self.bind(size=self._render_trigger)
        self._render_trigger()

    def set_metric(self, metric):
        if metric not in ('entry', 'exit', 'both'):
            raise ValueError(f'Unsupported chart metric: {metric}')
        self.metric = metric
        self._render_trigger()

    def set_data(self, data):
        self.data = sorted(data, key=lambda row: self._x_value(row[0]))
        self._render_trigger()

    def _x_value(self, value):
        return int(value) if self.period == 'hourly' else (date.fromisoformat(value).weekday()+2) % 7

    def _draw(self, *_):
        width, height = round(self.width), round(self.height)
        if width < 120 or height < 100:
            return
        key = (width, height, self.period, self.metric, tuple(tuple(row) for row in self.data))
        if key == self._render_key:
            if self.period == 'hourly':
                self._pan_hourly()
            return
        self._apply_raster(key, render_locked(render_chart, key))

    def _snapshot(self):
        return (round(self.width), round(self.height), self.period, self.metric,
                tuple(tuple(row) for row in self.data))

    def _request_render(self, *_):
        key = self._snapshot()
        if key[0] >= 120 and key[1] >= 100 and key != self._render_key:
            self._raster.request(key)

    def _apply_raster(self, key, result):
        if key != self._snapshot():
            return
        self._figure, self._agg, pixels, size = result
        width, height, period, metric, data = key
        hourly = period == 'hourly'
        left, right = 44, 26
        plot_width = width - left - right
        if hourly:
            self._hour_texture = Texture.create(size=size, colorfmt='rgba')
            self._hour_texture.flip_vertical()
            self._hour_texture.mag_filter = self._hour_texture.min_filter = 'linear'
            self._hour_texture.blit_buffer(pixels,
                                           colorfmt='rgba', bufferfmt='ubyte')
            self._left_margin.texture = self._hour_texture.get_region(0, 0, left * 2, size[1])
            self._right_margin.texture = self._hour_texture.get_region(
                size[0] - right * 2, 0, right * 2, size[1])
            self._hour_crop = (left * 2, plot_width * 2, width * 2)
            self._render_key = key
            self._pan_hourly()
            return
        texture = self._image.texture
        if texture is None or texture.size != size:
            texture = Texture.create(size=size, colorfmt='rgba')
            texture.flip_vertical()
            texture.mag_filter = texture.min_filter = 'linear'
        texture.blit_buffer(pixels, colorfmt='rgba', bufferfmt='ubyte')
        self._image.texture = texture
        self._render_key = key

    def _pan_hourly(self, *_):
        """Move a cached raster; never run Matplotlib on the pointer input path.

        Keep the vertical labels and both margins stationary while cropping the
        full-width timeline. Data, metric and size changes rebuild the cache.
        """
        if not hasattr(self, '_hour_texture'):
            return
        scroll = min(1, max(0, self.hour_scroll.scroll_x))
        left, plot, width = self._hour_crop
        offset = round(plot * scroll)
        self._image.texture = self._hour_texture.get_region(
            left + offset, 0, plot, self._hour_texture.height)
        self._figure.axes[0].set_xlim(-.5 + 12 * scroll, 11.5 + 12 * scroll)

    def _position_hourly_images(self, *_):
        self._left_margin.pos = self.pos
        self._left_margin.size = (44, self.height)
        self._image.pos = (self.x + 44, self.y)
        self._image.size = (max(1, self.width - 70), self.height)
        self._right_margin.pos = (self.right - 26, self.y)
        self._right_margin.size = (26, self.height)
