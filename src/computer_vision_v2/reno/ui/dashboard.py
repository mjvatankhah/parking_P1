"""Reference-inspired Kivy dashboard backed by the RENO services."""

import logging
import threading
from datetime import date
from functools import partial
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen
from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.ui.theme import COLORS
from computer_vision_v2.reno.ui.components.common import Card, RTLLabel, EmptyState, RoundedTextInput, SecondaryButton, styled_spinner
from computer_vision_v2.reno.ui.components.page_shell import PageShell
from computer_vision_v2.reno.ui.components.icons import Icon
from computer_vision_v2.reno.ui.components.stat_card import StatCard, GRADIENT_TEAL, GRADIENT_BLUE, GRADIENT_ORANGE, GRADIENT_CYAN
from computer_vision_v2.reno.ui.components.traffic_chart import TrafficChart
from computer_vision_v2.reno.ui.components.traffic_record import TrafficRecordRow, detection_header
from computer_vision_v2.reno.ui.components.week_picker import WeekPicker
from computer_vision_v2.reno.ui.components.jalali_calendar import week_bounds
from computer_vision_v2.reno.ui.components.camera_selector import build_camera_selector, ALL_CAMERAS_VALUE
from computer_vision_v2.reno.models.camera import STATUS_ONLINE
from computer_vision_v2.reno.services.camera_service import camera_service
from computer_vision_v2.reno.services.dashboard_service import dashboard_service
from computer_vision_v2.reno.services.plate_service import plate_service
from computer_vision_v2.reno.services.mock_mode import MOCK_DATA_ENABLED


class DashboardScreen(Screen):
    def __init__(self, on_navigate=None, **kwargs):
        super().__init__(**kwargs)
        self.on_navigate = on_navigate
        self._active = False
        self._loading = False
        self._timer = None
        self._camera = ''
        self._day = week_bounds(date.today())[1]
        self._revision = 0
        self._refresh_trigger = Clock.create_trigger(self._request_refresh, .3)
        self._build()
        camera_service.subscribe(self._on_cameras_changed)
        camera_service.subscribe_status(self._on_status_changed)

    def _build(self):
        content = BoxLayout(orientation='vertical', spacing=16)
        stats = BoxLayout(size_hint_y=None, height=112, spacing=13)
        self._today = StatCard('تردد امروز', 0, subtitle='مجموع ورود و خروج',
                               icon_name='car', gradient=GRADIENT_TEAL)
        self._unique = StatCard('خودروهای یکتا', 0, subtitle='بر اساس پلاک شناسایی‌شده',
                                icon_name='shield', gradient=GRADIENT_BLUE)
        self._online = StatCard('دوربین‌های فعال', 0, subtitle='در حال بررسی وضعیت دوربین‌ها',
                                icon_name='camera', gradient=GRADIENT_CYAN, value_color=COLORS['primary'])
        self._alerts = StatCard('هشدارها', 0, subtitle='پلاک ناخوانا و دوربین قطع',
                                icon_name='bell', gradient=GRADIENT_ORANGE, value_color=COLORS['warning'])
        for card in (self._today, self._unique, self._online, self._alerts):
            stats.add_widget(card)
        content.add_widget(stats)

        panels = BoxLayout(spacing=18)
        chart_panel = Card(orientation='vertical', padding=[17, 13, 17, 14], spacing=10, size_hint_x=.42)
        heading = BoxLayout(size_hint_y=None, height=28, spacing=8)
        heading.add_widget(RTLLabel(text='شنبه تا جمعه', font_size=11,
                                    color=theme.rgba(COLORS['text_secondary']), halign='left', padding=[0, 0]))
        heading.add_widget(RTLLabel(text='تردد هفتگی', font_size=14, padding=[0, 0]))
        heading.add_widget(Icon(name='reports', size_hint=(None, None), size=(16, 16),
                                pos_hint={'center_y': .5}, color=theme.rgba(COLORS['primary'])))
        chart_panel.add_widget(heading)
        self._chart = TrafficChart()
        chart_panel.add_widget(self._chart)
        self._chart_status = RTLLabel(text='در حال دریافت اطلاعات…', font_size=11,
                                      color=theme.rgba(COLORS['text_secondary']),
                                      size_hint_y=None, height=26, padding=[0, 0])
        chart_panel.add_widget(self._chart_status)
        controls = BoxLayout(orientation='vertical', size_hint_y=None, height=76, spacing=6)
        self._date_picker = WeekPicker(self._select_day, font_size=11, size_hint_y=None, height=34)
        controls.add_widget(self._date_picker)
        selectors = BoxLayout(spacing=6)
        self._metric_selector = styled_spinner(initial=theme.rtl('ورود'),
            values=[theme.rtl(v) for v in ('ورود','خروج','هر دو')])
        self._metric_selector.size_hint=(.35,1)
        self._metric_selector.font_size=12
        self._metric_selector.bind(text=lambda _, text: self._chart.set_metric(
            {theme.rtl('ورود'):'entry',theme.rtl('خروج'):'exit',theme.rtl('هر دو'):'both'}[text]))
        selectors.add_widget(self._metric_selector)
        self._camera_selector = build_camera_selector(self._select_camera)
        self._camera_selector.size_hint=(.65,1)
        self._camera_selector.font_size=12
        selectors.add_widget(self._camera_selector)
        controls.add_widget(selectors)
        chart_panel.add_widget(controls)
        panels.add_widget(chart_panel)

        self._record_panel = record_panel = Card(size_hint_x=.58, orientation='vertical',
            padding=[10, 13, 10, 14], spacing=8)
        heading = BoxLayout(size_hint_y=None, height=28, spacing=8, padding=[7, 0, 7, 0])
        self._record_status = RTLLabel(text='در حال دریافت…', font_size=11,
            color=theme.rgba(COLORS['text_secondary']), halign='left', padding=[0, 0], size_hint_x=None, width=110)
        heading.add_widget(self._record_status)
        heading.add_widget(RTLLabel(text='آخرین شناسایی‌ها', font_size=14, padding=[0, 0]))
        heading.add_widget(Icon(name='log', size_hint=(None, None), size=(16, 16),
                                pos_hint={'center_y': .5}, color=theme.rgba(COLORS['primary'])))
        record_panel.add_widget(heading)
        self._record_holder = BoxLayout(orientation='vertical')
        self._record_holder.add_widget(EmptyState(icon_name='log', title='در حال دریافت رویدادها',
                                                  subtitle='اطلاعات تردد در این بخش نمایش داده می‌شود'))
        record_panel.add_widget(self._record_holder)
        record_panel.add_widget(RTLLabel(text='جزئیات هر تردد با کلیک روی ردیف', font_size=11,
            color=theme.rgba(COLORS['text_secondary']), size_hint_y=None, height=23))
        panels.add_widget(record_panel)
        content.add_widget(panels)

        toolbar = BoxLayout(size_hint_y=None, height=41, spacing=10)
        reset = SecondaryButton(text=theme.rtl('بازنشانی'), size_hint_x=None, width=60,
                                 font_size=10, bg_color_normal=(0, 0, 0, 0), border_color=(0, 0, 0, 0),
                                 color=theme.rgba(COLORS['primary']))
        reset.bind(on_release=self._reset_filters)
        toolbar.add_widget(reset)
        self._search = RoundedTextInput(hint_text=theme.rtl('جست‌وجوی شماره پلاک…'),
                                        halign='right', multiline=False, font_size=11)
        self._search.bind(text=self._filters_changed)
        toolbar.add_widget(self._search)
        content.add_widget(toolbar)
        footer = BoxLayout(size_hint_y=None, height=20)
        footer.add_widget(RTLLabel(text='PLAKINO', font_size=11, halign='left',
                                   color=theme.rgba(COLORS['text_secondary']), padding=[0, 0]))
        self._data_status = RTLLabel(text='رویدادهای ثبت‌شدهٔ سامانه', font_size=11,
                                     color=theme.rgba(COLORS['text_secondary']), padding=[0, 0])
        footer.add_widget(self._data_status)
        content.add_widget(footer)
        self._shell = PageShell('داشبورد کنترل تردد', 'dashboard', content, self._navigate)
        self.add_widget(self._shell)
        self._set_camera_counts(camera_service.get_cameras())

    def _reset_filters(self, *_):
        self._search.text = ''
        self._camera_selector.text = theme.rtl('همه دوربین‌ها')
        self._date_picker.set_date(None)
        self._metric_selector.text = theme.rtl('ورود')

    def _set_camera_counts(self, cameras):
        online = sum(camera.status == STATUS_ONLINE for camera in cameras)
        total = len(cameras)
        self._online.set_value(online, total=total)
        self._online.set_subtitle(f'{theme.fa_number(total-online)} دوربین قطع' if total else 'دوربینی ثبت نشده است')

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
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _on_cameras_changed(self, cameras):
        self._set_camera_counts(cameras)
        self._filters_changed()

    def _on_status_changed(self, cameras):
        self._set_camera_counts(cameras)
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
        try:
            stats = dashboard_service.get_statistics()
            records = plate_service.get_recent_records(limit=20, plate=plate)
            flow = dashboard_service.get_daily_flow(end=day, camera=camera, plate=plate)
        except Exception:
            logging.getLogger(__name__).exception('Dashboard database read failed')
            Clock.schedule_once(partial(self._apply, revision, None, None, None), 0)
        else:
            Clock.schedule_once(partial(self._apply, revision, stats, records, flow), 0)

    def _apply(self, revision, stats, records, flow, _dt):
        self._loading = False
        if not self._active:
            return
        if revision != self._revision:
            self._request_refresh()
            return
        if stats is None:
            self._chart.set_data([])
            self._chart_status.set_text('دریافت داده ناموفق بود؛ تلاش مجدد خودکار')
            self._record_status.set_text('خطای دریافت')
            self._record_holder.clear_widgets()
            self._record_holder.add_widget(EmptyState(icon_name='log', title='دریافت رویدادها ناموفق بود',
                                                      subtitle='تلاش مجدد به‌صورت خودکار انجام می‌شود'))
            self._data_status.set_text('دریافت داده ناموفق بود؛ تلاش مجدد خودکار')
            return
        self._today.set_value(stats.today_total)
        self._unique.set_value(stats.unique_vehicles)
        self._online.set_value(stats.online_cameras, total=stats.total_cameras)
        offline = max(0, stats.total_cameras-stats.online_cameras)
        unread = max(0, stats.alerts-offline)
        self._online.set_subtitle(f'{theme.fa_number(offline)} دوربین قطع' if stats.total_cameras else 'دوربینی ثبت نشده است')
        self._alerts.set_subtitle(f'{theme.fa_number(unread)} پلاک ناخوانا · {theme.fa_number(offline)} دوربین قطع')
        self._alerts.set_value(stats.alerts)
        self._chart.set_data(flow)
        self._chart_status.set_text('ترددی در این بازه ثبت نشده است' if not any(a or b for _, a, b in flow) else 'بازهٔ هفتگی · تعداد رویدادهای ثبت‌شده')
        self._record_status.set_text(f'{theme.fa_number(len(records))} تردد')
        self._data_status.set_text('حالت نمایشی · داده‌های آزمایشی' if MOCK_DATA_ENABLED else 'رویدادهای ثبت‌شدهٔ سامانه')
        self._record_holder.clear_widgets()
        if not records:
            self._record_holder.add_widget(EmptyState(
                icon_name='reports', title='هنوز ترددی ثبت نشده است',
                subtitle='رویدادهای ثبت‌شده اینجا نمایش داده می‌شوند'))
            return
        scroll = ScrollView(do_scroll_x=True, scroll_x=1, bar_width=4)
        rows = GridLayout(cols=1, size_hint=(None,None), spacing=3)
        scroll.bind(width=lambda _, width: setattr(rows, 'width', max(480,width)))
        rows.width = max(480,scroll.width)
        rows.add_widget(detection_header())
        rows.bind(minimum_height=rows.setter('height'))
        for record in records:
            rows.add_widget(TrafficRecordRow(record))
        scroll.add_widget(rows)
        self._record_holder.add_widget(scroll)
