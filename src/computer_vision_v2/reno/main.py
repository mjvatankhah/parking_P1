"""
main.py

The only file you run: `python main.py`

This file does not contain any business logic. All it does is:
  1. Register the Persian-capable app font (must happen before any
     widget is created).
  2. Create every screen and wire their navigation callbacks together.
  3. Start the Kivy application.

If you are new to Kivy: a Kivy app is built from "screens" managed by
a ScreenManager, which shows exactly one screen at a time and can
switch between them (`screen_manager.current = "dashboard"`). Each
screen file under ui/ builds its own widgets in its __init__/_build().

Every screen's sidebar calls one single callback, `on_navigate(key)`,
for EVERY item including "logout" - there is no separate on_logout
callback anymore. That used to exist only on the Dashboard screen,
which meant the Camera Settings sidebar's logout button silently did
nothing (a real bug found during testing). Routing "logout" through
the same _navigate() as every other screen name fixes that everywhere
at once, and keeps each screen file simpler.
"""

import sys
from pathlib import Path

# Support direct execution as well as python -m computer_vision_v2.reno.main.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kivy.config import Config

# Reasonable default desktop window size; the user can resize freely
# afterwards (see ui/*.py - layouts are built with size_hints, not
# fixed pixel positions, so they adapt to the window size).
Config.set("graphics", "width", "1200")
Config.set("graphics", "height", "780")
Config.set("graphics", "minimum_width", "1000")
Config.set("graphics", "minimum_height", "650")
# Draw the desktop chrome ourselves.  AppHeader provides the minimize,
# maximize and close buttons on every screen.
Config.set("graphics", "borderless", "1")

# Kivy's mouse input provider simulates a second touch point on
# right-click (and right-click-drag) by default, drawn as a red dot -
# useful for testing multitouch gestures on a machine with no
# touchscreen, not useful for a normal desktop app. This turns it off.
Config.set("input", "mouse", "mouse,disable_multitouch")

from kivy.app import App
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager, TransitionBase

from computer_vision_v2.reno.ui.theme import register_app_font, rgba, COLORS
from computer_vision_v2.reno.ui.login import LoginScreen
from computer_vision_v2.reno.ui.dashboard import DashboardScreen
from computer_vision_v2.reno.ui.cameras import CamerasScreen
from computer_vision_v2.reno.ui.camera_settings import CameraSettingsScreen
from computer_vision_v2.reno.ui.placeholder_screen import PlaceholderScreen

# Kivy's window clears to white by default before anything else draws.
# On a dark UI that shows up as a white flash on resize or on any gap
# between widgets, so it's set to match the app's own dark background
# right away.
Window.clearcolor = rgba(COLORS["background"])


class InstantTransition(TransitionBase):
    """Switch desktop pages without an OpenGL transition framebuffer."""

    def start(self, manager):
        self.manager = manager
        self.add_screen(self.screen_in)
        self.screen_in.pos = manager.pos
        self.screen_in.size = manager.size
        self.screen_in.dispatch("on_pre_enter")
        self.screen_out.dispatch("on_pre_leave")
        self.remove_screen(self.screen_out)
        self.screen_in.dispatch("on_enter")
        self.screen_out.dispatch("on_leave")
        self.is_active = False


class RenoApp(App):
    title = "PLAKINO"
    icon = str(Path(__file__).resolve().parent / "assets/icons/reference/app.png")

    def build(self):
        register_app_font()

        # FadeTransition renders both full screens into OpenGL frame buffers.
        # Under WSLg's software renderer this can leave the manager between
        # screens and also stall OpenCV's first video decode. A direct desktop
        # page switch is stable and keeps all button hover/press animations.
        self.screen_manager = ScreenManager(transition=InstantTransition())

        login_screen = LoginScreen(name="login", on_login_success=self._go_to_dashboard)
        dashboard_screen = DashboardScreen(name="dashboard", on_navigate=self._navigate)
        cameras_screen = CamerasScreen(name="cameras", on_navigate=self._navigate)
        camera_settings_screen = CameraSettingsScreen(name="camera_settings", on_navigate=self._navigate)
        # Reports stays an empty, navigable page until its feature is built.
        reports_screen = PlaceholderScreen(
            name="reports", page_key="reports", title="گزارش‌ها",
            on_navigate=self._navigate,
        )

        for screen in (login_screen, dashboard_screen, cameras_screen, camera_settings_screen,
                       reports_screen):
            self.screen_manager.add_widget(screen)
            # Keep every pre-built page sized even before its first transition.
            # A deferred layout may otherwise leave the first page at Kivy's
            # default 100×100 after login on the Windows/WSLg renderer.
            screen.size = self.screen_manager.size
            self.screen_manager.bind(size=screen.setter("size"))
            page_root = screen.children[0]
            page_root.size = screen.size
            screen.bind(size=page_root.setter("size"))

        self.screen_manager.current = "login"
        return self.screen_manager

    # -- navigation callbacks, shared by every screen ------------------
    def _go_to_dashboard(self):
        self._show_screen("dashboard")

    def _show_screen(self, name):
        self.screen_manager.current = name

    def _navigate(self, screen_name: str):
        if screen_name == "logout":
            self._show_screen("login")
            return
        self._show_screen(screen_name)

    def on_stop(self):
        self.screen_manager.get_screen("cameras").on_leave()


if __name__ == "__main__":
    RenoApp().run()
