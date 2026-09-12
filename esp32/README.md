# ESP32 + GC9A01 display

A 240x240 circular IPS panel (GC9A01, SPI) driven by an ESP32, showing
each GPU's utilisation and VRAM as concentric dials, plus a CPU/RAM page.
Buttons switch pages and change display settings. resmon-lite sends one
JSON object per poll (UDP, or serial at 115200 baud); the firmware keeps
the latest reading and shows a "LINK LOST" page if nothing arrives for
10 s.

Display mockups (240x240 PNGs):

| GPU page | GPU page (idle) | CPU/RAM page | Settings | Link lost |
|---|---|---|---|---|
| ![GPU busy](mockups/gpu-page-busy.png) | ![GPU idle](mockups/gpu-page-idle.png) | ![CPU/RAM](mockups/cpu-ram-page.png) | ![Settings](mockups/settings-page.png) | ![Link lost](mockups/link-lost.png) |

## Parts

- ESP32 (classic `esp32dev`; an ESP32-S3 works too — see USB notes below)
- GC9A01 240x240 circular IPS panel (SPI interface)
- 3 buttons (or 2 — see `TWO_BUTTONS` below)

## Wiring

All pins are in `src/config.h` — adjust that file to match your wiring.

A typical GC9A01 breakout is labelled 3V3, GND, SDA, SCK, CS, DC/RS,
RES, LED — power, MOSI, SCK, CS, DC, RST and backlight respectively.

| Function | Pin | Notes |
|---|---|---|
| MOSI | 23 | data out |
| SCK | 18 | clock |
| CS | 5 | chip select |
| DC | 17 | data/command |
| RST | 16 | reset |
| BL | 4 | backlight, 5 kHz PWM |
| B1 | 34 | next |
| B2 | 35 | previous |
| B3 | 39 | settings / exit |

Buttons are active-low: wire each between its pin and GND, with a 10 kΩ
pull-up to 3V3.

## Buttons

| Button | Main mode | Settings mode |
|---|---|---|
| B1 short | next page | move selection |
| B2 short | previous page | move selection |
| B3 short | open settings | change selected value |
| B3 long | — | exit settings |

Only two buttons? Set `TWO_BUTTONS 1` in `src/config.h`: B1 = next /
change, B2 short = previous / move selection, B2 long = open settings /
exit.

## Wi-Fi setup (web page)

Flash the firmware (no need to fill in `config.h` Wi-Fi first). Power
on; connect a phone or laptop to the open network `Resmon`. Open
http://192.168.4.1; enter the home SSID + password; optionally adjust
the display settings; Save. The device reboots and joins the network;
the `Resmon` network stays available at any time for later changes.
The board advertises the mDNS name `resmon.local` — point the host's
`remote_host` at it (or at the board's IP). `config.h`
`WIFI_SSID`/`WIFI_PASS` remain the factory fallback.

## Build & flash

### PlatformIO

```sh
cd esp32
pio run -t upload    # PlatformIO (pip install platformio)
```

### Arduino IDE (1.8.x)

One-time setup:

1. **Board support** — File → Preferences → add
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
   to *Additional URLs for board managers* → OK. Then Tools → Board →
   Boards Manager → refresh → search `esp32` → install **esp32 by
   Espressif Systems**.
2. **Libraries** — Sketch → Include Library → Manage Libraries →
   install **LovyanGFX** and **ArduinoJson** (WebServer ships with the
   core).

Every flash:

3. Create a folder (e.g. `Resmon/`), copy all of `esp32/src/` into
   it, and add an empty `Resmon.ino` file (the IDE requires a .ino
   entry point; the code lives in the .cpp files). Open the folder
   in the IDE.
4. Adjust the pin map in `config.h` to match your wiring.
5. Tools → Board → **ESP32 Dev Module** (an S3: **ESP32S3 Dev
   Module**).
6. Tools → Port → the board's serial port (`/dev/ttyUSB0` classic,
   `/dev/ttyACM0` S3).
7. Upload — the toolbar arrow, or File → Upload. If it fails, hold
   **BOOT**, press **EN/RESET**, release **BOOT**, and upload again.

No Wi-Fi is needed in `config.h` first — provision it via the `Resmon`
network (see above).

### USB

- **Classic ESP32**: any USB-serial bridge works; the port shows up as
  `/dev/ttyUSB0` (set `remote_usb_device` in the host config to match).
  If the port never appears, the bridge chip needs its Linux driver
  (`cp210x` or `ch341`).
- **ESP32-S3**: native USB CDC — change `board` in `platformio.ini` to
  `esp32s3` (the port then shows up as `/dev/ttyACM0`).

## Settings

Display settings — backlight, colour mode (RGB/white/green),
auto-advance (off/5 s/10 s/30 s) — are changed on the display and stored
in ESP32 NVS, so they persist across power cycles. Host settings
(thresholds, poll interval) are not changed from the display.
