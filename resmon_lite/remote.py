"""ESP32 display output: sends each Sample as JSON over UDP or serial.

Fire-and-forget by design: the tray must keep working when the ESP32 is
absent, so send() never raises. Failures print to stderr at most once
per 60 s.
"""
from __future__ import annotations

import json
import socket
import sys
import time
from typing import TYPE_CHECKING

import serial

from .config import Config

if TYPE_CHECKING:  # runtime-avoidable: app.py imports this module
    from .app import Sample

_MAX_GPUS = 4  # protocol v1 carries at most four (firmware array size)


class Remote:
    """Sends each Sample to the ESP32 over UDP ("wifi") or serial ("usb").

    Construction never fails: a disabled config is a no-op, and the
    transport handle is opened lazily on the first send, so an absent
    ESP32 never blocks app startup.
    """

    def __init__(self, config: Config) -> None:
        self._cfg = config
        self._sock: socket.socket | None = None
        self._ser: serial.Serial | None = None
        self._down = False
        self._last_log = 0.0
        self._on = config.remote_enabled
        if not self._on:
            return
        # wifi: socket is created lazily on the first send.
        # usb: serial port is opened lazily on the first send.

    def send(self, sample: Sample) -> None:
        """Send one sample; never raises (the tray must keep ticking)."""
        if not self._on:
            return
        try:
            payload = self._encode(sample)
            if self._cfg.remote_transport == "usb":
                self._send_usb(payload)
            else:
                self._send_udp(payload)
        except Exception:
            self._log(f"ESP32 {self._cfg.remote_transport} link down (retrying)")

    # -- transports -----------------------------------------------------------

    def _send_udp(self, payload: bytes) -> None:
        if self._sock is None:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # UDP is fire-and-forget: sendto() cannot fail on an absent peer.
        self._sock.sendto(payload, (self._cfg.remote_host, self._cfg.remote_port))

    def _send_usb(self, payload: bytes) -> None:
        if self._ser is None or self._down:
            # First send, or recovering from a previous failure (e.g. the
            # ESP32 was unplugged and replugged): (re)open the port.
            self._close_usb()
            self._open_usb()
            if self._down:
                return
        try:
            self._ser.write(payload + b"\n")
        except (serial.SerialException, OSError):
            # Write failed (e.g. unplugged mid-send): close, reopen and
            # retry once within this call; if that also fails, stay down
            # and wait for the next poll.
            self._close_usb()
            self._open_usb()
            if self._down:
                return
            try:
                self._ser.write(payload + b"\n")
            except (serial.SerialException, OSError):
                self._close_usb()
                self._down = True
                self._log("ESP32 usb link down (retrying)")

    def _open_usb(self) -> None:
        try:
            self._ser = serial.Serial(
                self._cfg.remote_usb_device, self._cfg.remote_usb_baud, timeout=0
            )
            self._down = False
        except (serial.SerialException, OSError):
            self._ser = None
            self._down = True
            self._log("ESP32 usb link down (retrying)")

    def _close_usb(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            except (serial.SerialException, OSError):
                pass
            self._ser = None

    # -- encoding -------------------------------------------------------------

    def _encode(self, sample: Sample) -> bytes:
        """Build the protocol v1 object (see esp32/README.md)."""
        obj = {
            "v": 1,
            "cpu": sample.cpu_pct,
            "ct": sample.cpu_temp,
            "ru": None if sample.ram_used is None else int(sample.ram_used // (1024 * 1024)),
            "rt": None if sample.ram_total is None else int(sample.ram_total // (1024 * 1024)),
            "g": [
                {
                    "n": g.name[:24],
                    "u": g.busy_percent,
                    "v": None if g.vram_used is None else int(g.vram_used // (1024 * 1024)),
                    "vt": None if g.vram_total is None else int(g.vram_total // (1024 * 1024)),
                    "t": g.temp_c,
                    "p": g.power_w,
                }
                for g in sample.gpus[:_MAX_GPUS]
            ],
        }
        return json.dumps(obj, separators=(",", ":")).encode()

    # -- logging --------------------------------------------------------------

    def _log(self, msg: str) -> None:
        """Print to stderr at most once per 60 s."""
        now = time.monotonic()
        if now - self._last_log >= 60.0:
            self._last_log = now
            print(f"resmon-lite: {msg}", file=sys.stderr)
