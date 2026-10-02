"""
ui/components/camera_selector.py

The "[ All Cameras v ]" dropdown above the camera monitoring area.

Its options are NEVER hard-coded. On creation - and again every time
Camera Settings adds, edits or deletes a camera - it rebuilds its
option list from services/camera_service.py. This is the piece that
makes "Camera Settings drives the Dashboard selector" true.

This is a plain factory FUNCTION (not a widget class) that returns an
already-wired Spinner. That keeps it simple: no custom widget
subclass to reason about, just "call this, get a working dropdown".
"""

from computer_vision_v2.reno.ui.theme import rtl
from computer_vision_v2.reno.ui.components.common import styled_spinner
from computer_vision_v2.reno.services.camera_service import camera_service

ALL_CAMERAS_LABEL = "همه دوربین‌ها"
ALL_CAMERAS_VALUE = "__all__"


def build_camera_selector(on_select=None):
    """Create the camera-selector dropdown.

    on_select: called with the selected value every time the user
    picks something - either ALL_CAMERAS_VALUE or a real camera id.
    """
    spinner = styled_spinner(values=[], initial="", width=220)
    value_by_label = {}

    def refresh_options(*_args):
        all_label = rtl(ALL_CAMERAS_LABEL)
        value_by_label.clear()
        value_by_label[all_label] = ALL_CAMERAS_VALUE
        for camera in camera_service.get_cameras():
            value_by_label[rtl(camera.id)] = camera.id
        spinner.values = list(value_by_label.keys())
        if spinner.text not in value_by_label:
            spinner.text = all_label

    def selected_value():
        return value_by_label.get(spinner.text, ALL_CAMERAS_VALUE)

    def on_cameras_changed(_cameras):
        previous_value = selected_value()
        refresh_options()
        # Try to keep the same camera selected if it still exists,
        # otherwise fall back to "All Cameras".
        for label, value in value_by_label.items():
            if value == previous_value:
                spinner.text = label
                return
        spinner.text = rtl(ALL_CAMERAS_LABEL)

    def on_text_changed(*_args):
        if on_select:
            on_select(selected_value())

    def maybe_unsubscribe(_widget, new_parent):
        if new_parent is None:
            camera_service.unsubscribe(on_cameras_changed)

    refresh_options()
    spinner.bind(text=on_text_changed, parent=maybe_unsubscribe)
    camera_service.subscribe(on_cameras_changed)
    spinner.selected_value = selected_value  # small convenience for callers
    return spinner
