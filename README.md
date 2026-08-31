# resmon-lite

A small, lightweight system-stats app for the Ubuntu taskbar (system tray).
Shows CPU %, RAM used/total, and per-GPU utilisation, VRAM, power draw and
temperature — colour-coded as values climb.

```
CPU     12%   56°C
RAM    19.3/ 64.0 GiB
───────────────────
GPU 0 · Radeon AI PRO R9700
       97%   30.5/ 34.2 GiB    66 W   73°C
GPU 1 · AMD Raphael iGPU
        0%    0.0/  0.5 GiB    47 W   57°C
───────────────────
Quit
```

The tray icon is a tiny level meter — one bar per metric (CPU, RAM, one per
GPU) with a dimmed track and a coloured fill from the bottom — that mirrors
the same colours, so you can see trouble at a glance without opening the menu.

## Status colours

| Range | Colour |
|---|---|
| < 50% utilisation (or < 75 °C) | green |
| 50–74% utilisation (or 75–89 °C) | yellow |
| ≥ 75% utilisation (or ≥ 90 °C) | red |

All thresholds and colours are configurable — see below.

## Pin to screen

The tray menu has a **Pin to screen** toggle that opens the same stats as a
small always-on-top, borderless, translucent panel you can leave on your
desktop:

- **Drag** it anywhere; the position is remembered across restarts.
- **Scroll wheel** over the panel adjusts its opacity (the tray menu's
  opacity radio buttons stay in sync).
- **Right-click** the panel to unpin it.
- If resmon-lite quits while pinned, it re-pins at the same spot on next start.

Starting opacity, text size and text colour are configurable — see below.

## Requirements

- Ubuntu 22.04+ with GNOME (Wayland or X11) — uses the Ayatana AppIndicator,
  already present on stock Ubuntu (`gir1.2-ayatanaappindicator3-0.1`).
- Python 3.11+ with PyGObject (`python3-gi`, standard on Ubuntu).
- AMD GPUs (amdgpu driver). GPU utilisation needs the kernel parameter
  `amdgpu.gpu_busy_percent=1`; if it isn't set, the util column shows `n/a`
  and everything else still works.
- NVIDIA GPUs need the proprietary driver plus the optional `nvidia` extra
  (`pip install resmon-lite[nvidia]`), which pulls in `nvidia-ml-py` for
  NVML. Without it, or without the extra installed, NVIDIA GPUs are just
  skipped — everything else still works.

Only required Python dependency is PyGObject; metrics come straight from
`/proc`, sysfs and (for NVIDIA) NVML, with no subprocesses spawned per poll.

## Run

```sh
./resmon-lite            # run from this checkout (no install needed)
./resmon-lite --print    # print one reading to stdout and exit
```

Or install it as a regular command, e.g. straight from GitHub:

```sh
pip install --user git+https://github.com/The-Deflection-Engine/resmon-lite.git
resmon-lite
```

`pip install --user` puts the command in `~/.local/bin`, which needs to be
on your `PATH` (pip warns if it isn't) — add `export PATH="$HOME/.local/bin:$PATH"`
to your shell rc file if `resmon-lite` isn't found after installing.

(`pipx install git+https://...` works the same way, in its own venv.) For
hacking on a local checkout: `pip install --user -e .`.

## Autostart with the session

```sh
ln -s "$PWD/resmon-lite" ~/.local/bin/resmon-lite        # launcher on PATH
cp resmon-lite.desktop ~/.local/share/applications/
mkdir -p ~/.config/autostart
ln -s "$PWD/resmon-lite.desktop" ~/.config/autostart/
```

## Configuration

Optional file at `~/.config/resmon-lite/config.toml` (see
[`config.example.toml`](config.example.toml)). Every key is optional:

| Key | Default | Meaning |
|---|---|---|
| `poll_interval` | `2.0` | seconds between updates |
| `util_warn` / `util_crit` | `50` / `75` | % thresholds (CPU, GPU, VRAM) for yellow / red |
| `temp_warn` / `temp_crit` | `75` / `90` | °C thresholds for yellow / red |
| `color_ok` / `color_warn` / `color_crit` | green/amber/red | hex colours |
| `overlay_opacity` | `0.7` | starting background alpha of the pinned overlay (scroll wheel overrides) |
| `overlay_font_pt` | `12.0` | text size in the pinned overlay, points |
| `overlay_text_color` | `#ffffff` | base text colour of the pinned overlay (hex); status colours still apply to values |

## Notes & design

- **GPU backend**: AMD via amdgpu sysfs (`/sys/class/drm/cardN/device/…`,
  hwmon for temp/power) and NVIDIA via NVML (optional `nvidia-ml-py`
  dependency). Every GPU present is listed automatically, so mixed AMD +
  NVIDIA systems and new cards "just work". AMD names come from `lspci`
  (looked up once at startup, with a small built-in map for very new cards);
  NVIDIA names come straight from NVML.
- **CPU temperature**: read from the `k10temp` / `coretemp` hwmon chip.
- **RAM**: `MemTotal − MemAvailable` from `/proc/meminfo`.
- **Icon**: drawn with Cairo to a PNG in `~/.cache/resmon-lite/`, rewritten only
  when values actually change.
- **Single instance**: resmon-lite owns the D-Bus name `org.resmonlite.App` for
  the session; starting a second copy prints a notice and exits. The name is
  released automatically on crash, so there are no stale lock files.
