"""Entry point: `python3 -m resmon_lite` or the `resmon-lite` launcher script."""
from __future__ import annotations

import argparse
import sys


def _print_once() -> None:
    """Print a single reading to stdout (for debugging / cron-style use)."""
    import time

    from . import gpu, sensors

    reader = sensors.CpuReader()
    time.sleep(0.5)  # prime so the CPU % is a real value
    cpu_pct = reader.read_percent()
    cpu_temp = sensors.read_cpu_temp_c()
    ram_used, ram_total = sensors.read_ram()
    gpus = gpu.read_gpus()

    def f(v, fmt):
        return format(v, fmt) if v is not None else "n/a"

    print(f"CPU   {f(cpu_pct, '3.0f')}%  {f(cpu_temp, '3.0f')}\u00b0C")
    if ram_used is not None and ram_total:
        print(f"RAM   {ram_used / 2**30:5.1f}/{ram_total / 2**30:5.1f} GiB")
    for g in gpus:
        vram = f"{g.vram_used / 2**30:5.1f}/{g.vram_total / 2**30:5.1f} GiB" if g.vram_used is not None and g.vram_total else "n/a"
        print(
            f"GPU {g.index}  {g.name}: "
            f"{f(g.busy_percent, '3.0f')}%  {vram}  {f(g.power_w, '4.0f')} W  {f(g.temp_c, '3.0f')}\u00b0C"
        )
    if not gpus:
        print("GPU   no AMD GPU detected")


def _acquire_single_instance():
    """Claim a well-known session-bus name so only one resmon-lite runs at a time.

    Returns the bus connection if we are the primary owner (i.e. the sole
    instance), or None if another instance already owns the name. Owning a
    D-Bus name is ideal for a tray daemon: it is released automatically when
    the process exits, so there is no stale lockfile to clean up.
    """
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        result = bus.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "RequestName",
            GLib.Variant("(su)", ("org.resmonlite.App", Gio.BusNameOwnerFlags.DO_NOT_QUEUE)),
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
        vals = result.unpack()  # (reply,) or (reply, name) depending on GLib build
        reply = vals[0] if vals else 0
        # DBUS_REQUEST_NAME_REPLY_PRIMARY_OWNER == 1
        if reply == 1:
            return bus  # hold the connection so the name stays owned
    except Exception:
        pass  # no session bus / unexpected error: don't block startup
    return None


def _prepare_display_environment() -> None:
    """Prefer X11/XWayland on Wayland sessions.

    The pinned overlay wants stacking control (stay above other windows) and a
    fixed corner. GNOME Shell speaks no layer-shell protocol, so on Wayland we
    go through XWayland, where Mutter honours _NET_WM_STATE_ABOVE and moves.
    Set GDK_BACKEND=wayland to opt out and accept a plain, placeable-by-you window.
    """
    import os

    if os.environ.get("XDG_SESSION_TYPE") == "wayland":
        os.environ.setdefault("GDK_BACKEND", "x11")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="resmon-lite", description="Lightweight CPU/RAM/GPU stats in the system tray."
    )
    parser.add_argument("--print", action="store_true", help="print one reading to stdout and exit")
    args = parser.parse_args()

    from .config import load_config

    config = load_config()

    if args.print:
        _print_once()
        return

    _prepare_display_environment()

    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import GLib, Gtk

    # Refuse to start a second copy: multiple instances each add a tray icon,
    # create their own overlay, and clobber the shared state file.
    bus = _acquire_single_instance()
    if bus is None:
        print("resmon-lite is already running; not starting another instance.", file=sys.stderr)
        return

    from .app import ResmonLite

    app = ResmonLite(config)
    GLib.timeout_add(int(config.poll_interval * 1000), app.tick)
    Gtk.main()


if __name__ == "__main__":
    main()
