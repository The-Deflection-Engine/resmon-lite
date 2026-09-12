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
- Python 3.11+ with PyGObject (`python3-gi`, standard on Ubuntu) and
  `python3-gi-cairo`. The latter is needed for the pinned overlay's translucent
  background — without it, GTK's `draw` signal can't hand Python a
  `cairo.Context` (fails silently with a `TypeError` in stderr), so the panel
  still shows but its opacity control does nothing.
- AMD GPUs (amdgpu driver). GPU utilisation needs the kernel parameter
  `amdgpu.gpu_busy_percent=1`; if it isn't set, the util column shows `n/a`
  and everything else still works.
- NVIDIA GPUs need the proprietary driver plus the optional `nvidia` extra
  (`pip install "resmon-lite[nvidia] @ git+https://github.com/The-Deflection-Engine/resmon-lite.git@v0.2.0"`),
  which pulls in `nvidia-ml-py` for NVML. Without it, or without the extra
  installed, NVIDIA GPUs are just skipped — everything else still works.

Only required Python dependency is PyGObject; metrics come straight from
`/proc`, sysfs and (for NVIDIA) NVML, with no subprocesses spawned per poll.

## Run

```sh
./resmon-lite            # run from this checkout (no install needed)
./resmon-lite --print    # print one reading to stdout and exit
```

Or install it as a regular command, e.g. straight from GitHub:

```sh
pip install --user git+https://github.com/The-Deflection-Engine/resmon-lite.git@v0.2.0
resmon-lite
```

`pip install --user` puts the command in `~/.local/bin`, which needs to be
on your `PATH` (pip warns if it isn't) — add `export PATH="$HOME/.local/bin:$PATH"`
to your shell rc file if `resmon-lite` isn't found after installing.

(`pipx install git+https://github.com/The-Deflection-Engine/resmon-lite.git@v0.2.0`
works the same way, in its own venv.) For
hacking on a local checkout: `pip install --user -e .`.

## Ubuntu package (PPA)

The easiest way to install on Ubuntu, and to get updates automatically:

```sh
sudo add-apt-repository ppa:euan-webster/resmon-lite
sudo apt update
sudo apt install resmon-lite
```

This pulls in all the system dependencies (PyGObject, the AppIndicator and
cairo GObject-introspection bindings) via `apt` automatically, installs the
`resmon-lite` command to `/usr/bin`, and the launcher `.desktop` file to
`/usr/share/applications` (so it shows up in the GNOME app grid too).
NVIDIA support still needs the `nvidia-ml-py` pip extra separately — see
[Requirements](#requirements) — since it isn't packaged for Debian/Ubuntu.

### Building the .deb yourself

If you'd rather not add the PPA, the same package builds locally:

```sh
sudo apt build-dep .            # or: sudo apt install debhelper-compat dh-python \
                                 #     pybuild-plugin-pyproject python3-all python3-setuptools
dpkg-buildpackage -us -uc -b
sudo apt install ../resmon-lite_*_all.deb
```

## Autostart with the session

If you installed via the PPA or the `.deb`, the launcher and `.desktop` file
are already on your system, so autostart is just:

```sh
mkdir -p ~/.config/autostart
cp /usr/share/applications/resmon-lite.desktop ~/.config/autostart/
```

Running from a checkout instead (no install)? Point the same autostart
mechanism at the checkout's own copies:

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

## ESP32 display

An optional second output: a 240x240 circular IPS panel (GC9A01) on an
ESP32, driven over Wi-Fi (UDP) or USB (serial). Each GPU's utilisation
and VRAM are shown as concentric dials, plus a CPU/RAM page; buttons
switch pages and change display settings. The tray app keeps working
exactly as today — the ESP32 is an additional, non-fatal output (an
absent ESP32 costs at most a few throttled stderr lines).

| GPU page | GPU page (idle) | CPU/RAM page | Settings | Link lost |
|---|---|---|---|---|
| ![GPU busy](esp32/mockups/gpu-page-busy.png) | ![GPU idle](esp32/mockups/gpu-page-idle.png) | ![CPU/RAM](esp32/mockups/cpu-ram-page.png) | ![Settings](esp32/mockups/settings-page.png) | ![Link lost](esp32/mockups/link-lost.png) |

Hardware, wiring, buttons and build/flash instructions: see
[`esp32/README.md`](esp32/README.md) (firmware in `esp32/`, built with
PlatformIO — Arduino + LovyanGFX + ArduinoJson).

Wi-Fi is configured via the `Resmon` setup network on first boot:
connect to it, open http://192.168.4.1, save the home credentials —
the device reboots and joins the network. The `Resmon` network stays
available for later changes.

New config keys (all optional, see [`config.example.toml`](config.example.toml)):

| Key | Default | Meaning |

|---|---|---|
| `remote_enabled` | `false` | send telemetry to the ESP32 |
| `remote_transport` | `"wifi"` | `"wifi"` (UDP) or `"usb"` (serial) |
| `remote_host` | `"127.0.0.1"` | ESP32 IP, or `"resmon.local"` (mDNS) |
| `remote_port` | `8266` | UDP port |
| `remote_usb_device` | `"/dev/ttyUSB0"` | serial port for `"usb"` |
| `remote_usb_baud` | `115200` | serial baud rate |

Display settings (backlight, colour mode, auto-advance) are changed on
the ESP32 itself — with the panel's buttons or the web settings page
(http://192.168.4.1 on the `Resmon` network) — and stored in its flash
(NVS); they are not changed from the host.
