"""Pinned overlay: the menu's stats in a small, translucent on-screen window.

The tray menu can only be read one hover at a time, so "Pin to screen" opens
this window instead: borderless, always-on-top, and painted with an alpha
channel so whatever is behind it stays visible.

Interaction: drag anywhere to move it, scroll to change opacity, right-click to
unpin. Position/opacity are remembered between sessions (see ``state.py``).

Portability notes: transparency needs a compositing display server, which GNOME
always provides. ``keep_above`` and explicit positioning work on X11/XWayland;
on native Wayland a plain top-level cannot raise itself or pick its own corner
(that would need the layer-shell protocol), so there it behaves as an ordinary
window you can raise and move with the window manager.
"""
from __future__ import annotations

import math

try:  # pycairo is a PyGObject dependency in practice, but stay import-safe
    import cairo

    _OPERATOR_SOURCE = cairo.OPERATOR_SOURCE
except ImportError:  # pragma: no cover - cairo not wired up
    _OPERATOR_SOURCE = 1

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

# Opacity steps offered by the menu slider and stepped through with the scroll wheel.
OPACITY_LEVELS: tuple[float, ...] = tuple(round(i / 10, 1) for i in range(1, 11))

_CORNER = 10.0  # background corner radius, px
_BORDER_ALPHA = 0.16  # hairline around the panel, so it reads on pale pages
_HINT = "Drag to move \u00b7 scroll for opacity \u00b7 right-click to unpin"


def _nearest_level(value: float) -> float:
    return min(OPACITY_LEVELS, key=lambda lv: abs(lv - value))


class Overlay:
    """A borderless, translucent, always-on-top stats window."""

    def __init__(
        self,
        opacity: float = 0.7,
        font_pt: float = 12.0,
        text_color: str = "#ffffff",
        pos: tuple[int, int] | None = None,
        on_close=None,
        on_opacity_change=None,
        on_move=None,
    ) -> None:
        self.on_close = on_close
        self.on_opacity_change = on_opacity_change
        self.on_move = on_move
        self.opacity = _nearest_level(opacity)
        self.font_pt = min(24.0, max(6.0, float(font_pt)))
        self.text_color = text_color
        self._pos = pos
        self._target: tuple[int, int] | None = None
        self._labels: list[Gtk.Label] = []
        self._rows: list[tuple[str, bool]] = []
        self._pending: list[tuple[str, bool]] = []
        self._save_tag: int | None = None

        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.set_title("resmon-lite")
        self.window.set_role("resmon-lite-overlay")
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_skip_taskbar_hint(True)
        self.window.set_skip_pager_hint(True)
        self.window.set_keep_above(True)
        self.window.set_accept_focus(False)
        self.window.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.window.set_tooltip_text(_HINT)

        # Alpha background: an RGBA visual plus our own drawing, so the panel
        # can be translucent *and* rounded without a theme fighting us.
        screen = self.window.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            self.window.set_visual(visual)
        self.window.set_app_paintable(True)

        # NB: the provider/class must be attached to each *label*, not the
        # window -- GTK3 does not apply descendant selectors (".hud label")
        # from a window's style context to child widgets.
        self._css = Gtk.CssProvider()
        self._css.load_from_data(
            (
                f".resmonlite-hud {{ font-family: monospace; color: {self.text_color};"
                f" font-size: {self.font_pt:g}pt; }}"
            ).encode("utf-8")
        )

        self.box = self._make_box(spacing=0)
        self.window.add(self.box)

        self.window.connect("draw", self._on_draw)
        self.window.connect("map-event", lambda *_: GLib.idle_add(self._apply_target))
        self.window.connect("delete-event", self._on_delete_event)
        self.window.connect("button-press-event", self._on_button_press)
        self.window.connect("scroll-event", self._on_scroll)
        self.window.connect("configure-event", self._on_configure)
        self.window.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_MOTION_MASK
            | Gdk.EventMask.SCROLL_MASK
            | Gdk.EventMask.SMOOTH_SCROLL_MASK
        )

    # -- visibility ---------------------------------------------------------

    @property
    def visible(self) -> bool:
        return self.window.get_visible()

    def show(self) -> None:
        if not self.visible:
            self._place()
            self._render()  # paint the last known values before we appear
        self.window.show_all()
        # Re-assert stacking and position once mapped: the requested size is only
        # known after mapping, and window managers nudge unmanaged placements.
        self.window.set_keep_above(True)
        self._apply_target()

    def hide(self) -> None:
        if self.visible:
            self.window.hide()

    # -- content ------------------------------------------------------------

    def update(self, rows: list[tuple[str, bool]]) -> None:
        """Refresh the window. `rows` is (pango markup, is_header) per line.

        Values are always remembered, so a window that was pinned while hidden
        shows real numbers the moment it appears instead of an empty panel.
        """
        self._pending = rows
        if self.visible:
            self._render()

    def _render(self) -> None:
        rows = self._pending
        if not rows:
            return
        if [header for _, header in rows] != [header for _, header in self._rows]:
            self._rebuild(rows)
        else:
            for label, (markup, _) in zip(self._labels, rows):
                label.set_markup(markup)
        self.window.queue_draw()

    def _make_box(self, spacing: int) -> Gtk.Box:
        """Container for the stat rows, with the same padding everywhere."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(12)
        return box

    def _rebuild(self, rows: list[tuple[str, bool]]) -> None:
        self.box.destroy()
        self.box = self._make_box(spacing=2)
        self._labels = []
        first_header = True
        for markup, is_header in rows:
            if is_header and first_header:
                self.box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 4)
                first_header = False
            label = Gtk.Label()
            label.set_markup(markup)
            label.set_xalign(0.0)
            label.get_style_context().add_provider(
                self._css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            label.get_style_context().add_class("resmonlite-hud")
            self.box.pack_start(label, False, False, 0)
            self._labels.append(label)
        self.window.add(self.box)
        self.window.show_all()
        self._rows = list(rows)

    # -- opacity ------------------------------------------------------------

    def set_opacity(self, value: float, notify: bool = True) -> None:
        self.opacity = _nearest_level(value)
        self.window.queue_draw()
        if notify and self.on_opacity_change:
            self.on_opacity_change(self.opacity)

    def _step_opacity(self, direction: int) -> None:
        idx = OPACITY_LEVELS.index(self.opacity)
        last = len(OPACITY_LEVELS) - 1
        self.set_opacity(OPACITY_LEVELS[max(0, min(last, idx + direction))])

    # -- drawing ------------------------------------------------------------

    def _on_draw(self, widget, cr) -> bool:
        alloc = widget.get_allocation()
        w, h = alloc.width, alloc.height
        # Reset the surface to transparent first: with an app-paintable window
        # nothing else clears it, and without this, repeated draws (e.g. after
        # an opacity change) would accumulate alpha.
        # NB: OPERATOR_SOURCE, not OPERATOR_CLEAR -- under XWayland (rootless)
        # a CLEAR on an ARGB surface leaves the window completely invisible.
        cr.set_operator(_OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()

        r = min(_CORNER, w / 2, h / 2)
        cr.new_sub_path()
        cr.arc(w - r, r, r, -math.pi / 2, 0)
        cr.arc(w - r, h - r, r, 0, math.pi / 2)
        cr.arc(r, h - r, r, math.pi / 2, math.pi)
        cr.arc(r, r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()
        cr.set_source_rgba(0.06, 0.07, 0.09, self.opacity)
        cr.fill_preserve()
        cr.set_source_rgba(1.0, 1.0, 1.0, _BORDER_ALPHA)
        cr.set_line_width(1.0)
        cr.stroke()
        return False  # let the labels draw on top of our panel

    # -- signals ------------------------------------------------------------

    def _apply_target(self) -> bool:
        """Move to the wanted spot. Must happen *after* mapping: Mutter picks its
        own corner for a first-map request and ignores the pre-map hint."""
        if self._target is not None and self.visible:
            self.window.move(*self._target)
        return False

    def _on_delete_event(self, *_args) -> bool:
        if self.on_close:
            self.on_close()
        else:
            self.hide()
        return True  # hide only; the window is reused next time it's pinned

    def _on_button_press(self, _widget, event) -> bool:
        if event.button == 3:
            if self.on_close:
                self.on_close()
            else:
                self.hide()
            return True
        if event.button == 1:
            self.window.begin_move_drag(
                int(event.button), int(event.x_root), int(event.y_root), event.time
            )
            return True
        return False

    def _on_scroll(self, _widget, event) -> bool:
        direction = 0
        if hasattr(event, "get_scroll_deltas"):
            ok, _dx, dy = event.get_scroll_deltas()
            if ok:
                direction = -1 if dy < 0 else (1 if dy > 0 else 0)
        if direction == 0 and event.direction == Gdk.ScrollDirection.UP:
            direction = -1
        elif direction == 0 and event.direction == Gdk.ScrollDirection.DOWN:
            direction = 1
        if direction:
            self._step_opacity(direction)
            return True
        return False

    def _on_configure(self, *_args) -> bool:
        # Fires during mapping too; debounce so we do not thrash the state file.
        if self._save_tag is not None:
            GLib.source_remove(self._save_tag)
        self._save_tag = GLib.timeout_add(500, self._save_position)
        return False

    def _save_position(self) -> bool:
        self._save_tag = None
        if self.visible and self.on_move:
            self.on_move(*self.window.get_position())
        return False

    # -- placement ----------------------------------------------------------

    def _place(self) -> None:
        """Put the window where it was left, else top-left under the top bar."""
        display = Gdk.Display.get_default()
        monitor = None
        if display is not None:
            monitor = display.get_primary_monitor() or display.get_monitor(0)
        geo = monitor.get_geometry() if monitor else None
        width = max(self.window.get_preferred_width()[1], 1)
        height = max(self.window.get_preferred_height()[1], 1)
        if self._pos is not None:
            x, y = self._pos
        elif geo is not None:
            x, y = geo.x + 24, geo.y + 56
        else:
            x, y = 24, 56
        if geo is not None:  # keep it on screen if the layout changed
            x = max(geo.x, min(x, geo.x + geo.width - width - 8))
            y = max(geo.y, min(y, geo.y + geo.height - height - 8))
        self._target = (int(x), int(y))
        self.window.move(*self._target)
