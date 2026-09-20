"""
ui/components/recent_records.py

The recent plate-records table at the bottom of the Dashboard.
Column order follows the Balsamiq wireframe: camera, plate number,
time, date, direction (event), plate photo.

Data comes from services/plate_service.py; this file only knows how
to lay records out, not where they came from - and it does NOT
generate fake rows to avoid ever looking empty. If plate_service has
no records (real production state until a backend is connected), this
shows a proper empty state instead.
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.image import Image
from pathlib import Path
from kivy.graphics import Color, RoundedRectangle

from typing import List
from computer_vision_v2.reno.models.plate_record import PlateRecord
from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.ui.theme import COLORS, FONT_SIZE, SPACING
from computer_vision_v2.reno.ui.components.common import Card, Divider, RTLLabel, EmptyState

_COLUMNS = [
    ("دوربین", 0.13),
    ("نوع", 0.12),
    ("شماره پلاک", 0.18),
    ("ساعت", 0.12),
    ("تاریخ", 0.15),
    ("رخداد", 0.14),
    ("عکس پلاک", 0.16),
]


class RecentRecordsPanel(Card):
    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("padding", [SPACING["md"], SPACING["md"], SPACING["md"], SPACING["md"]])
        kwargs.setdefault("spacing", SPACING["sm"])
        super().__init__(**kwargs)

        self._title = RTLLabel(text="رکوردهای اخیر", font_size=FONT_SIZE["subtitle"],
                                bold=True, size_hint_y=None, height=24)
        self._subtitle = RTLLabel(text="", font_size=FONT_SIZE["caption"],
                                   color=theme.rgba(COLORS["text_secondary"]),
                                   size_hint_y=None, height=18)
        title_box = BoxLayout(orientation="vertical", size_hint_y=None, height=44, spacing=2)
        title_box.add_widget(self._title)
        title_box.add_widget(self._subtitle)
        self.add_widget(title_box)

        self._table_holder = BoxLayout(orientation="vertical")
        self.add_widget(self._table_holder)
        self.set_records([])

    def set_records(self, records: List[PlateRecord]):
        self._table_holder.clear_widgets()

        if not records:
            self._subtitle.set_text("")
            self._table_holder.add_widget(EmptyState(
                icon_name="reports",
                title="هنوز گزارشی ثبت نشده است",
                subtitle="با اتصال دوربین‌ها، رکوردهای شناسایی پلاک اینجا نمایش داده می‌شود",
            ))
            return

        self._subtitle.set_text(f"{len(records)} رکورد ثبت‌شده")
        self._table_holder.add_widget(self._build_header_row())
        self._table_holder.add_widget(Divider())

        scroll = ScrollView(size_hint=(1, 1))
        rows = GridLayout(cols=1, size_hint_y=None, spacing=1)
        rows.bind(minimum_height=rows.setter("height"))
        for index, record in enumerate(records):
            rows.add_widget(self._build_data_row(record, index))
        scroll.add_widget(rows)
        self._table_holder.add_widget(scroll)

    def _build_header_row(self):
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=32)
        for label, width_ratio in _COLUMNS:
            cell = RTLLabel(
                text=label,
                font_size=FONT_SIZE["caption"],
                bold=True,
                color=theme.rgba(COLORS["text_secondary"]),
                size_hint_x=width_ratio,
                halign="center",
            )
            row.add_widget(cell)
        return row

    def set_error(self):
        self._subtitle.set_text("دریافت رکوردها ناموفق بود؛ تلاش مجدد خودکار انجام می‌شود")

    def clear_error(self, count):
        self._subtitle.set_text(f"{count} رکورد ثبت‌شده" if count else "")

    def _build_data_row(self, record: PlateRecord, index: int):
        bg = COLORS["background"] if index % 2 == 0 else COLORS["surface"]
        row = _RowBackground(bg_color=theme.rgba(bg), orientation="horizontal",
                              size_hint_y=None, height=40)

        values = [record.camera, record.class_label(), record.plate, record.time, record.date,
                  record.direction_label(), "🖼" if record.image_path else "—"]
        for column, ((_, width_ratio), value) in enumerate(zip(_COLUMNS, values)):
            if column == 6 and record.image_path and Path(record.image_path).is_file():
                row.add_widget(Image(source=record.image_path, size_hint_x=width_ratio))
                continue
            if column == 6:
                value = "—"
            cell = RTLLabel(
                text=value,
                font_size=FONT_SIZE["caption"],
                size_hint_x=width_ratio,
                halign="center",
            )
            row.add_widget(cell)
        return row


class _RowBackground(BoxLayout):
    def __init__(self, bg_color, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            self._color = Color(*bg_color)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[6])
        self.bind(pos=self._redraw, size=self._redraw)

    def _redraw(self, *args):
        self._rect.pos = self.pos
        self._rect.size = self.size
