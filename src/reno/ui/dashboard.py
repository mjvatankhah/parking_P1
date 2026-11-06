"""Reference-inspired Kivy dashboard backed by the RENO services."""

import logging
import threading
from datetime import date
from functools import partial
from dataclasses import astuple
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen
from kivy.uix.popup import Popup
from reno.ui import theme
from reno.ui.components.common import Card, Divider, RTLLabel, EmptyState, SecondaryButton, styled_spinner
from reno.ui.components.plate_input import PlateSearchInput
from reno.ui.components.page_shell import PageShell
from reno.ui.components.stat_card import StatCard
from reno.ui.components.traffic_chart import TrafficChart
from reno.ui.components.traffic_record import TrafficRecordRow, detection_header
from reno.ui.components.jalali_date_picker import JalaliDatePicker
from reno.ui.components.traffic_breakdown import TrafficBreakdown, StatusDot
from reno.ui.components.camera_selector import build_camera_selector, ALL_CAMERAS_VALUE
from reno.services.camera_service import camera_service
from reno.services.dashboard_service import dashboard_service
from reno.services.plate_service import plate_service
from reno.services.mock_mode import MOCK_DATA_ENABLED


class DashboardScreen(Screen):
    def __init__(self, on_navigate=None, **kwargs):
        super().__init__(**kwargs)
        self.on_navigate = on_navigate
        self._active = False
        self._loading = False
        self._timer = None
        self._camera = ''
        self._day = None  # None follows today across midnight; a selected date stays fixed.
        self._revision = 0
        self._record_scroll = None
        self._record_rows = None
        self._record_keys = []
        self._refresh_trigger = Clock.create_trigger(self._request_refresh, .3)
        self._build()
        camera_service.subscribe(self._on_cameras_changed)
        camera_service.subscribe_status(self._on_status_changed)

    def _build(self):
        palette = theme.DASHBOARD_COLORS
        self._content = content = BoxLayout(orientation='vertical', spacing=24,
                                           size_hint_y=None, padding=[2, 2, 6, 4])
        content.bind(minimum_height=content.setter('height'))
        self._stats_grid = stats = GridLayout(cols=4, size_hint_y=None, height=118, spacing=13)
        self._today = StatCard('کل تردد امروز', 0, icon_name='car',
                              gradient=(palette['cyan'], '#246A83'))
        self._inside = StatCard('خودروهای داخل محوطه', 0, icon_name='maximize',
                               gradient=(palette['green'], '#246B52'))
        self._guests = StatCard('میهمانان امروز', 0, icon_name='guard_add',
                               gradient=(palette['amber'], '#8B6127'))
        self._blocked = StatCard('خودروهای غیرمجاز امروز', 0, icon_name='shield',
                                gradient=(palette['red'], '#8A384A'))
        for card in (self._blocked, self._guests, self._inside, self._today):
            stats.add_widget(card)
        content.add_widget(stats)

        panel_style = dict(orientation='vertical', padding=0, spacing=0, radius=14,
                           hover_effect=False, bg_color=theme.rgba(palette['surface']),
                           border_color=theme.rgba(palette['border']), size_hint_y=None)
        self._chart_panel = chart_panel = Card(height=356, **panel_style)
        chart_heading = BoxLayout(size_hint_y=None, height=46, padding=[16, 0, 16, 0], spacing=7)
        legend = BoxLayout(size_hint_x=None, width=92, spacing=16)
        for title, color in (('خروج', palette['amber']), ('ورود', palette['cyan'])):
            item = BoxLayout(spacing=6)
            item.add_widget(RTLLabel(text=title, font_size=11, padding=[0, 0],
                                     color=theme.rgba(palette['muted'])))
            item.add_widget(StatusDot(color, pos_hint={'center_y': .5}))
            legend.add_widget(item)
        chart_heading.add_widget(legend)
        chart_heading.add_widget(RTLLabel(text='نمودار تردد ساعتی', font_size=13, bold=True, padding=[0, 0]))
        chart_panel.add_widget(chart_heading)
        chart_panel.add_widget(Divider(line_color=theme.rgba(palette['border'])))
        self._chart = TrafficChart(period='hourly')
        self._chart.set_metric('both')
        chart_panel.add_widget(self._chart)
        controls = BoxLayout(size_hint_y=None, height=36, spacing=10, padding=[18, 0, 18, 0])
        self._metric_selector = styled_spinner(initial=theme.rtl('هر دو'),
            values=[theme.rtl(v) for v in ('ورود', 'خروج', 'هر دو')])
        self._metric_selector.size_hint_x = .25
        self._metric_selector.font_size = 12
        self._metric_selector.bind(text=lambda _, text: self._chart.set_metric(
            {theme.rtl('ورود'): 'entry', theme.rtl('خروج'): 'exit', theme.rtl('هر دو'): 'both'}[text]))
        controls.add_widget(self._metric_selector)
        self._camera_selector = build_camera_selector(self._select_camera)
        self._camera_selector.size_hint_x = .45
        self._camera_selector.font_size = 12
        controls.add_widget(self._camera_selector)
        self._date_picker = JalaliDatePicker(font_size=12, size_hint_x=.3)
        self._date_picker.text = theme.rtl('امروز')
        self._date_picker.bind(text=lambda *_: self._select_day(self._date_picker.selected))
        controls.add_widget(self._date_picker)
        filter_content = Card(orientation='vertical', padding=18, spacing=10, hover_effect=False,
                              bg_color=theme.rgba(palette['surface']), border_color=theme.rgba(palette['border']))
        filter_content.add_widget(RTLLabel(text='فیلتر نمودار و جست‌وجوی آخرین ترددها', font_size=14,
                                           size_hint_y=None, height=28))
        filter_content.add_widget(controls)
        self._chart_status = RTLLabel(text='در حال دریافت اطلاعات…', font_size=11,
                                      color=theme.rgba(palette['muted']),
                                      size_hint_y=None, height=32, padding=[18, 0])
        filter_content.add_widget(self._chart_status)
        content.add_widget(chart_panel)

        self._breakdown = TrafficBreakdown(size_hint_y=None, height=350)
        content.add_widget(self._breakdown)

        self._record_panel = record_panel = Card(height=420, **panel_style)
        heading = BoxLayout(size_hint_y=None, height=46, spacing=10, padding=[18, 0, 18, 0])
        self._view_all = SecondaryButton(text=theme.rtl('‹  مشاهده همه'), size_hint_x=None, width=105,
            font_size=12, bg_color_normal=(0, 0, 0, 0), border_color=(0, 0, 0, 0),
            color=theme.rgba(palette['cyan']))
        self._view_all.bind(on_release=lambda *_: self._navigate('reports'))
        heading.add_widget(self._view_all)
        self._record_status = RTLLabel(text='در حال دریافت…', font_size=11,
            color=theme.rgba(palette['muted']), halign='left', padding=[0, 0])
        heading.add_widget(self._record_status)
        heading.add_widget(RTLLabel(text='آخرین ترددها', font_size=14, bold=True, padding=[0, 0]))
        record_panel.add_widget(heading)
        record_panel.add_widget(Divider(line_color=theme.rgba(palette['border'])))
        toolbar = BoxLayout(size_hint_y=None, height=60, spacing=10, padding=[18, 10, 18, 10])
        reset = SecondaryButton(text=theme.rtl('بازنشانی'), size_hint_x=None, width=80,
                                 font_size=11, bg_color_normal=(0, 0, 0, 0), border_color=(0, 0, 0, 0),
                                 color=theme.rgba(palette['cyan']))
        reset.bind(on_release=self._reset_filters)
        toolbar.add_widget(reset)
        self._search = PlateSearchInput(hint_text=theme.rtl('جست‌وجوی شماره پلاک…'),
                                        halign='left', multiline=False, font_size=12)
        self._search.bind(text=self._filters_changed)
        toolbar.add_widget(self._search)
        filter_content.add_widget(toolbar)
        self._record_holder = BoxLayout(orientation='vertical', padding=[10, 0, 10, 0])
        self._record_holder.add_widget(EmptyState(icon_name='log', title='در حال دریافت رویدادها',
                                                  subtitle='اطلاعات تردد در این بخش نمایش داده می‌شود'))
        record_panel.add_widget(self._record_holder)
        record_panel.add_widget(RTLLabel(text='جزئیات هر تردد با کلیک روی ردیف', font_size=11,
            color=theme.rgba(palette['muted']), size_hint_y=None, height=30, padding=[18, 0]))
        content.add_widget(record_panel)
        footer = BoxLayout(size_hint_y=None, height=20)
        footer.add_widget(RTLLabel(text='PLAKINO', font_size=11, halign='left',
                                   color=theme.rgba(palette['muted']), padding=[0, 0]))
        self._data_status = RTLLabel(text='رویدادهای ثبت‌شدهٔ سامانه', font_size=11,
                                     color=theme.rgba(palette['muted']), padding=[0, 0])
        footer.add_widget(self._data_status)
        content.add_widget(footer)
        self._dashboard_scroll = ScrollView(do_scroll_x=False, bar_width=4, scroll_type=['bars', 'content'])
        self._dashboard_scroll.add_widget(content)
        self._shell = PageShell('داشبورد کنترل تردد', 'dashboard', self._dashboard_scroll, self._navigate)
        self._shell.frame.bg_color = theme.rgba(palette['background'])
        self._filters_popup = Popup(title='', separator_height=0, content=filter_content,
                                    size_hint=(.8, None), height=294, background='',
                                    background_color=(0, 0, 0, 0))
        close_filters = SecondaryButton(text=theme.rtl('بستن'), size_hint_y=None, height=36, font_size=12)
        close_filters.bind(on_release=lambda *_: self._filters_popup.dismiss())
        filter_content.add_widget(close_filters)
        self._filter_button = SecondaryButton(text=theme.rtl('جست‌وجو و فیلتر'), font_size=12,
                                              size_hint=(None, None), size=(136, 36), pos_hint={'center_y': .5})
        self._filter_button.bind(on_release=lambda *_: self._filters_popup.open())
        self._shell.header.add_widget(self._filter_button, index=len(self._shell.header.children)-1)
        self.add_widget(self._shell)

    def _reset_filters(self, *_):
        self._search.text = ''
        self._camera_selector.text = theme.rtl('همه دوربین‌ها')
        self._date_picker.selected = None
        self._date_picker.text = theme.rtl('امروز')
        self._select_day(None)
        self._metric_selector.text = theme.rtl('هر دو')

    def _navigate(self, key):
        if self.on_navigate:
            self.on_navigate(key)

    def on_pre_enter(self, *_):
        self._active = True
        self._request_refresh()
        if self._timer is None:
            self._timer = Clock.schedule_interval(self._request_refresh, 5)

    def on_leave(self, *_):
        self._active = False
        if hasattr(self, '_filters_popup'):
            self._filters_popup.dismiss()
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _on_cameras_changed(self, cameras):
        self._filters_changed()

    def _on_status_changed(self, cameras):
        self._request_refresh()

    def _select_camera(self, value):
        self._camera = '' if value == ALL_CAMERAS_VALUE else value
        self._filters_changed()

    def _select_day(self, value):
        self._day = value
        self._filters_changed()

    def _filters_changed(self, *_):
        self._revision += 1
        self._refresh_trigger()

    def _request_refresh(self, *_):
        if not self._active or self._loading:
            return
        self._loading = True
        threading.Thread(target=self._load, args=(self._revision, self._camera, self._day, self._search.text.strip()),
                         daemon=True, name='reno-dashboard-data').start()

    def _load(self, revision, camera, day, plate):
        day = day or date.today()
        logger = logging.getLogger(__name__)
        stats = records = flow = None
        errors = []
        # Recent events are independent of the chart's date and camera controls.
        # A failed aggregate must never hide a successful event query.
        try:
            records = plate_service.get_recent_records(limit=50, plate=plate)
        except Exception:
            logger.exception('Dashboard recent events read failed')
            errors.append('records')
        try:
            stats = dashboard_service.get_statistics()
        except Exception:
            logger.exception('Dashboard statistics read failed')
            errors.append('statistics')
        try:
            flow = dashboard_service.get_hourly_flow(day=day, camera=camera, plate=plate)
        except Exception:
            logger.exception('Dashboard hourly flow read failed')
            errors.append('flow')
        Clock.schedule_once(partial(self._apply, revision, stats, records, flow, errors=tuple(errors)), 0)

    def _apply(self, revision, stats, records, flow, _dt, errors=()):
        self._loading = False
        if not self._active:
            return
        if revision != self._revision:
            self._request_refresh()
            return
        if stats is not None:
            self._today.set_value(stats.today_total)
            self._inside.set_value(stats.inside_vehicles)
            self._guests.set_value(stats.guest_vehicles)
            self._blocked.set_value(stats.blocked_vehicles)
            self._breakdown.set_data(stats.access_counts)
        if flow is not None:
            self._chart.set_data(flow)
            self._chart_status.set_text('ترددی در این بازه ثبت نشده است' if not any(a or b for _, a, b in flow)
                                        else 'ورود و خروج به تفکیک ساعت')
        elif 'flow' in errors:
            self._chart_status.set_text('دریافت نمودار ناموفق بود؛ تلاش مجدد خودکار')
        if records is not None:
            self._record_status.set_text(f'{theme.fa_number(len(records))} تردد')
            self._set_records(records)
        else:
            self._record_status.set_text('خطای دریافت ترددها')
            if self._record_scroll is None:
                self._record_holder.clear_widgets()
                self._record_holder.add_widget(EmptyState(icon_name='log', title='دریافت رویدادها ناموفق بود',
                                                          subtitle='تلاش مجدد به‌صورت خودکار انجام می‌شود'))
        if errors or stats is None or records is None or flow is None:
            self._data_status.set_text('دریافت بخشی از اطلاعات ناموفق بود؛ تلاش مجدد خودکار')
        else:
            self._data_status.set_text('حالت نمایشی · داده‌های آزمایشی' if MOCK_DATA_ENABLED
                                       else 'رویدادهای ثبت‌شدهٔ سامانه')

    def _set_records(self, records):
        keys = [astuple(record) for record in records]
        if keys == self._record_keys and self._record_scroll is not None:
            return
        if not records:
            self._record_holder.clear_widgets()
            self._record_scroll = self._record_rows = None
            self._record_keys = []
            search = getattr(self, '_search', None)
            filtered = bool(search and search.text.strip())
            self._record_holder.add_widget(EmptyState(
                icon_name='reports', title='ترددی با این پلاک پیدا نشد' if filtered else 'هنوز ترددی ثبت نشده است',
                subtitle='عبارت جست‌وجو را تغییر دهید یا فیلتر را بازنشانی کنید' if filtered
                         else 'رویدادهای ثبت‌شده اینجا نمایش داده می‌شوند'))
            return
        if self._record_scroll is None:
            self._record_holder.clear_widgets()
            self._record_scroll = scroll = ScrollView(do_scroll_x=True, scroll_x=1, bar_width=4)
            self._record_rows = rows = GridLayout(cols=1, size_hint=(None,None), spacing=3)
            scroll.bind(width=lambda _, width: setattr(rows, 'width', max(640,width)))
            rows.width = max(640,scroll.width)
            rows.bind(minimum_height=rows.setter('height'))
            scroll.add_widget(rows)
            self._record_holder.add_widget(scroll)

        scroll, rows = self._record_scroll, self._record_rows
        at_top = scroll.scroll_y >= .999
        offset = (1 - scroll.scroll_y) * max(0, rows.height - scroll.height)
        old_widgets = list(reversed(rows.children))
        old_data_rows = old_widgets[1:]
        # Anchor to the first surviving row at/after the visible top. Each
        # data row occupies 56 pixels plus 3 pixels of spacing after the header.
        first_visible = max(0, int((offset - 29) // 59))
        if not at_top:
            for index in range(first_visible, len(self._record_keys)):
                key = self._record_keys[index]
                if key in keys:
                    offset += (keys.index(key) - index) * 59
                    break

        available = {}
        for key, row in zip(self._record_keys, old_data_rows):
            available.setdefault(key, []).append(row)
        new_rows = []
        for key, record in zip(keys, records):
            matches = available.get(key)
            if matches:
                row = matches.pop(0)
                row.record = record
            else:
                row = TrafficRecordRow(record)
            new_rows.append(row)
        rows.clear_widgets()
        rows.add_widget(old_widgets[0] if old_widgets else detection_header())
        for row in new_rows:
            rows.add_widget(row)
        self._record_keys = keys
        # Resolve height before restoring the scroll so a later layout does
        # not apply an obsolete normalized position to the updated content.
        rows.height = 26 + len(records) * 59
        rows.do_layout()
        extent = max(0, rows.height - scroll.height)
        scroll.scroll_y = 1 if at_top or not extent else 1 - min(extent, max(0, offset)) / extent
