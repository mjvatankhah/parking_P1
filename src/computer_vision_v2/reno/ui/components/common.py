"""
ui/components/common.py

Small, generic, reusable building blocks used by every screen: a
rounded "card" container, a primary/secondary button, a rounded text
input and a little colored "online/offline" status dot.

Kivy's stock widgets (Button, TextInput, ...) are drawn from bitmap
"background_normal" images that are hard to restyle, so the pattern
used throughout this file is:

    1. Turn the stock background off (background_color = transparent,
       background_normal = '').
    2. Draw our own shape (usually a RoundedRectangle) on
       canvas.before, using the app's theme colors.
    3. Redraw that shape whenever the widget moves/resizes (bind pos
       and size to a `_redraw` method) so it always matches the
       widget's current position.

Every other component/screen in this project builds on top of these
few classes instead of repeating this pattern.
"""

import math
from functools import lru_cache

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.uix.floatlayout import FloatLayout
from kivy.graphics import Color, RoundedRectangle, Line, Ellipse, InstructionGroup, Mesh
from kivy.graphics.texture import Texture
from kivy.properties import ListProperty, NumericProperty, StringProperty, BooleanProperty
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window

from computer_vision_v2.reno.ui import theme
from computer_vision_v2.reno.ui.theme import COLORS, RADIUS, FONT_SIZE, SPACING, rtl


@lru_cache(maxsize=32)
def make_gradient_texture(top_hex: str, bottom_hex: str, steps: int = 256):
    """Build a small vertical-gradient texture between two hex colors.

    Used to give a handful of "hero" surfaces (see StatCard) real
    depth instead of a flat fill, without ever needing an image asset:
    the gradient is generated in memory and applied as the `texture`
    of a RoundedRectangle, so it's still clipped to rounded corners
    like a normal Card.
    """
    top = theme.rgba(top_hex)
    bottom = theme.rgba(bottom_hex)
    buf = bytearray()
    for i in range(steps):
        t = 1 - i / (steps - 1)
        r = round((top[0] * (1 - t) + bottom[0] * t) * 255)
        g = round((top[1] * (1 - t) + bottom[1] * t) * 255)
        b = round((top[2] * (1 - t) + bottom[2] * t) * 255)
        buf += bytes([r, g, b, 255])
    texture = Texture.create(size=(1, steps), colorfmt="rgba")
    texture.blit_buffer(bytes(buf), colorfmt="rgba", bufferfmt="ubyte")
    texture.wrap = "clamp_to_edge"
    texture.min_filter = texture.mag_filter = "linear"
    return texture


@lru_cache(maxsize=16)
def make_spotlight_texture(first_hex: str, second_hex: str, steps: int = 256):
    """Build a two-tone border highlight with transparent, feathered tails."""
    first = theme.rgba(first_hex)
    second = theme.rgba(second_hex)
    buf = bytearray()
    for i in range(steps):
        t = i / (steps - 1)
        color_mix = min(1, max(0, (t - .32) / .36))
        intensity = math.exp(-.5 * ((t - .5) / .135) ** 2)
        rgb = [first[channel] * (1-color_mix) + second[channel] * color_mix
               for channel in range(3)]
        buf += bytes([*(round(value*255) for value in rgb), round(intensity*255)])
    texture = Texture.create(size=(1, steps), colorfmt="rgba")
    texture.blit_buffer(bytes(buf), colorfmt="rgba", bufferfmt="ubyte")
    texture.wrap = "repeat"
    texture.min_filter = texture.mag_filter = "linear"
    return texture


class Card(BoxLayout):
    """Reference glass surface; optional gradient is confined to the thin frame."""

    bg_color = ListProperty(theme.rgba(COLORS['surface']))
    border_color = ListProperty(theme.rgba(COLORS['border']))
    radius = NumericProperty(10)
    _hover_amount = NumericProperty(0)
    _border_phase = NumericProperty(0)

    def __init__(self, gradient=None, border_gradient=None, hover_effect=True, animated_border=False, **kwargs):
        super().__init__(**kwargs)
        self._hover_enabled = hover_effect
        self._has_fill_gradient = bool(gradient)
        self._frame = None
        self._halo = None
        self._spotlight_texture = None
        self._animated_border = animated_border and bool(border_gradient)
        self._neon_glow = []
        with self.canvas.before:
            self._shadow_color = Color(0, 0, 0, .18)
            self._shadow = RoundedRectangle(pos=self.pos, size=self.size, radius=[self.radius])
            self._color = Color(1, 1, 1, self.bg_color[3]) if gradient else Color(*self.bg_color)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[self.radius],
                texture=make_gradient_texture(*gradient) if gradient else None)
            self._border_color_instr = Color(*self.border_color)
            self._border = Line(rounded_rectangle=(*self.pos, *self.size, self.radius), width=.65)
            self._shine_color = Color(1, 1, 1, .045)
            self._shine = Line(points=[], width=.6)
        # Paint the accent after child canvases so content cannot cover it.
        with self.canvas.after:
            if border_gradient:
                if self._animated_border:
                    self._spotlight_texture = make_spotlight_texture(*border_gradient)
                    self._halo_color = Color(1, 1, 1, .20)
                    self._halo = Mesh(vertices=[], indices=[], mode='triangles',
                                      texture=self._spotlight_texture)
                self._frame_color = Color(1, 1, 1, .68)
                self._frame = Mesh(vertices=[], indices=[], mode='triangles',
                                   texture=(self._spotlight_texture or
                                            make_gradient_texture(*border_gradient)))
        if hover_effect:
            Window.bind(mouse_pos=self._glass_hover)
        self.bind(pos=self._redraw, size=self._redraw, bg_color=self._redraw,
                  border_color=self._redraw, radius=self._redraw, _hover_amount=self._redraw)
        self.bind(_border_phase=self._redraw)
        self._border_animation = (Clock.schedule_interval(self._animate_border, 1/30)
                                  if self._animated_border else None)
        self._redraw()

    def _animate_border(self, dt):
        if self.get_root_window():
            self._border_phase = (self._border_phase + dt*math.tau/18) % math.tau

    def _glass_hover(self, _window, position):
        hovered = bool(self.get_root_window() and self.collide_point(*self.to_widget(*position)))
        target = float(hovered)
        if getattr(self, '_hover_target', None) != target:
            self._hover_target = target
            Animation.cancel_all(self, '_hover_amount')
            Animation(_hover_amount=target, duration=theme.ANIM_FAST, t='out_quad').start(self)

    def _redraw(self, *_):
        self._color.rgba = (1, 1, 1, self.bg_color[3]) if self._has_fill_gradient else self.bg_color
        self._shadow.pos, self._shadow.size = (self.x, self.y-3), self.size
        self._shadow.radius = [self.radius]
        self._rect.pos, self._rect.size, self._rect.radius = self.pos, self.size, [self.radius]
        self._border_color_instr.rgba = self.border_color
        self._border_color_instr.a = min(1, self.border_color[3] + .15*self._hover_amount)
        self._border.rounded_rectangle = (*self.pos, *self.size, self.radius)
        self._shine.points = [self.x+18, self.y+self.height-1,
                              max(self.x+18, self.x+self.width-18), self.y+self.height-1]
        if self._frame is not None:
            self._frame_color.a = (.96 + .04*self._hover_amount if self._animated_border
                                   else .68 + .3*self._hover_amount)
            self._update_gradient_frame()

    def _update_gradient_frame(self):
        """Draw a neutral hairline plus one feathered highlight on the perimeter."""
        radius = min(self.radius, self.width/2, self.height/2)
        right, top = self.x+self.width, self.y+self.height
        corner_points = []
        for cx, cy, start in [(right-radius, top-radius, 0),
                              (self.x+radius, top-radius, 90),
                              (self.x+radius, self.y+radius, 180),
                              (right-radius, self.y+radius, 270)]:
            for step in range(13):
                angle = math.radians(start + step*90/12)
                corner_points.append((cx+radius*math.cos(angle),
                                      cy+radius*math.sin(angle)))

        points = []
        for index, point in enumerate(corner_points):
            following = corner_points[(index+1) % len(corner_points)]
            distance = math.dist(point, following)
            samples = max(1, math.ceil(distance/10)) if self._animated_border else 1
            for sample in range(samples):
                t = sample/samples
                points.append((point[0]+(following[0]-point[0])*t,
                               point[1]+(following[1]-point[1])*t))

        distances = [0]
        for point, following in zip(points, points[1:]):
            distances.append(distances[-1] + math.dist(point, following))
        perimeter = distances[-1] + math.dist(points[-1], points[0])

        def ring_geometry(thickness):
            vertices = []
            # Duplicate the closing point with UV + 1: interpolating back to
            # UV zero would stretch a second highlight across the last segment.
            for index in range(len(points)+1):
                x, y = points[index % len(points)]
                # The closest point in the rounded rectangle's inner box
                # gives the outward normal on both straight edges and arcs.
                cx = min(right-radius, max(self.x+radius, x))
                cy = min(top-radius, max(self.y+radius, y))
                dx, dy = x-cx, y-cy
                if dx == 0 and dy == 0:
                    # Square corners still need a normal on each straight edge.
                    _, dx, dy = min((abs(x-self.x), -1, 0),
                                    (abs(x-right), 1, 0),
                                    (abs(y-self.y), 0, -1),
                                    (abs(y-top), 0, 1))
                length = max(.0001, math.hypot(dx, dy))
                distance = distances[index] if index < len(points) else perimeter
                texture_v = distance/perimeter + self._border_phase/math.tau
                for inset in (0, thickness):
                    vertices.extend((x-dx/length*inset, y-dy/length*inset,
                                     .5, texture_v))
            indices = []
            for index in range(len(points)):
                a, b = 2*index, 2*(index+1)
                indices.extend((a, a+1, b, a+1, b+1, b))
            return vertices, indices

        thickness = (1.1 if self._animated_border else 1.15) + .2*self._hover_amount
        self._frame.vertices, self._frame.indices = ring_geometry(thickness)
        if self._halo is not None:
            self._halo.vertices, self._halo.indices = ring_geometry(4.5)

class HoverBehavior:
    """Adds a desktop hover state without changing touch behavior."""

    hovered = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.bind(mouse_pos=self._track_pointer)

    def _track_pointer(self, _window, position):
        if not self.get_root_window():
            self.hovered = False
            return
        self.hovered = self.collide_point(*self.to_widget(*position))


class _RoundedButtonBase(HoverBehavior, ButtonBehavior, Label):
    """Shared drawing logic for PrimaryButton / SecondaryButton /
    GhostButton - only the colors differ between them. Background
    color changes (hover/press/disabled) are animated with a short
    fade instead of an instant swap - see theme.ANIM_FAST."""

    bg_color_normal = ListProperty([0, 0, 0, 0])
    bg_color_hover = ListProperty([0, 0, 0, 0])
    bg_color_down = ListProperty([0, 0, 0, 0])
    border_color = ListProperty([0, 0, 0, 0])
    radius = NumericProperty(RADIUS["sm"])
    _animated_color = ListProperty([0, 0, 0, 0])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.font_name = theme.APP_FONT_NAME
        self.font_size = kwargs.get("font_size", FONT_SIZE["body"])
        self.padding = [8, 2]
        with self.canvas.before:
            self._color = Color(*self.bg_color_normal)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[self.radius])
            self._border_color_instr = Color(*self.border_color)
            self._border = Line(rounded_rectangle=(*self.pos, *self.size, self.radius), width=.7)
            self._animated_color = list(self.bg_color_normal)
        self.bind(pos=self._reposition, size=self._reposition,
                  state=self._redraw, disabled=self._redraw, hovered=self._redraw)

    def _reposition(self, *args):
        self._rect.pos = self.pos
        self._rect.size = self.size
        self._border.rounded_rectangle = (*self.pos, *self.size, self.radius)

    def _redraw(self, *args):
        self._reposition()
        if self.disabled:
            target = theme.rgba(COLORS["disabled_bg"])
            self.color = theme.rgba(COLORS["disabled_text"])
        else:
            if self.state == "down":
                target = self.bg_color_down
            elif self.hovered:
                target = self.bg_color_hover
            else:
                target = self.bg_color_normal
        Animation.cancel_all(self, "_animated_color")
        Animation(_animated_color=target, duration=theme.ANIM_FAST, t="out_quad").start(self)
        self._border_color_instr.rgba = self.border_color

    def on__animated_color(self, _widget, value):
        self._color.rgba = value


class PrimaryButton(_RoundedButtonBase):
    """Solid brand-colored button, e.g. the Login / Save buttons."""

    def __init__(self, **kwargs):
        kwargs.setdefault("bg_color_normal", theme.rgba(COLORS["action"]))
        kwargs.setdefault("bg_color_hover", theme.rgba(COLORS["action_hover"]))
        kwargs.setdefault("bg_color_down", theme.rgba(COLORS["primary_dark"]))
        kwargs.setdefault("border_color", theme.rgba(COLORS["action"]))
        kwargs.setdefault("color", theme.rgba(COLORS["text_on_primary"]))
        super().__init__(**kwargs)


class SecondaryButton(_RoundedButtonBase):
    """Outlined button for secondary actions, e.g. Cancel."""

    def __init__(self, **kwargs):
        kwargs.setdefault("bg_color_normal", theme.rgba(COLORS["surface"]))
        kwargs.setdefault("bg_color_hover", theme.rgba(COLORS["primary_light"]))
        kwargs.setdefault("bg_color_down", theme.rgba(COLORS["background"]))
        kwargs.setdefault("border_color", theme.rgba(COLORS["border"]))
        kwargs.setdefault("color", theme.rgba(COLORS["text_primary"]))
        super().__init__(**kwargs)


class DangerButton(_RoundedButtonBase):
    """Used for the Delete action."""

    def __init__(self, **kwargs):
        kwargs.setdefault("bg_color_normal", theme.rgba(COLORS["offline"]))
        kwargs.setdefault("bg_color_hover", theme.rgba("#F08C92"))
        kwargs.setdefault("bg_color_down", theme.rgba("#D45C5C"))
        kwargs.setdefault("border_color", theme.rgba(COLORS["offline"]))
        kwargs.setdefault("color", theme.rgba(COLORS["text_on_primary"]))
        super().__init__(**kwargs)


class RoundedTextInput(TextInput):
    """A single-line-styled TextInput with a rounded, bordered
    background that changes color when focused, instead of Kivy's
    default beveled image background."""

    radius = NumericProperty(RADIUS["sm"])

    def __init__(self, **kwargs):
        kwargs.setdefault("multiline", False)
        kwargs.setdefault("font_name", theme.APP_FONT_NAME)
        kwargs.setdefault("font_size", FONT_SIZE["body"])
        # The Persian font needs enough room around its ascenders and baseline.
        kwargs.setdefault("padding", [18, 10, 18, 10])
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_active", "")
        kwargs.setdefault("background_color", (0, 0, 0, 0))
        kwargs.setdefault("cursor_color", theme.rgba(COLORS["primary"]))
        kwargs.setdefault("foreground_color", theme.rgba(COLORS["text_primary"]))
        kwargs.setdefault("disabled_foreground_color", theme.rgba(COLORS["disabled_text"]))
        kwargs.setdefault("hint_text_color", theme.rgba(COLORS["placeholder"]))
        super().__init__(**kwargs)
        # Insert the decoration BEFORE Kivy's cursor/foreground instructions.
        # Appending it would tint the text with the pale border color and
        # paint over the cursor, making entered values nearly invisible.
        background = InstructionGroup()
        self._color = Color(*theme.rgba(COLORS["background"]))
        self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[self.radius])
        self._border_color_instr = Color(*theme.rgba(COLORS["border"]))
        self._border = Line(rounded_rectangle=(*self.pos, *self.size, self.radius), width=.7)
        for instruction in (self._color, self._rect, self._border_color_instr, self._border):
            background.add(instruction)
        self.canvas.before.insert(0, background)
        self.bind(pos=self._redraw, size=self._redraw, focus=self._redraw)

    def _redraw(self, *args):
        self._rect.pos = self.pos
        self._rect.size = self.size
        self._border.rounded_rectangle = (*self.pos, *self.size, self.radius)
        if self.focus:
            self._color.rgba = theme.rgba(COLORS["surface"])
            self._border_color_instr.rgba = theme.rgba(COLORS["primary"])
        else:
            self._color.rgba = theme.rgba(COLORS["background"])
            self._border_color_instr.rgba = theme.rgba(COLORS["border"])


class StatusDot(BoxLayout):
    """A small colored circle used to show a camera's online/offline
    state next to its name. When `pulse=True` (used for "online"), a
    soft ring animates outward and fades on a loop - a small,
    purposeful motion that communicates "this is live" rather than a
    static icon."""

    dot_color = ListProperty(theme.rgba(COLORS["online"]))
    _pulse_radius = NumericProperty(0.0)
    _pulse_alpha = NumericProperty(0.0)

    def __init__(self, pulse=False, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (14, 14)
        with self.canvas:
            self._pulse_color = Color(*self.dot_color[:3], 0)
            self._pulse_ring = Ellipse(pos=self.pos, size=self.size)
            self._color = Color(*self.dot_color)
            self._dot = Ellipse(pos=self.pos, size=(10, 10))
        self.bind(pos=self._redraw, size=self._redraw, dot_color=self._redraw,
                  _pulse_radius=self._redraw)
        self._redraw()
        if pulse:
            self._pulse_loop()

    def _redraw(self, *args):
        self._color.rgba = self.dot_color
        self._pulse_color.rgb = self.dot_color[:3]
        cx, cy = self.center
        self._dot.pos = (cx - 5, cy - 5)
        self._dot.size = (10, 10)
        r = 5 + self._pulse_radius
        self._pulse_ring.pos = (cx - r, cy - r)
        self._pulse_ring.size = (r * 2, r * 2)

    def _pulse_loop(self, *_args):
        self._pulse_radius = 0
        self._pulse_alpha = 0.4
        anim = Animation(_pulse_radius=9, _pulse_alpha=0, duration=1.3, t="out_quad")
        anim.bind(on_complete=self._pulse_loop)
        anim.start(self)

    def on__pulse_alpha(self, _widget, value):
        self._pulse_color.a = value


class Divider(Widget):
    """A thin horizontal rule used to separate sections inside a card."""

    line_color = ListProperty(theme.rgba(COLORS["border"]))

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", 1)
        super().__init__(**kwargs)
        with self.canvas:
            self._color = Color(*self.line_color)
            self._line = Line(points=[self.x, self.y, self.right, self.y], width=1)
        self.bind(pos=self._redraw, size=self._redraw)

    def _redraw(self, *args):
        self._line.points = [self.x, self.y, self.right, self.y]


class RTLLabel(Label):
    """The one Label every screen should use for Persian text.

    Fixes, in one place, the three things that have to be right for
    Persian to look correct (found during the UI audit - some labels
    had one or two of these but not all three):

      1. rtl(text) - reshape + reorder the text (see ui/theme.py).
      2. halign="right" AND text_size bound to the widget's own size -
         Kivy ignores halign entirely until text_size is set, which is
         why some labels still looked left-aligned even after rtl().
      3. line_height=LINE_HEIGHT_FA - Persian needs more vertical room
         between lines than Kivy's Latin-tuned default.

    Pass raw Persian (or mixed) text; do not pre-call rtl() yourself.
    For plain Latin/numeric content (camera IDs, timestamps) keep
    using a plain Label - rtl() on pure-Latin text is a harmless
    no-op, but a plain Label is one less abstraction to think about.
    """

    def __init__(self, text="", **kwargs):
        kwargs.setdefault("font_name", theme.APP_FONT_NAME)
        kwargs.setdefault("font_size", FONT_SIZE["body"])
        kwargs.setdefault("halign", "right")
        kwargs.setdefault("valign", "middle")
        kwargs.setdefault("color", theme.rgba(COLORS["text_primary"]))
        kwargs.setdefault("line_height", theme.LINE_HEIGHT_FA)
        # A few pixels of inset prevent Persian glyph overhangs from being
        # clipped at the right/left edge of tightly sized labels.
        kwargs.setdefault("padding", [8, 2])
        super().__init__(text=rtl(text), **kwargs)
        self.bind(size=self._sync_text_size)
        self._sync_text_size()

    def _sync_text_size(self, *_args):
        self.text_size = self.size

    def set_text(self, raw_text: str):
        """Update the label's text later, still going through rtl()."""
        self.text = rtl(raw_text)


class Badge(BoxLayout):
    """A small rounded status pill, e.g. 'آنلاین' / 'آفلاین'. Replaces
    the plain colored-text pattern used ad hoc in a couple of places
    before the audit, so every status indicator in the app looks the
    same."""

    def __init__(self, text: str, color_hex: str, **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("height", 24)
        kwargs.setdefault("padding", [10, 0, 10, 0])
        super().__init__(**kwargs)
        with self.canvas.before:
            self._bg = Color(*theme.rgba(color_hex, 0.14))
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[12])
        self.bind(pos=self._redraw, size=self._redraw)

        self._label = RTLLabel(
            text=text,
            font_size=FONT_SIZE["caption"],
            color=theme.rgba(color_hex),
            halign="center",
            size_hint=(None, None),
        )
        self._label.bind(texture_size=self._fit_to_label)
        self.add_widget(self._label)

    def _fit_to_label(self, _label, texture_size):
        self.width = texture_size[0] + 20
        self._label.size = texture_size

    def _redraw(self, *args):
        self._rect.pos = self.pos
        self._rect.size = self.size


class EmptyState(BoxLayout):
    """The 'nothing here yet' view every list/table/panel in the app
    should show instead of manufacturing fake rows to look fuller.

    This is a direct design-system-level fix for the audit finding
    that mock data was being used to avoid ever showing an empty
    screen: now there is one correct, polished way to show "no data
    yet", so no screen has an excuse to fake it.
    """

    def __init__(self, icon_name: str, title: str, subtitle: str = "",
                 action_text: str = "", on_action=None, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("spacing", SPACING["sm"])
        kwargs.setdefault("padding", [SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"]])
        super().__init__(**kwargs)

        from computer_vision_v2.reno.ui.components.icons import Icon  # local import: avoids a cycle with icons.py

        self.add_widget(BoxLayout(size_hint_y=1))
        self.add_widget(Icon(name=icon_name, color=theme.rgba(COLORS["placeholder"]),
                              size_hint=(None, None), size=(40, 40), pos_hint={"center_x": 0.5}))
        self.add_widget(RTLLabel(text=title, font_size=FONT_SIZE["subtitle"], bold=True,
                                  halign="center", color=theme.rgba(COLORS["text_secondary"]),
                                  size_hint_y=None, height=26))
        if subtitle:
            self.add_widget(RTLLabel(text=subtitle, font_size=FONT_SIZE["caption"],
                                      halign="center", color=theme.rgba(COLORS["placeholder"]),
                                      size_hint_y=None, height=42))
        if action_text and on_action:
            action_button = SecondaryButton(text=rtl(action_text), size_hint=(None, None),
                                             size=(180, 40), pos_hint={"center_x": 0.5})
            action_button.bind(on_release=lambda *_: on_action())
            self.add_widget(action_button)
        self.add_widget(BoxLayout(size_hint_y=1))


class LoadingSpinner(Widget):
    """A small indeterminate spinner (a rotating arc), used while a
    (future, real) backend call is in flight. There is no async
    backend to trigger this yet, so it is wired up for the moments
    that already take a visible beat (see ui/login.py's login button)
    and ready for real async calls later."""

    def __init__(self, color_hex=COLORS["primary"], **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (20, 20))
        super().__init__(**kwargs)
        self._angle = 0
        with self.canvas:
            self._color = Color(*theme.rgba(color_hex))
            self._arc = Line(width=2.2)
        self.bind(pos=self._redraw, size=self._redraw)
        self._event = Clock.schedule_interval(self._tick, 1 / 30)
        self._redraw()

    def _tick(self, dt):
        self._angle = (self._angle + dt * 320) % 360
        self._redraw()

    def _redraw(self, *args):
        r = min(self.width, self.height) / 2
        cx, cy = self.center
        self._arc.circle = (cx, cy, r, self._angle, self._angle + 260)

    def stop(self):
        self._event.cancel()
        self.canvas.clear()


class Toast(BoxLayout):
    """A small, self-dismissing notification pinned to the bottom of
    a screen - used for success/error feedback after an action (save,
    delete, add) instead of a blocking Popup, per the design system's
    'Success/Error state' requirement.

    Usage from any Screen:
        from computer_vision_v2.reno.ui.components.common import show_toast
        show_toast(self, "دوربین ذخیره شد", kind="success")
    """

    _KIND_COLORS = {
        "success": COLORS["online"],
        "error": COLORS["offline"],
        "info": COLORS["info"],
    }

    def __init__(self, message: str, kind: str = "info", **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("height", 44)
        kwargs.setdefault("padding", [SPACING["md"], 0, SPACING["md"], 0])
        kwargs.setdefault("pos_hint", {"center_x": 0.5, "y": 0.04})
        super().__init__(**kwargs)
        color_hex = self._KIND_COLORS.get(kind, COLORS["info"])

        with self.canvas.before:
            self._color = Color(*theme.rgba(color_hex, 0))
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[10])
        self.bind(pos=self._redraw, size=self._redraw)

        label = RTLLabel(text=message, color=theme.rgba(COLORS["text_on_primary"]),
                          font_size=FONT_SIZE["body"], halign="center", size_hint=(None, None))
        label.bind(texture_size=self._fit_to_label)
        self.add_widget(label)
        self._label = label
        self.opacity = 0

    def _fit_to_label(self, _label, texture_size):
        self.width = texture_size[0] + SPACING["lg"] * 2
        self._label.size = texture_size
        self._rect.size = self.size

    def _redraw(self, *args):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def show_on(self, root: FloatLayout, duration: float = 2.0):
        root.add_widget(self)
        color_hex = self._KIND_COLORS.get(getattr(self, "_kind", "info"), COLORS["info"])
        self._color.rgba = theme.rgba(color_hex, 0.96)
        anim_in = Animation(opacity=1, duration=theme.ANIM_NORMAL)
        anim_out = Animation(opacity=0, duration=theme.ANIM_NORMAL)

        def _remove(*_args):
            if self.parent:
                self.parent.remove_widget(self)

        anim_in.start(self)
        Clock.schedule_once(lambda *_: anim_out.start(self), duration)
        anim_out.bind(on_complete=lambda *_a: _remove())


def show_toast(screen, message: str, kind: str = "info", duration: float = 2.2):
    """Convenience wrapper: find the FloatLayout root a Screen built
    (every screen in this project builds one as its outermost/near-
    outermost widget for exactly this reason) and pop a Toast onto it.
    """
    root = screen
    # walk down to the first FloatLayout, which every screen in this
    # project provides at or near the top of its widget tree
    while root.children and not isinstance(root, FloatLayout):
        root = root.children[0]
    toast = Toast(message, kind=kind)
    toast._kind = kind
    toast.show_on(root, duration=duration)


# ---------------------------------------------------------------------
# Styled Spinner (dropdown) - fixes a real bug found in testing: the
# dropdown's OPTION list is built from a separate widget class
# (SpinnerOption) that does NOT inherit the Spinner's own font_name,
# so Persian option text was falling back to Kivy's default font
# (no Persian glyphs -> effectively invisible/blank-looking rows).
# Every dropdown in the app should be built with styled_spinner()
# instead of a bare kivy Spinner, so this stays fixed everywhere.
# ---------------------------------------------------------------------
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.dropdown import DropDown


class _StyledSpinnerOption(SpinnerOption):
    """One row inside an open dropdown list."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.font_name = theme.APP_FONT_NAME
        self.font_size = kwargs.get("font_size", FONT_SIZE["body"])
        self.background_normal = ""
        self.background_down = ""
        self.background_color = theme.rgba(COLORS["surface"])
        self.color = theme.rgba(COLORS["text_primary"])
        self.halign = "center"


class _AnimatedDropDown(DropDown):
    """Same dropdown behavior as Kivy's default, with a quick fade-in
    instead of appearing instantly - part of the 'animation should aid
    understanding, not decorate' pass: it signals *where* the list
    came from (the spinner you just tapped)."""

    def open(self, widget):
        super().open(widget)
        self.opacity = 0
        Animation(opacity=1, duration=theme.ANIM_NORMAL, t="out_quad").start(self)


class _StyledSpinner(HoverBehavior, Spinner):
    """Shared outlined dropdown with consistent focus/hover and Lucide affordance."""
    _surface_rgba = ListProperty(theme.rgba(COLORS['surface']))

    def __init__(self, **kwargs):
        kwargs['background_color'] = (0,0,0,0)
        super().__init__(**kwargs)
        from computer_vision_v2.reno.ui.components.icons import Icon
        with self.canvas.before:
            self._surface_color = Color(*self._surface_rgba)
            self._surface = RoundedRectangle(pos=self.pos,size=self.size,radius=[6])
            self._outline_color = Color(*theme.rgba(COLORS['border']))
            self._outline = Line(rounded_rectangle=(*self.pos,*self.size,6),width=.65)
        self._chevron = Icon(name='chevron_down',color=theme.rgba(COLORS['text_secondary']),
                             size_hint=(None,None),size=(12,12))
        self.add_widget(self._chevron)
        self.bind(hovered=self._animate_surface,state=self._animate_surface,
                  pos=self._position_surface,size=self._position_surface,
                  _surface_rgba=self._sync_surface)
        self._position_surface()

    def _position_surface(self,*_):
        self._surface.pos,self._surface.size=self.pos,self.size
        self._outline.rounded_rectangle=(*self.pos,*self.size,6)
        self._chevron.pos=(self.x+9,self.center_y-6)

    def _sync_surface(self,_,color):
        self._surface_color.rgba=color

    def _animate_surface(self,*_):
        active=self.state=='down' or self.hovered
        target=theme.rgba(COLORS['primary_light'] if active else COLORS['surface'])
        self._outline_color.rgba=theme.rgba(COLORS['primary'] if active else COLORS['border'])
        Animation.cancel_all(self,'_surface_rgba')
        Animation(_surface_rgba=target,duration=theme.ANIM_FAST,t='out_quad').start(self)


def styled_spinner(values, initial, width=None):
    """Build a Spinner styled to match the rest of the app, with a
    working Persian dropdown list and a soft open animation. Use this
    everywhere instead of a bare kivy.uix.spinner.Spinner.

    Pass `width` for a fixed-width dropdown (e.g. next to a label in a
    row). Leave it out for a dropdown that should stretch to fill
    whatever column/box it's placed in (e.g. a form field)."""
    size_kwargs = (
        {"size_hint": (None, None), "size": (width, 44)}
        if width is not None
        else {"size_hint": (1, None), "height": 44}
    )
    return _StyledSpinner(
        text=initial,
        values=values,
        font_name=theme.APP_FONT_NAME,
        font_size=FONT_SIZE["body"],
        background_normal="",
        background_down="",
        background_color=theme.rgba(COLORS["background"]),
        color=theme.rgba(COLORS["text_primary"]),
        option_cls=_StyledSpinnerOption,
        dropdown_cls=_AnimatedDropDown,
        **size_kwargs,
    )
