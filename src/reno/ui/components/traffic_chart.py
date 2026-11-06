"""Non-interactive Matplotlib/Agg chart, rendered at twice the panel resolution."""
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
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import FuncFormatter, MaxNLocator

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


class TrafficChart(FloatLayout):
    """Keep the existing data/filter interface; no pyplot window or mouse tools."""

    def __init__(self, period='weekly', **kwargs):
        super().__init__(**kwargs)
        self.period = period
        self.data = []
        self.metric = 'entry'
        font_path = Path(__file__).resolve().parents[2] / 'assets/fonts/Vazirmatn-Regular.ttf'
        self._font = FontProperties(fname=str(font_path))
        self._figure = Figure(dpi=192, facecolor='none')
        self._agg = FigureCanvasAgg(self._figure)
        self._image = Image(fit_mode='fill', pos_hint={'x': 0, 'y': 0})
        self.add_widget(self._image)
        self._render_key = None
        # Coalesce resize events; moving the panel never requires a new render.
        self._render_trigger = Clock.create_trigger(self._draw, .12)
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
            return
        self._figure.clear()
        # Logical pixels at 96 DPI, rasterized at 192 DPI for clean downsampling.
        self._figure.set_size_inches(width / 96, height / 96, forward=False)
        hourly = self.period == 'hourly'
        left, right, top = (44, 26, 26) if hourly else (38, 20, 36)
        axes = self._figure.add_axes((left / width, 32 / height,
                                     max(.1, 1 - (left + right) / width),
                                     max(.1, 1 - (top + 32) / height)))
        axes.set_facecolor('none')
        for spine in axes.spines.values():
            spine.set_visible(False)
        axes.set_axisbelow(True)
        axes.grid(axis='y', color=(theme.DASHBOARD_COLORS['border'] if hourly else theme.COLORS['border']),
                  linewidth=.6 if hourly else .55, alpha=.75)
        axes.tick_params(axis='both', length=0, pad=7, colors=theme.COLORS['text_secondary'])
        axes.set_xlim(-.15, 23.15 if self.period == 'hourly' else 6.15)
        # Matplotlib 3.11+ shapes and orders Persian through HarfBuzz/Raqm.
        # Kivy's pre-reversed theme.rtl() would reverse these labels twice.
        if self.period == 'hourly':
            ticks = [0, 3, 6, 9, 12, 15, 18, 21, 23]
            axes.set_xticks(ticks, [theme.fa_number(f'{hour:02}:00') for hour in ticks])
        else:
            axes.set_xticks(range(7), WEEKDAYS)
        axes.yaxis.set_major_locator(MaxNLocator(nbins=4, integer=True, min_n_ticks=3))
        axes.yaxis.set_major_formatter(FuncFormatter(lambda value, _: theme.fa_number(f'{value:,.0f}')))
        columns = (1, 2) if self.metric == 'both' else (2,) if self.metric == 'exit' else (1,)
        peak = max([0] + [row[column] for row in self.data for column in columns])
        if hourly:
            locator = MaxNLocator(nbins=4, integer=True, steps=[1, 2, 2.5, 3, 4, 5, 6, 8, 10])
            ticks = locator.tick_values(0, max(4, peak * 1.03))
            axes.set_ylim(0, ticks[-1])
            axes.set_yticks(ticks)
        else:
            axes.set_ylim(0, max(4, peak * 1.15))
        x_values = [self._x_value(row[0]) for row in self.data]
        for column in columns:
            entry = column == 1
            values = [row[column] for row in self.data]
            color = (theme.DASHBOARD_COLORS['cyan' if entry else 'amber'] if self.period == 'hourly'
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
                      marker=None if self.period == 'hourly' else 'o', markersize=3.3, markeredgewidth=0,
                      markevery=[index for index,value in enumerate(curve_x) if value in x_values],
                      solid_capstyle='round', antialiased=True, clip_on=False)
        font_size = 8.2 if width >= 340 else 7.2
        for label in axes.get_xticklabels() + axes.get_yticklabels():
            label.set_fontproperties(self._font)
            label.set_fontsize(font_size)
        legend_font = self._font.copy()
        legend_font.set_size(8.5)
        if self.data and not hourly:
            axes.legend(loc='lower left', bbox_to_anchor=(0, 1.03), ncol=len(columns),
                        frameon=False, prop=legend_font, labelcolor='linecolor',
                        handlelength=2, handletextpad=.6, columnspacing=1.6, borderaxespad=0)
        elif not self.data:
            axes.text(.5, .5, 'داده‌ای برای نمایش موجود نیست',
                      transform=axes.transAxes, ha='center', va='center',
                      fontproperties=legend_font, color=theme.COLORS['text_secondary'])
        self._agg.draw()
        size = self._agg.get_width_height()
        texture = self._image.texture
        if texture is None or texture.size != size:
            texture = Texture.create(size=size, colorfmt='rgba')
            texture.flip_vertical()
            texture.mag_filter = texture.min_filter = 'linear'
        texture.blit_buffer(bytes(self._agg.buffer_rgba()), colorfmt='rgba', bufferfmt='ubyte')
        self._image.texture = texture
        self._render_key = key
