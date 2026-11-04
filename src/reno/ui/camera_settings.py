"""
ui/camera_settings.py

The Camera Settings screen: a form to add/edit a camera (ID, source
type, source, function) plus a table of already-configured cameras
with Edit/Delete actions, and Save/Cancel for the form itself.

Every change goes through services/camera_service.py. Because the
Dashboard's camera selector and the live detection page are subscribed to that
same service, adding/editing/deleting a camera here is immediately
reflected on the Dashboard - no code on this screen needs to know
that the Dashboard exists.
"""

import base64
import os
import subprocess
import sys
from threading import Thread

from kivy.uix.image import Image
from kivy.uix.popup import Popup
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

from reno.ui import theme
from reno.ui.components.page_shell import PageShell
from reno.ui.theme import COLORS, FONT_SIZE, SPACING, rtl, rtl_map, PAGE_BG_TOP, PAGE_BG_BOTTOM
from reno.ui.components.common import (
    Card, make_gradient_texture, PrimaryButton, SecondaryButton, RoundedTextInput, Divider,
    StatusDot, RTLLabel, EmptyState, show_toast, styled_spinner, HoverBehavior,
)
from reno.ui.components.sidebar import Sidebar
from reno.ui.components.app_header import AppHeader
from reno.ui.components.icons import Icon
from reno.ui.components.geometry_dialog import GeometryDialog

from reno.models.camera import (
    Camera, SOURCE_TYPE_RTSP, SOURCE_TYPE_VIDEO_FILE, SOURCE_TYPE_LABELS,
    ROLE_ENTRY, ROLE_EXIT, ROLE_ENTRY_AND_EXIT, ROLE_LABELS, STATUS_ONLINE, STATUS_OFFLINE,
)
from reno.services.camera_service import camera_service
from reno.services.camera_setup_service import CameraSetupResult, register_camera, check_connection

# Reshaped-for-display option lists + reverse lookup back to the real
# (unreshaped) model key. Built once, at import time, from the single
# source of truth in models/camera.py - see theme.rtl_map()'s
# docstring for why this exists (it's the fix for a real RTL bug found
# during the audit: dropdown text wasn't being reshaped/reordered).
_SOURCE_TYPE_VALUES, _SOURCE_TYPE_BY_DISPLAY = rtl_map(SOURCE_TYPE_LABELS)
_ROLE_VALUES, _ROLE_BY_DISPLAY = rtl_map(ROLE_LABELS)


class CameraSettingsScreen(Screen):
    """`on_navigate` is set by main.py."""

    def __init__(self, on_navigate=None, **kwargs):
        super().__init__(**kwargs)
        self.on_navigate = on_navigate
        self._editing_camera_id = None  # None => "add" mode
        self._checking = False
        self._connection_popup = None
        self._verified_settings = None
        self._updating_form = False
        self._build()
        for field in (self._gate_input, self._id_input, self._source_input,
                      self._source_type_spinner, self._role_spinner):
            field.bind(text=self._settings_changed)
        self._set_connection_state('initial')
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
        card = self._form_card = Card(orientation="vertical", size_hint_y=None, height=570,
                    padding=[22, 14, 22, 14], spacing=8)

        self._form_title = RTLLabel(text="افزودن دوربین جدید", font_size=FONT_SIZE["subtitle"],
                                     bold=True, size_hint_y=None, height=26)
        card.add_widget(self._form_title)

        self._gate_input = RoundedTextInput(size_hint_y=None, height=44, halign="right")
        card.add_widget(self._labeled('نام گیت', self._gate_input, fixed_height=68))

        fields_row = BoxLayout(orientation="horizontal", spacing=SPACING["md"], size_hint_y=None, height=68)
        camera_name = self._make_id_input()
        source_type = self._make_source_type_spinner()
        fields_row.add_widget(self._labeled("کارکرد دوربین", self._make_role_spinner()))
        fields_row.add_widget(self._labeled("نوع ورودی", source_type))
        fields_row.add_widget(self._labeled("نام دوربین", camera_name))
        card.add_widget(fields_row)

        card.add_widget(self._labeled(
            "آدرس منبع (RTSP یا مسیر فایل ویدیو)",
            self._make_source_input(),
            fixed_height=120,
        ))

        self._geometry_section = BoxLayout(orientation='vertical', size_hint_y=None, height=46, spacing=8)
        self._geometry_button = _GeometryButton(disabled=True)
        self._geometry_button.bind(on_release=lambda *_: self._select_geometry())
        self._geometry_section.add_widget(self._geometry_button)
        self._geometry_details = BoxLayout(orientation='vertical', size_hint_y=None, height=270, spacing=8)
        self._geometry_preview = Image(fit_mode='contain', size_hint_x=.72, pos_hint={'center_x': .5})
        self._geometry_hint = RTLLabel(text='مختصات ثبت شد', font_size=13,
                                        size_hint_y=None, height=26, halign='center',
                                        color=theme.rgba(COLORS['online']))
        self._geometry_details.add_widget(self._geometry_hint)
        self._geometry_details.add_widget(self._geometry_preview)
        card.add_widget(self._geometry_section)

        buttons_row = BoxLayout(orientation="horizontal", spacing=SPACING["sm"],
                                 size_hint_y=None, height=42)
        add_button = PrimaryButton(text=rtl("ثبت دوربین"), size_hint_x=None, width=154,
                                   bg_color_normal=theme.rgba('#237A54'),
                                   bg_color_hover=theme.rgba('#2B9165'),
                                   bg_color_down=theme.rgba('#195A3D'),
                                   border_color=theme.rgba('#237A54'))
        add_button.bind(on_release=lambda *_: self._save())
        cancel_button = SecondaryButton(text=rtl("انصراف"), size_hint_x=None, width=108)
        cancel_button.bind(on_release=lambda *_: self._start_add_mode())

        buttons_row.add_widget(cancel_button)
        buttons_row.add_widget(BoxLayout())
        buttons_row.add_widget(add_button)
        card.add_widget(buttons_row)

        self._error_label = RTLLabel(text="", font_size=FONT_SIZE["caption"],
                                      color=theme.rgba(COLORS["offline"]),
                                      size_hint_y=None, height=20)
        card.add_widget(self._error_label, index=1)
        card.bind(minimum_height=card.setter("height"))
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
        self._source_input = RoundedTextInput(size_hint_y=None, height=44, halign="left")
        self._source_input.bind(on_touch_down=self._open_picker_from_source)
        self._source_picker_button = SecondaryButton(
            text=rtl("انتخاب فایل"), size_hint_x=None, width=118,
        )
        self._source_picker_button.bind(on_release=lambda *_: self._choose_video_file())
        source_row.add_widget(self._source_input)
        source_row.add_widget(self._source_picker_button)
        controls = BoxLayout(orientation='vertical', spacing=8)
        controls.add_widget(source_row)
        check_row = BoxLayout(size_hint_y=None, height=44, spacing=12)
        self._connection_status = RTLLabel(text='', font_size=12)
        check_row.add_widget(self._connection_status)
        self._connection_button = PrimaryButton(text=rtl('بررسی اتصال'),
                                                size_hint_x=None, width=140)
        self._connection_button.bind(on_release=lambda *_: self._check_connection())
        check_row.add_widget(self._connection_button)
        controls.add_widget(check_row)
        self._sync_source_control()
        return controls

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
            if is_video else rtl("مثال: rtsp://192.168.1.100:554/stream")
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
        return self._role_spinner

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

        scroll = ScrollView(do_scroll_x=False, bar_width=0)
        rows = GridLayout(cols=1, size_hint_y=None, spacing=2)
        rows.bind(minimum_height=rows.setter("height"))
        for camera in cameras:
            rows.add_widget(self._build_table_row(camera))
        scroll.add_widget(rows)
        self._table_holder.add_widget(scroll)

    def _build_table_header(self):
        row = Card(orientation="horizontal", size_hint_y=None, height=36, padding=0, spacing=4,
                   radius=4, hover_effect=False, bg_color=theme.rgba(COLORS["surface_alt"]))
        headers = [("عملیات", 0.26), ("وضعیت", 0.16), ("کارکرد", 0.2), ("نوع", 0.16), ("شناسه", 0.22)]
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

        is_online = camera.status == STATUS_ONLINE
        status_wrap = RTLLabel(text=camera.status_label(), size_hint_x=0.16,
                               halign='center', font_size=FONT_SIZE['caption'],
                               color=theme.rgba('#36B37E' if is_online else '#F87171'))

        actions_box = BoxLayout(size_hint_x=0.26)
        action_buttons = BoxLayout(size_hint=(None, None), size=(68, 32), spacing=4,
                                   pos_hint={'center_y': .5})
        actions_box.add_widget(BoxLayout())
        actions_box.add_widget(action_buttons)
        actions_box.add_widget(BoxLayout())
        edit_button = _IconOnlyButton(icon_name="edit", color=COLORS["primary"])
        edit_button.bind(on_release=lambda *_, cam=camera: self._start_edit_mode(cam))
        delete_button = _IconOnlyButton(icon_name="delete", color=COLORS["offline"])
        delete_button.bind(on_release=lambda *_, cam=camera: self._delete(cam))
        action_buttons.add_widget(edit_button)
        action_buttons.add_widget(delete_button)

        row.add_widget(actions_box)
        row.add_widget(status_wrap)
        row.add_widget(role_label)
        row.add_widget(type_label)
        row.add_widget(id_label)
        return row

    def _settings_key(self):
        return (self._gate_input.text.strip(), self._id_input.text.strip(),
                self._source_input.text.strip(), self._source_type(),
                _ROLE_BY_DISPLAY.get(self._role_spinner.text))

    def _settings_changed(self, *_):
        if self._updating_form:
            return
        self._verified_settings = None
        self._set_connection_state('initial')
        self._connection_status.set_text('')
        self._show_geometry_preview('')

    def _set_connection_state(self, state):
        self._connection_state = state
        colors = {
            'initial': (COLORS['action'], COLORS['action_hover'], COLORS['primary_dark']),
            'success': ('#237A54', '#2B9165', '#195A3D'),
            'failed': ('#B83D4B', '#CC4C5B', '#962D39'),
        }
        normal, hover, down = colors[state]
        button = self._connection_button
        button.bg_color_normal = theme.rgba(normal)
        button.bg_color_hover = theme.rgba(hover)
        button.bg_color_down = theme.rgba(down)
        button.border_color = theme.rgba(normal)
        button.color = theme.rgba(COLORS['text_on_primary'])
        button._redraw()
        self._geometry_button.disabled = state != 'success'

    def _show_geometry_preview(self, path):
        visible = bool(path and os.path.isfile(path))
        self._geometry_preview.source = path if visible else ''
        if visible:
            self._geometry_preview.reload()
            if self._geometry_details.parent is None:
                self._geometry_section.add_widget(self._geometry_details)
        elif self._geometry_details.parent is not None:
            self._geometry_section.remove_widget(self._geometry_details)
        self._geometry_section.height = 324 if visible else 46
        self._geometry_hint.set_text('مختصات ثبت شد' if visible else '')

    # -- actions --------------------------------------------------------
    def _select_geometry(self):
        if (self._checking or self._connection_state != 'success'
                or self._verified_settings != self._settings_key()):
            self._error_label.set_text('ابتدا بررسی اتصال را انجام دهید؛ نتیجه باید سبز باشد.')
            return
        camera_id = self._id_input.text.strip()
        if camera_service.get_camera(camera_id) is None:
            self._error_label.set_text('ابتدا دوربین را ذخیره کنید، سپس آن را برای رسم محدوده ویرایش کنید.')
            return
        camera = camera_service.get_camera(camera_id)
        if (self._source_input.text.strip() != camera.source or self._source_type() != camera.source_type
                or _ROLE_BY_DISPLAY.get(self._role_spinner.text) != camera.role):
            self._error_label.set_text('ابتدا تغییرات منبع و کارکرد دوربین را با بررسی اتصال ثبت کنید.')
            return
        if getattr(self, '_geometry_dialog', None) is not None:
            return
        dialog = GeometryDialog(camera.to_dict(), camera_service.configuration_path, self._geometry_saved)
        self._geometry_dialog = dialog
        dialog.bind(on_dismiss=lambda *_: setattr(self, '_geometry_dialog', None))
        dialog.open()

    def _geometry_saved(self, preview):
        camera_service.reload()
        self._show_geometry_preview('')
        key = self._settings_key()

        def reveal():
            if key == self._settings_key():
                self._show_geometry_preview(preview)

        def notify(_):
            if key == self._settings_key():
                self._show_connection_result('مختصات با موفقیت ثبت شد', success=True,
                                             title='ثبت مختصات', on_confirm=reveal)
        # Allow the drawing dialog's dismissal animation to finish first.
        Clock.schedule_once(notify, .25)


    def _start_add_mode(self):
        if self._checking:
            return
        self._updating_form = True
        self._verified_settings = None
        self._gate_input.text = ""
        self._editing_camera_id = None
        self._form_title.set_text("افزودن دوربین جدید")
        self._id_input.text = ""
        self._id_input.disabled = False
        self._source_input.text = ""
        self._source_type_spinner.text = rtl(SOURCE_TYPE_LABELS[SOURCE_TYPE_RTSP])
        self._sync_source_control()
        self._role_spinner.text = rtl(ROLE_LABELS[ROLE_ENTRY])
        self._show_geometry_preview('')
        self._updating_form = False
        self._set_connection_state('initial')
        self._connection_status.set_text('')
        self._error_label.set_text("")

    def _start_edit_mode(self, camera: Camera):
        if self._checking:
            return
        self._updating_form = True
        self._gate_input.text = camera.gate_id
        self._editing_camera_id = camera.id
        self._form_title.set_text(f"ویرایش دوربین: {camera.id}")
        self._id_input.text = camera.id
        self._id_input.disabled = True  # ID is the primary key; not editable once created
        self._source_input.text = camera.source
        self._source_type_spinner.text = rtl(camera.source_type_label())
        self._sync_source_control()
        self._role_spinner.text = rtl(camera.role_label())
        self._show_geometry_preview(camera.geometry_preview)
        self._updating_form = False
        if self._verified_settings != self._settings_key():
            self._verified_settings = None
            self._set_connection_state('initial')
        self._error_label.set_text("")

    def _save(self):
        if self._checking:
            return
        gate_name = self._gate_input.text.strip()
        if not gate_name:
            self._error_label.set_text('ابتدا نام گیت را وارد کنید')
            return
        camera_id = self._id_input.text.strip()
        if not camera_id:
            self._error_label.set_text("نام دوربین نمی‌تواند خالی باشد")
            return

        if gate_name == camera_id:
            self._error_label.set_text('نام گیت و دوربین نباید یکسان باشند')
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
        existing = camera_service.get_camera(camera_id)
        same_source = existing is not None and existing.source == source and existing.source_type == source_type
        line_points = existing.line if same_source else [[.2, .6], [.8, .6]]
        inside_point = existing.inside_point if same_source and existing.inside_point else [.5, .3]
        coordinate_space = existing.coordinate_space if same_source else 'normalized'
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
            roi=existing.roi if same_source else None,
            geometry_preview=existing.geometry_preview if same_source else "",
        )

        self._verified_settings = None
        self._set_connection_state('initial')
        self._checking = True
        self._form_card.disabled = True
        self._error_label.color = theme.rgba(COLORS['text_secondary'])
        self._error_label.set_text('')
        self._connection_status.color = theme.rgba(COLORS['text_secondary'])
        self._connection_status.set_text('در حال ثبت دوربین…')

        def work():
            try:
                result = register_camera(camera, gate_name)
            except Exception:
                result = CameraSetupResult(False, 'ثبت دوربین انجام نشد؛ دوباره تلاش کنید')
            Clock.schedule_once(lambda _: self._setup_finished(camera, is_new, result))
        Thread(target=work, daemon=True).start()

    def _setup_finished(self, camera, is_new, result):
        self._checking = False
        self._form_card.disabled = False
        self._error_label.color = theme.rgba(COLORS['offline'])
        self._connection_status.color = theme.rgba(COLORS['online'] if result.success else COLORS['offline'])
        self._connection_status.set_text(result.message)
        if not result.success:
            self._verified_settings = None
            self._set_connection_state('initial')
            self._error_label.set_text("")
            self._show_connection_result(result.message, success=False, title="ثبت دوربین")
            return
        try:
            if is_new:
                camera_service.add_camera(camera)
            else:
                camera_service.update_camera(camera)
        except OSError:
            self._set_connection_state('initial')
            self._error_label.set_text('')
            self._show_connection_result('ثبت دیتابیس موفق بود، اما ذخیره تنظیمات محلی انجام نشد', success=False, title='ثبت دوربین')
            return
        self._start_edit_mode(camera)
        self._verified_settings = None
        self._set_connection_state('initial')
        self._error_label.color = theme.rgba(COLORS['online'])
        self._error_label.set_text('')
        self._show_connection_result(result.message, success=True, title="ثبت دوربین")

    def _check_connection(self):
        if self._checking:
            return
        camera = camera_service.get_camera(self._id_input.text.strip())
        if camera is None or self._settings_key() != (camera.gate_id, camera.id, camera.source, camera.source_type, camera.role):
            self._error_label.set_text('ابتدا اطلاعات دوربین را با دکمه ثبت دوربین ذخیره کنید.')
            return
        self._verified_settings = None
        self._set_connection_state('initial')
        self._checking = True
        self._form_card.disabled = True
        key = self._settings_key()
        self._connection_status.set_text('در حال بررسی اتصال…')

        def work():
            try:
                result = check_connection(camera)
            except Exception:
                result = CameraSetupResult(False, 'بررسی اتصال انجام نشد؛ دوباره تلاش کنید')
            Clock.schedule_once(lambda _: self._connection_checked(result, key))
        Thread(target=work, daemon=True).start()

    def _connection_checked(self, result, key):
        self._checking = False
        self._form_card.disabled = False
        if key != self._settings_key():
            self._settings_changed()
            return
        self._verified_settings = key if result.success else None
        self._set_connection_state('success' if result.success else 'failed')
        self._connection_status.color = theme.rgba(COLORS['online'] if result.success else COLORS['offline'])
        self._connection_status.set_text(result.message)
        self._show_connection_result(result.message, success=result.success)

    def _show_connection_result(self, message, success, title="نتیجه بررسی اتصال", on_confirm=None):
        if self._connection_popup:
            self._connection_popup.dismiss()
        body = BoxLayout(orientation='vertical', padding=20, spacing=18)
        body.add_widget(Icon(name='camera', size_hint=(None, None), size=(42, 42),
                             pos_hint={'center_x': .5},
                             color=theme.rgba(COLORS['online'] if success else COLORS['offline'])))
        body.add_widget(RTLLabel(text=message, halign='center', font_size=14))
        okay = PrimaryButton(text=rtl('باشه'), size_hint=(None, None), size=(120, 44),
                             pos_hint={'center_x': .5})
        body.add_widget(okay)
        popup = Popup(title=rtl(title), title_font=theme.APP_FONT_NAME,
                      title_align='right', content=body, auto_dismiss=False,
                      size_hint=(None, None), size=(480, 300), separator_height=1,
                      background='', background_color=theme.rgba(COLORS['surface']))
        self._connection_popup = popup
        def acknowledge(*_):
            popup.dismiss()
            if on_confirm:
                on_confirm()
        okay.bind(on_release=acknowledge)

        def clear(*_):
            if self._connection_popup is popup:
                self._connection_popup = None
        popup.bind(on_dismiss=clear)
        popup.open()

    def _delete(self, camera: Camera):
        if self._checking:
            return
        camera_service.delete_camera(camera.id)
        if self._editing_camera_id == camera.id:
            self._start_add_mode()
        show_toast(self, f"دوربین «{camera.id}» حذف شد", kind="info")

    def _on_cameras_changed(self, _cameras):
        self._refresh_table()
        if self._editing_camera_id:
            camera = camera_service.get_camera(self._editing_camera_id)
            if camera is not None:
                self._start_edit_mode(camera)

    def _on_camera_status_changed(self, _cameras):
        self._refresh_table()

    def _handle_navigate(self, key):
        if self.on_navigate:
            self.on_navigate(key)


class _GeometryButton(HoverBehavior, ButtonBehavior, Card):
    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=46, padding=[16, 8], spacing=12,
                         radius=9, bg_color=theme.rgba(COLORS['primary_light']), **kwargs)
        content = FloatLayout()
        content.add_widget(RTLLabel(text='رسم خط مرجع و محدوده پردازش', font_size=14,
                                    halign='center', padding=[40, 0],
                                    pos_hint={'center_x': .5, 'center_y': .5}))
        content.add_widget(Icon(name='edit', color=theme.rgba(COLORS['primary']),
                                size_hint=(None, None), size=(23, 23),
                                pos_hint={'right': 1, 'center_y': .5}))
        self.add_widget(content)


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
