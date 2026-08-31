"""Tray application: builds and updates the AppIndicator menu."""
from __future__ import annotations

import os
from dataclasses import dataclass

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import GLib, Gtk, AyatanaAppIndicator3 as AppIndicator  # noqa: E402

from . import gpu as gpumod  # noqa: E402
from . import sensors  # noqa: E402
from .config import Config  # noqa: E402
from .icon import IconWriter  # noqa: E402
from .overlay import OPACITY_LEVELS, Overlay, _nearest_level  # noqa: E402
from .state import UIState, load_state, save_state  # noqa: E402
from .status import Status, classify, colored, mono  # noqa: E402

APP_ID = "resmon-lite"


def _cell_pct(v: float | None) -> str:
    return f"{v:3.0f}%" if v is not None else "n/a"


def _cell_temp(v: float | None) -> str:
    return f"{v:3.0f}\u00b0C" if v is not None else "n/a"


def _cell_watts(v: float | None) -> str:
    return f"{v:4.0f} W" if v is not None else "n/a"


def _cell_vram(used: int | None, total: int | None) -> str:
    if used is None or total is None:
        return "n/a"
    return f"{used / 2**30:5.1f}/{total / 2**30:5.1f} GiB"


@dataclass
class Sample:
    """One poll's worth of readings, shared by the menu, overlay and icon."""

    cpu_pct: float | None
    cpu_temp: float | None
    ram_used: int | None
    ram_total: int | None
    gpus: list[gpumod.Gpu]

    @property
    def ram_percent(self) -> float | None:
        if self.ram_used is None or not self.ram_total:
            return None
        return 100.0 * self.ram_used / self.ram_total


class ResmonLite:
    def __init__(self, config: Config, state: UIState | None = None) -> None:
        self.config = config
        self.state = state or load_state()
        self.overlay: Overlay | None = None
        self._pin_item: Gtk.CheckMenuItem | None = None
        self._opacity_items: list[tuple[float, Gtk.RadioMenuItem]] = []
        self._auto_pin = self.state.pinned
        self.colors = {
            Status.OK: config.color_ok,
            Status.WARN: config.color_warn,
            Status.CRIT: config.color_crit,
        }
        self.cpu_reader = sensors.CpuReader()
        self.gpu_names = gpumod.device_names()  # one-time lspci lookup

        self.icon_path = os.path.join(GLib.get_user_cache_dir(), "resmon-lite", "icon.png")
        self.icons = IconWriter(self.icon_path)
        self.icons.update([], self.colors)  # placeholder before first tick

        self.indicator = AppIndicator.Indicator.new(
            APP_ID, self.icon_path, AppIndicator.IndicatorStatus.ACTIVE
        )
        self.indicator.set_label("", APP_ID)
        # libayatana-appindicator does not publish the status passed to
        # Indicator.new(); without this the item stays "Passive" and GNOME
        # hides it from the top bar.
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self._labels: dict[str, Gtk.Label] = {}
        self._gpu_ids: tuple[int, ...] | None = None
        self._menu_ready = False  # suppress item signals during _build_menu
        self._build_menu([])

    # -- menu ---------------------------------------------------------------

    def _build_menu(self, gpus: list[gpumod.Gpu]) -> None:
        menu = Gtk.Menu()
        self._labels = {}
        self._menu_ready = False  # set_active() below must not fire handlers

        def row(key: str, markup: str = "") -> None:
            item = Gtk.MenuItem()
            lbl = Gtk.Label()
            if markup:
                lbl.set_markup(markup)
            lbl.set_xalign(0.0)
            item.add(lbl)
            menu.append(item)
            self._labels[key] = lbl

        row("cpu")
        row("ram")
        menu.append(Gtk.SeparatorMenuItem())
        if not gpus:
            row("no_gpu", "<i>No AMD GPU detected</i>")
        for g in gpus:
            name = GLib.markup_escape_text(g.name)
            row(f"gpu{g.index}_head", f"<b>GPU {g.index} \u00b7 {name}</b>")
            row(f"gpu{g.index}_vals")
        menu.append(Gtk.SeparatorMenuItem())

        # Pin the same numbers into a translucent on-screen window.
        self._pin_item = Gtk.CheckMenuItem(label="Pin to screen")
        self._pin_item.set_active(self.state.pinned)
        self._pin_item.connect("toggled", self._on_pin_toggled)
        menu.append(self._pin_item)

        opacity_item = Gtk.MenuItem(label="Overlay opacity")
        submenu = Gtk.Menu()
        current = _nearest_level(self._overlay_opacity())
        self._opacity_items = []
        group: Gtk.RadioMenuItem | None = None
        for level in OPACITY_LEVELS:
            item = Gtk.RadioMenuItem.new_with_label_from_widget(group, f"{level * 100:.0f}%")
            group = item
            item.connect("toggled", self._on_opacity_toggled, level)
            if abs(level - current) < 1e-9:
                item.set_active(True)
            submenu.append(item)
            self._opacity_items.append((level, item))
        opacity_item.set_submenu(submenu)
        menu.append(opacity_item)

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda *_: Gtk.main_quit())
        menu.append(quit_item)
        menu.show_all()
        self.indicator.set_menu(menu)
        self._gpu_ids = tuple(g.index for g in gpus)
        self._menu_ready = True

    def _sync_menu(self, gpus: list[gpumod.Gpu]) -> list[gpumod.Gpu]:
        if tuple(g.index for g in gpus) != self._gpu_ids:
            # GPU set changed (new card / driver reload): refresh names.
            self.gpu_names = gpumod.device_names()
            gpus = gpumod.read_gpus(self.gpu_names)
            self._build_menu(gpus)
        return gpus

    # -- pinned overlay -----------------------------------------------------

    def _overlay_opacity(self) -> float:
        if self.state.opacity is not None:
            return self.state.opacity
        return self.config.overlay_opacity

    def _ensure_overlay(self) -> Overlay:
        if self.overlay is None:
            pos = (
                (self.state.x, self.state.y)
                if self.state.x is not None and self.state.y is not None
                else None
            )
            self.overlay = Overlay(
                opacity=self._overlay_opacity(),
                font_pt=self.config.overlay_font_pt,
                text_color=self.config.overlay_text_color,
                pos=pos,
                on_close=self.unpin,
                on_opacity_change=self._on_overlay_opacity,
                on_move=self._on_overlay_move,
            )
        return self.overlay

    def _on_pin_toggled(self, item: Gtk.CheckMenuItem) -> None:
        if not self._menu_ready:
            return  # set_active() during menu construction is not a user click
        if item.get_active():
            self.state.pinned = True
            self._ensure_overlay().show()
        else:
            self.state.pinned = False
            if self.overlay is not None:
                self.overlay.hide()
        save_state(self.state)

    def unpin(self) -> None:
        """Close the overlay (right-click on it, or the window manager)."""
        self.state.pinned = False
        if self.overlay is not None:
            self.overlay.hide()
        if self._pin_item is not None and self._pin_item.get_active():
            self._pin_item.set_active(False)  # -> _on_pin_toggled, idempotent
        save_state(self.state)

    def _on_overlay_opacity(self, level: float) -> None:
        """Scroll wheel on the overlay: keep the menu's radios in step."""
        self.state.opacity = level
        for item_level, item in self._opacity_items:
            active = abs(item_level - level) < 1e-9
            if item.get_active() != active:
                item.set_active(active)  # -> _on_opacity_toggled, same value
        save_state(self.state)

    def _on_opacity_toggled(self, item: Gtk.RadioMenuItem, level: float) -> None:
        if not self._menu_ready:
            return  # set_active() during menu construction is not a user click
        if not item.get_active():
            return
        self.state.opacity = level
        if self.overlay is not None:
            self.overlay.set_opacity(level, notify=False)
        save_state(self.state)

    def _on_overlay_move(self, x: int, y: int) -> None:
        self.state.x, self.state.y = int(x), int(y)
        save_state(self.state)

    # -- polling ------------------------------------------------------------

    def _read(self) -> Sample:
        """Poll every metric source once, rebuilding the menu if GPUs changed."""
        cpu_pct = self.cpu_reader.read_percent()
        cpu_temp = sensors.read_cpu_temp_c()
        ram_used, ram_total = sensors.read_ram()
        gpus = self._sync_menu(gpumod.read_gpus(self.gpu_names))
        return Sample(
            cpu_pct=cpu_pct,
            cpu_temp=cpu_temp,
            ram_used=ram_used,
            ram_total=ram_total,
            gpus=gpus,
        )

    def _span(self, text: str, value: float | None, warn: float, crit: float) -> str:
        """Wrap a preformatted cell in its status colour."""
        return colored(text, classify(value, warn, crit), self.colors)

    def _rows_for(self, s: Sample) -> list[tuple[str, str, bool]]:
        """The (key, pango markup, is_header) rows shown in the tray menu.

        The same rows are mirrored to the pinned overlay, so both views are
        rendered from one place.
        """
        cfg = self.config
        rows: list[tuple[str, str, bool]] = [
            (
                "cpu",
                mono(
                    f"CPU   "
                    f"{self._span(_cell_pct(s.cpu_pct), s.cpu_pct, cfg.util_warn, cfg.util_crit)}  "
                    f"{self._span(_cell_temp(s.cpu_temp), s.cpu_temp, cfg.temp_warn, cfg.temp_crit)}"
                ),
                False,
            ),
            (
                "ram",
                mono(
                    f"RAM   "
                    f"{self._span(_cell_vram(s.ram_used, s.ram_total), s.ram_percent, cfg.util_warn, cfg.util_crit)}"
                ),
                False,
            ),
        ]
        for g in s.gpus:
            name = GLib.markup_escape_text(g.name)
            rows.append((f"gpu{g.index}_head", f"<b>GPU {g.index} \u00b7 {name}</b>", True))
            rows.append(
                (
                    f"gpu{g.index}_vals",
                    mono(
                        f"      "
                        f"{self._span(_cell_pct(g.busy_percent), g.busy_percent, cfg.util_warn, cfg.util_crit)}  "
                        f"{self._span(_cell_vram(g.vram_used, g.vram_total), g.vram_percent, cfg.util_warn, cfg.util_crit)}  "
                        f"{colored(_cell_watts(g.power_w), Status.OK, self.colors)}  "
                        f"{self._span(_cell_temp(g.temp_c), g.temp_c, cfg.temp_warn, cfg.temp_crit)}"
                    ),
                    False,
                )
            )
        return rows

    def _icon_bars_and_tip(self, s: Sample) -> tuple[list[tuple[float, Status]], list[str]]:
        """Tray icon bar heights/statuses and tooltip text for one sample."""
        cfg = self.config
        bars: list[tuple[float, Status]] = []
        tip: list[str] = []

        def add(percent: float, label: str) -> None:
            bars.append((percent / 100.0, classify(percent, cfg.util_warn, cfg.util_crit)))
            tip.append(label)

        if s.cpu_pct is not None:
            add(s.cpu_pct, f"CPU {s.cpu_pct:.0f}%")
        if s.ram_percent is not None:
            add(s.ram_percent, f"RAM {s.ram_used / 2**30:.0f}/{s.ram_total / 2**30:.0f} GiB")
        for g in s.gpus:
            if g.busy_percent is not None:
                add(g.busy_percent, f"GPU{g.index} {g.busy_percent:.0f}%")
            if g.vram_percent is not None:
                add(g.vram_percent, f"VRAM{g.index} {g.vram_percent:.0f}%")
        return bars, tip

    def tick(self) -> bool:
        try:
            return self._tick()
        except Exception:
            # A failed poll must not stop the tray for good: log and keep ticking.
            import traceback

            traceback.print_exc()
            log = os.path.join(os.path.dirname(self.icon_path), "error.log")
            try:
                with open(log, "a") as f:
                    f.write("\n" + traceback.format_exc())
            except OSError:
                pass
            return True

    def _tick(self) -> bool:
        sample = self._read()
        rows = self._rows_for(sample)

        for key, markup, _header in rows:
            label = self._labels.get(key)
            if label is not None:
                label.set_markup(markup)
        overlay_rows = [(markup, header) for _key, markup, header in rows]
        if self.overlay is not None:
            self.overlay.update(overlay_rows)

        bars, tip = self._icon_bars_and_tip(sample)
        self.indicator.set_title(" \u00b7 ".join(tip) if tip else "resmon-lite")
        new_icon = self.icons.update(bars, self.colors)
        if new_icon is not None:
            self.indicator.set_icon(new_icon)

        if self._auto_pin:
            # Re-open the overlay from the previous session, once it has data.
            self._auto_pin = False
            overlay = self._ensure_overlay()
            overlay.update(overlay_rows)
            overlay.show()
        return True
