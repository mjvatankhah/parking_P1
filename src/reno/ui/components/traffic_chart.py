"""Non-interactive Matplotlib/Agg chart, rendered at twice the panel resolution."""
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


class TrafficChart(FloatLayout):
    """Keep the existing data/filter interface; no pyplot window or mouse tools."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
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
        self.data = sorted(data, key=lambda row: (date.fromisoformat(row[0]).weekday()+2) % 7)
        self._render_trigger()

    def _draw(self, *_):
        width, height = round(self.width), round(self.height)
        if width < 120 or height < 100:
            return
        key = (width, height, self.metric, tuple(tuple(row) for row in self.data))
        if key == self._render_key:
            return
        self._figure.clear()
        # Logical pixels at 96 DPI, rasterized at 192 DPI for clean downsampling.
        self._figure.set_size_inches(width / 96, height / 96, forward=False)
        axes = self._figure.add_axes((38 / width, 32 / height,
                                     max(.1, 1 - 58 / width), max(.1, 1 - 68 / height)))
        axes.set_facecolor('none')
        for spine in axes.spines.values():
            spine.set_visible(False)
        axes.set_axisbelow(True)
        axes.grid(axis='y', color=theme.COLORS['border'], linewidth=.55, alpha=.75)
        axes.tick_params(axis='both', length=0, pad=7, colors=theme.COLORS['text_secondary'])
        axes.set_xlim(-.15, 6.15)
        # Matplotlib 3.11+ shapes and orders Persian through HarfBuzz/Raqm.
        # Kivy's pre-reversed theme.rtl() would reverse these labels twice.
        axes.set_xticks(range(7), WEEKDAYS)
        axes.yaxis.set_major_locator(MaxNLocator(nbins=4, integer=True, min_n_ticks=3))
        axes.yaxis.set_major_formatter(FuncFormatter(lambda value, _: theme.fa_number(f'{value:,.0f}')))
        columns = (1, 2) if self.metric == 'both' else (2,) if self.metric == 'exit' else (1,)
        peak = max([0] + [row[column] for row in self.data for column in columns])
        axes.set_ylim(0, max(4, peak * 1.15))
        x_values = [(date.fromisoformat(row[0]).weekday()+2) % 7 for row in self.data]
        for column in columns:
            entry = column == 1
            axes.plot(x_values, [row[column] for row in self.data],
                      label='ورود' if entry else 'خروج',
                      color=theme.COLORS['entry' if entry else 'exit'],
                      linewidth=1.5, linestyle='-' if entry else (0, (4, 2.5)),
                      marker='o', markersize=3.3, markeredgewidth=0,
                      solid_capstyle='round', antialiased=True, clip_on=False)
        font_size = 8.2 if width >= 340 else 7.2
        for label in axes.get_xticklabels() + axes.get_yticklabels():
            label.set_fontproperties(self._font)
            label.set_fontsize(font_size)
        legend_font = self._font.copy()
        legend_font.set_size(8.5)
        if self.data:
            axes.legend(loc='lower left', bbox_to_anchor=(0, 1.03), ncol=len(columns),
                        frameon=False, prop=legend_font, labelcolor='linecolor',
                        handlelength=2, handletextpad=.6, columnspacing=1.6, borderaxespad=0)
        else:
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
