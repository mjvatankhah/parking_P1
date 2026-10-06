"""
ui/camera_settings.py

The Camera Settings screen: a form to add/edit a camera (ID, source
type, source, function) plus a table of already-configured cameras
with Edit/Delete actions, and Save/Cancel for the form itself.

Every change goes through services/camera_service.py. Because the
Dashboard's camera selector and camera grid are subscribed to that
same service, adding/editing/deleting a camera here is immediately
reflected on the Dashboard - no code on this screen needs to know
that the Dashboard exists.
"""

import base64
import os
import subprocess
import sys

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.behaviors import ButtonBehavior
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.animation import Animation
from kivy.properties import ListProperty
from kivy.clock import Clock

from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.ui.components.page_shell import PageShell
from computer_vision_v2.reno.ui.theme import COLORS, FONT_SIZE, SPACING, rtl, rtl_map, PAGE_BG_TOP, PAGE_BG_BOTTOM
from computer_vision_v2.reno.ui.components.common import (
    Card, make_gradient_texture, PrimaryButton, SecondaryButton, RoundedTextInput, Divider,
    StatusDot, RTLLabel, EmptyState, Badge, show_toast, styled_spinner, HoverBehavior,
)
from computer_vision_v2.reno.ui.components.sidebar import Sidebar
from computer_vision_v2.reno.ui.components.app_header import AppHeader
from computer_vision_v2.reno.ui.components.icons import Icon

from computer_vision_v2.reno.models.camera import (
    Camera, SOURCE_TYPE_RTSP, SOURCE_TYPE_VIDEO_FILE, SOURCE_TYPE_LABELS,
    ROLE_ENTRY, ROLE_EXIT, ROLE_ENTRY_AND_EXIT, ROLE_LABELS, STATUS_ONLINE, STATUS_OFFLINE,
)
from computer_vision_v2.reno.services.camera_service import camera_service

# Reshaped-for-display option lists + reverse lookup back to the real
# (unreshaped) model key. Built once, at import time, from the single
# source of truth in models/camera.py - see theme.rtl_map()'s
# docstring for why this exists (it's the fix for a real RTL bug found
# during the audit: dropdown text wasn't being reshaped/reordered).
_SOURCE_TYPE_VALUES, _SOURCE_TYPE_BY_DISPLAY = rtl_map(SOURCE_TYPE_LABELS)
_ROLE_VALUES, _ROLE_BY_DISPLAY = rtl_map(ROLE_LABELS)

_DEFAULT_LINE = (0.2, 0.6, 0.8, 0.6)
_DEFAULT_INSIDE_POINT = (0.5, 0.3)


class CameraSettingsScreen(Screen):
    """`on_navigate` is set by main.py."""

    def __init__(self, on_navigate=None, **kwargs):
        super().__init__(**kwargs)
        self.on_navigate = on_navigate
        self._editing_camera_id = None  # None => "add" mode
        self._build()
        camera_service.subscribe(self._on_cameras_changed)
        camera_service.subscribe_status(self._on_camera_status_changed)

    # ------------------------------------------------------------------
    def _build(self):
        content = BoxLayout(
            orientation="vertical",
            padding=0, size_hint_y=None,
            spacing=SPACING["md"],
        )
        content.add_widget(self._build_form_card())
        table = self._build_table_card()
        table.size_hint_y = None
        table.height = 260
        content.add_widget(table)
        content.bind(minimum_height=content.setter('height'))
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(content)
        self._shell = PageShell('تنظیمات دوربین', 'camera_settings', scroll, self._handle_navigate,
                                subtitle='مدیریت منابع تصویر و تنظیمات گیت‌ها')
        overlay_root = FloatLayout()
        overlay_root.add_widget(self._shell)
        self.add_widget(overlay_root)

    # -- form -------------------------------------------------------------
    def _build_form_card(self):
        card = Card(orientation="vertical", size_hint_y=None, height=450,
                    padding=[22, 14, 22, 14], spacing=8)

        self._form_title = RTLLabel(text="افزودن دوربین جدید", font_size=FONT_SIZE["subtitle"],
                                     bold=True, size_hint_y=None, height=26)
        card.add_widget(self._form_title)

        fields_row = BoxLayout(orientation="horizontal", spacing=SPACING["md"], size_hint_y=None, height=68)
        fields_row.add_widget(self._labeled("شناسه دوربین (ID)", self._make_id_input()))
        fields_row.add_widget(self._labeled("نوع انتقال داده", self._make_source_type_spinner()))
        fields_row.add_widget(self._labeled("کارکرد دوربین", self._make_role_spinner()))
        card.add_widget(fields_row)

        card.add_widget(self._labeled(
            "آدرس منبع (RTSP یا مسیر فایل ویدیو)",
            self._make_source_input(),
            fixed_height=68,
        ))

        line_row = BoxLayout(orientation="horizontal", spacing=SPACING["md"],
                             size_hint_y=None, height=68)
        self._line_inputs = []
        for label, default_value in zip(
            ("خط: X1 (۰ تا ۱)", "خط: Y1 (۰ تا ۱)",
             "خط: X2 (۰ تا ۱)", "خط: Y2 (۰ تا ۱)",
             "L: X3 (اختیاری)", "L: Y3 (اختیاری)"),
            (*_DEFAULT_LINE, "", ""),
        ):
            line_input = RoundedTextInput(
                text=str(default_value), input_filter="float", size_hint_y=None,
                height=44, halign="center",
            )
            self._line_inputs.append(line_input)
            line_row.add_widget(self._labeled(label, line_input))
        card.add_widget(line_row)

        inside_row = BoxLayout(orientation="horizontal", spacing=SPACING["md"],
                               size_hint_y=None, height=68)
        self._inside_point_inputs = []
        for label, default_value in zip(
            ("داخل پارکینگ: X", "داخل پارکینگ: Y"),
            _DEFAULT_INSIDE_POINT,
        ):
            point_input = RoundedTextInput(
                text=str(default_value), input_filter="float", size_hint_y=None,
                height=44, halign="center",
            )
            self._inside_point_inputs.append(point_input)
            inside_row.add_widget(self._labeled(label, point_input))
        self._inside_point_help = RTLLabel(
            text="", font_size=FONT_SIZE["caption"],
            color=theme.rgba(COLORS["text_secondary"]),
            size_hint_x=2, halign="right", valign="middle",
        )
        inside_row.add_widget(self._inside_point_help)
        card.add_widget(inside_row)
        self._sync_inside_point_fields()

        buttons_row = BoxLayout(orientation="horizontal", spacing=SPACING["sm"],
                                 size_hint_y=None, height=42)
        add_button = PrimaryButton(text=rtl("افزودن دوربین"), size_hint_x=None, width=154)
        add_button.bind(on_release=lambda *_: self._start_add_mode())
        save_button = PrimaryButton(text=rtl("ذخیره"), size_hint_x=None, width=108)
        save_button.bind(on_release=lambda *_: self._save())
        cancel_button = SecondaryButton(text=rtl("انصراف"), size_hint_x=None, width=108)
        cancel_button.bind(on_release=lambda *_: self._start_add_mode())

        buttons_row.add_widget(add_button)
        buttons_row.add_widget(BoxLayout())
        buttons_row.add_widget(cancel_button)
        buttons_row.add_widget(save_button)
        card.add_widget(buttons_row)

        self._error_label = RTLLabel(text="", font_size=FONT_SIZE["caption"],
                                      color=theme.rgba(COLORS["offline"]),
                                      size_hint_y=None, height=20)
        card.add_widget(self._error_label)
        return card

    def _labeled(self, label_text, field_widget, fixed_height=None):
        box = BoxLayout(orientation="vertical", spacing=4)
        if fixed_height is not None:
            box.size_hint_y = None
            box.height = fixed_height
        label = RTLLabel(text=label_text, font_size=FONT_SIZE["caption"],
                          color=theme.rgba(COLORS["text_secondary"]),
                          size_hint_y=None, height=20)
        box.add_widget(label)
        box.add_widget(field_widget)
        return box

    def _make_id_input(self):
        self._id_input = RoundedTextInput(size_hint_y=None, height=44, halign="right")
        return self._id_input

    def _make_source_input(self):
        source_row = BoxLayout(orientation="horizontal", spacing=SPACING["sm"])
        self._source_input = RoundedTextInput(size_hint_y=None, height=44, halign="right")
        self._source_input.bind(on_touch_down=self._open_picker_from_source)
        self._source_picker_button = SecondaryButton(
            text=rtl("انتخاب فایل"), size_hint_x=None, width=118,
        )
        self._source_picker_button.bind(on_release=lambda *_: self._choose_video_file())
        source_row.add_widget(self._source_input)
        source_row.add_widget(self._source_picker_button)
        self._sync_source_control()
        return source_row

    def _make_source_type_spinner(self):
        self._source_type_spinner = styled_spinner(
            values=_SOURCE_TYPE_VALUES,
            initial=rtl(SOURCE_TYPE_LABELS[SOURCE_TYPE_RTSP]),
        )
        self._source_type_spinner.bind(text=lambda *_: self._sync_source_control())
        return self._source_type_spinner

    def _source_type(self):
        return _SOURCE_TYPE_BY_DISPLAY.get(self._source_type_spinner.text, SOURCE_TYPE_RTSP)

    def _sync_source_control(self):
        if not hasattr(self, "_source_input"):
            return
        is_video = self._source_type() == SOURCE_TYPE_VIDEO_FILE
        self._source_input.readonly = is_video
        self._source_input.hint_text = (
            rtl("برای انتخاب فایل ویدیو کلیک کنید")
            if is_video else "مثال: rtsp://192.168.1.100:554/stream"
        )
        if hasattr(self, "_source_picker_button"):
            self._source_picker_button.disabled = not is_video
            self._source_picker_button.opacity = 1 if is_video else 0.42

    def _open_picker_from_source(self, widget, touch):
        if self._source_type() != SOURCE_TYPE_VIDEO_FILE or not widget.collide_point(*touch.pos):
            return False
        Clock.schedule_once(lambda _dt: self._choose_video_file(), 0)
        return True

    def _choose_video_file(self):
        if self._source_type() != SOURCE_TYPE_VIDEO_FILE:
            return
        try:
            selected_path = (
                self._windows_file_dialog_from_wsl()
                if self._is_wsl() else self._native_tk_file_dialog()
            )
        except Exception as exc:
            self._error_label.set_text(f"باز کردن پنجره انتخاب فایل ممکن نشد: {exc}")
            return
        if selected_path:
            self._source_input.text = selected_path
            self._error_label.set_text("")

    @staticmethod
    def _is_wsl():
        if sys.platform != "linux":
            return False
        try:
            with open("/proc/sys/kernel/osrelease", encoding="utf-8") as release_file:
                return "microsoft" in release_file.read().lower()
        except OSError:
            return False

    @staticmethod
    def _native_tk_file_dialog():
        from tkinter import Tk, filedialog

        dialog_root = Tk()
        dialog_root.withdraw()
        dialog_root.attributes("-topmost", True)
        try:
            return filedialog.askopenfilename(
                title="انتخاب فایل ویدیو",
                filetypes=[
                    ("Video files", "*.mp4 *.avi *.mkv *.mov *.wmv"),
                    ("All files", "*.*"),
                ],
            )
        finally:
            dialog_root.destroy()

    @staticmethod
    def _windows_file_dialog_from_wsl():
        """Open Windows' own file picker and return a WSL-readable path."""
        powershell = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
        if not os.path.isfile(powershell):
            raise RuntimeError("PowerShell ویندوز پیدا نشد")

        script = r"""
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = 'Select video file'
$dialog.Filter = 'Video files|*.mp4;*.avi;*.mkv;*.mov;*.wmv|All files|*.*'
$dialog.Multiselect = $false
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    [Console]::Write($dialog.FileName)
}
"""
        encoded_script = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        result = subprocess.run(
            [powershell, "-NoProfile", "-STA", "-EncodedCommand", encoded_script],
            capture_output=True,
            check=True,
        )
        windows_path = result.stdout.decode("utf-8", errors="replace").strip().strip("\x00")
        if not windows_path:
            return ""

        converted = subprocess.run(
            ["wslpath", "-u", windows_path],
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
        return converted or windows_path

    def _make_role_spinner(self):
        self._role_spinner = styled_spinner(
            values=_ROLE_VALUES,
            initial=rtl(ROLE_LABELS[ROLE_ENTRY]),
        )
        self._role_spinner.bind(text=self._sync_inside_point_fields)
        return self._role_spinner

    def _sync_inside_point_fields(self, *_args):
        role = _ROLE_BY_DISPLAY.get(self._role_spinner.text, ROLE_ENTRY)
        is_dual_role = role == ROLE_ENTRY_AND_EXIT
        for field in getattr(self, "_inside_point_inputs", []):
            field.disabled = not is_dual_role
        help_label = getattr(self, "_inside_point_help", None)
        if help_label is not None:
            help_label.set_text(
                "یک نقطه در سمت داخل پارکینگ وارد کنید؛ نقطه نباید روی خط باشد"
                if is_dual_role
                else "برای دوربین تک‌نقش لازم نیست"
            )

    # -- table --------------------------------------------------------
    def _build_table_card(self):
        card = Card(orientation="vertical", padding=[22, 16, 22, 18],
                    spacing=SPACING["sm"])
        title = RTLLabel(text="دوربین‌های تنظیم‌شده", font_size=FONT_SIZE["subtitle"], bold=True,
                          size_hint_y=None, height=24)
        card.add_widget(title)

        self._table_holder = BoxLayout(orientation="vertical")
        card.add_widget(self._table_holder)
        self._refresh_table()
        return card

    def _refresh_table(self):
        self._table_holder.clear_widgets()
        cameras = camera_service.get_cameras()

        if not cameras:
            self._table_holder.add_widget(EmptyState(
                icon_name="camera",
                title="هنوز دوربینی تنظیم نشده است",
                subtitle="فرم بالا را پر کنید تا اولین دوربین اضافه شود",
            ))
            return

        header = self._build_table_header()
        self._table_holder.add_widget(header)
        self._table_holder.add_widget(Divider())

        scroll = ScrollView()
        rows = GridLayout(cols=1, size_hint_y=None, spacing=2)
        rows.bind(minimum_height=rows.setter("height"))
        for camera in cameras:
            rows.add_widget(self._build_table_row(camera))
        scroll.add_widget(rows)
        self._table_holder.add_widget(scroll)

    def _build_table_header(self):
        row = Card(orientation="horizontal", size_hint_y=None, height=36, padding=0,
                   radius=4, hover_effect=False, bg_color=theme.rgba(COLORS["surface_alt"]))
        headers = [("شناسه", 0.22), ("نوع", 0.16), ("کارکرد", 0.2), ("وضعیت", 0.16), ("عملیات", 0.26)]
        for text, ratio in headers:
            cell = RTLLabel(text=text, font_size=FONT_SIZE["caption"], bold=True,
                             color=theme.rgba(COLORS["text_secondary"]), size_hint_x=ratio,
                             halign="center")
            row.add_widget(cell)
        return row

    def _build_table_row(self, camera: Camera):
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=46, spacing=4)

        id_label = RTLLabel(text=camera.id, font_size=FONT_SIZE["body"], size_hint_x=0.22,
                             halign="center")
        type_label = RTLLabel(text=camera.source_type_label(), font_size=FONT_SIZE["caption"],
                               color=theme.rgba(COLORS["text_secondary"]), size_hint_x=0.16,
                               halign="center")
        role_label = RTLLabel(text=camera.role_label(), font_size=FONT_SIZE["caption"],
                               color=theme.rgba(COLORS["text_secondary"]), size_hint_x=0.2,
                               halign="center")

        status_wrap = BoxLayout(size_hint_x=0.16)
        is_online = camera.status == STATUS_ONLINE
        status_wrap.add_widget(Badge(
            text=camera.status_label(),
            color_hex=COLORS["online"] if is_online else COLORS["offline"],
        ))

        actions_box = BoxLayout(size_hint_x=0.26, spacing=4)
        edit_button = _IconOnlyButton(icon_name="edit", color=COLORS["primary"])
        edit_button.bind(on_release=lambda *_, cam=camera: self._start_edit_mode(cam))
        delete_button = _IconOnlyButton(icon_name="delete", color=COLORS["offline"])
        delete_button.bind(on_release=lambda *_, cam=camera: self._delete(cam))
        actions_box.add_widget(edit_button)
        actions_box.add_widget(delete_button)

        row.add_widget(id_label)
        row.add_widget(type_label)
        row.add_widget(role_label)
        row.add_widget(status_wrap)
        row.add_widget(actions_box)
        return row

    # -- actions --------------------------------------------------------
    def _start_add_mode(self):
        self._editing_camera_id = None
        self._form_title.set_text("افزودن دوربین جدید")
        self._id_input.text = ""
        self._id_input.disabled = False
        self._source_input.text = ""
        self._source_type_spinner.text = rtl(SOURCE_TYPE_LABELS[SOURCE_TYPE_RTSP])
        self._sync_source_control()
        self._role_spinner.text = rtl(ROLE_LABELS[ROLE_ENTRY])
        for line_input, value in zip(self._line_inputs, (*_DEFAULT_LINE, "", "")):
            line_input.text = str(value)
        for point_input, value in zip(self._inside_point_inputs, _DEFAULT_INSIDE_POINT):
            point_input.text = str(value)
        self._sync_inside_point_fields()
        self._error_label.set_text("")

    def _start_edit_mode(self, camera: Camera):
        self._editing_camera_id = camera.id
        self._form_title.set_text(f"ویرایش دوربین: {camera.id}")
        self._id_input.text = camera.id
        self._id_input.disabled = True  # ID is the primary key; not editable once created
        self._source_input.text = camera.source
        self._source_type_spinner.text = rtl(camera.source_type_label())
        self._sync_source_control()
        self._role_spinner.text = rtl(camera.role_label())
        line_values = [value for point in camera.line for value in point]
        line_values += [""] * (6 - len(line_values))
        for line_input, value in zip(self._line_inputs, line_values):
            line_input.text = str(value)
        inside_point = camera.inside_point or _DEFAULT_INSIDE_POINT
        for point_input, value in zip(self._inside_point_inputs, inside_point):
            point_input.text = str(value)
        self._sync_inside_point_fields()
        self._error_label.set_text("")

    def _save(self):
        camera_id = self._id_input.text.strip()
        if not camera_id:
            self._error_label.set_text("شناسه دوربین نمی‌تواند خالی باشد")
            return

        source = self._source_input.text.strip()
        if not source:
            self._error_label.set_text("آدرس RTSP یا مسیر فایل ویدیو را وارد کنید")
            return

        is_new = self._editing_camera_id is None
        if is_new and camera_service.get_camera(camera_id) is not None:
            self._error_label.set_text("دوربینی با این شناسه از قبل وجود دارد")
            return

        source_type = _SOURCE_TYPE_BY_DISPLAY.get(self._source_type_spinner.text, SOURCE_TYPE_RTSP)
        role = _ROLE_BY_DISPLAY.get(self._role_spinner.text, ROLE_ENTRY)
        try:
            x1, y1, x2, y2 = (float(field.text) for field in self._line_inputs[:4])
            line_points = [[x1, y1], [x2, y2]]
            if any(field.text.strip() for field in self._line_inputs[4:]):
                line_points.append([float(field.text) for field in self._line_inputs[4:]])
        except ValueError:
            self._error_label.set_text("مختصات خط عبور باید کامل و عددی باشند")
            return
        if any(a == b for a, b in zip(line_points, line_points[1:])):
            self._error_label.set_text("دو نقطه خط عبور نمی‌توانند یکسان باشند")
            return
        existing = camera_service.get_camera(camera_id)
        if existing is not None and existing.coordinate_space != "normalized":
            self._error_label.set_text("مختصات پیکسلی قدیمی را ابتدا به بازه صفر تا یک تبدیل کنید")
            return
        coordinate_space = "normalized"
        if not all(0 <= v <= 1 for point in line_points for v in point):
            self._error_label.set_text("مختصات نرمال‌شده باید بین صفر و یک باشند")
            return
        inside_point = None
        if role == ROLE_ENTRY_AND_EXIT:
            try:
                inside_x, inside_y = (float(field.text) for field in self._inside_point_inputs)
            except ValueError:
                self._error_label.set_text("مختصات سمت داخل پارکینگ باید کامل و عددی باشند")
                return
            if not all(0 <= value <= 1 for value in (inside_x, inside_y)):
                self._error_label.set_text("مختصات نقطه داخل باید بین صفر و یک باشند")
                return
            cross = ((x2 - x1) * (inside_y - y1)
                     - (y2 - y1) * (inside_x - x1))
            if abs(cross) <= 1e-9:
                self._error_label.set_text("نقطه داخل پارکینگ نباید روی خط مرجع باشد")
                return
            inside_point = [inside_x, inside_y]
            for a, b in zip(line_points, line_points[1:]):
                cross = ((b[0] - a[0]) * (inside_y - a[1])
                         - (b[1] - a[1]) * (inside_x - a[0]))
                if abs(cross) <= 1e-9:
                    self._error_label.set_text("نقطه داخل نباید روی امتداد ضلع خط مرجع باشد")
                    return
        # A brand-new camera has no real connection yet, so it starts
        # OFFLINE - "online" would be a fake status nobody verified.
        status = existing.status if existing else STATUS_OFFLINE

        camera = Camera(
            id=camera_id,
            source_type=source_type,
            source=source,
            role=role,
            status=status,
            line=line_points,
            inside_point=inside_point,
            coordinate_space=coordinate_space,
        )

        if is_new:
            camera_service.add_camera(camera)
            show_toast(self, f"دوربین «{camera_id}» اضافه شد", kind="success")
        else:
            camera_service.update_camera(camera)
            show_toast(self, f"دوربین «{camera_id}» به‌روزرسانی شد", kind="success")

        self._start_add_mode()

    def _delete(self, camera: Camera):
        camera_service.delete_camera(camera.id)
        if self._editing_camera_id == camera.id:
            self._start_add_mode()
        show_toast(self, f"دوربین «{camera.id}» حذف شد", kind="info")

    def _on_cameras_changed(self, _cameras):
        self._refresh_table()

    def _on_camera_status_changed(self, _cameras):
        self._refresh_table()

    def _handle_navigate(self, key):
        if self.on_navigate:
            self.on_navigate(key)


class _IconOnlyButton(HoverBehavior, ButtonBehavior, BoxLayout):
    """A small square, borderless, icon-only button used for the
    Edit/Delete row actions."""

    _animated_bg = ListProperty([0, 0, 0, 0])

    def __init__(self, icon_name, color, **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (32, 32))
        super().__init__(**kwargs)
        self._normal_bg = theme.rgba(color, 0)
        self._hover_bg = theme.rgba(color, 0.12)
        self._animated_bg = self._normal_bg
        with self.canvas.before:
            self._bg_color = Color(*self._animated_bg)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[8])
        self.bind(pos=self._redraw_button, size=self._redraw_button,
                  hovered=self._animate_button, state=self._animate_button,
                  _animated_bg=self._apply_button_color)
        self._icon = Icon(name=icon_name, color=theme.rgba(color), size_hint=(None, None), size=(18, 18),
                           pos_hint={"center_x": 0.5, "center_y": 0.5})
        self.add_widget(self._icon)

    def _redraw_button(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def _animate_button(self, *_):
        target = theme.rgba(COLORS["primary_dark"], 0.18) if self.state == "down" else (
            self._hover_bg if self.hovered else self._normal_bg
        )
        Animation.cancel_all(self, "_animated_bg")
        Animation(_animated_bg=target, duration=theme.ANIM_FAST, t="out_quad").start(self)

    def _apply_button_color(self, _widget, color):
        self._bg_color.rgba = color
