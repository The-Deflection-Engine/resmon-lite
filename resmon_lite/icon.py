"""Tray icon: a small level meter, one bar per metric, coloured by status.

Each bar is a dimmed full-height track with a coloured fill rising from the
bottom, so the icon still reads as a bar chart at the ~22px tray size even
when values are near zero (a plain filled bar would shrink to a dot).

The PNG is encoded in pure Python (no cairo/PIL dependency): a 44x44 RGBA
image, rewritten only when values actually change.
"""
from __future__ import annotations

import os
import struct
import zlib
from typing import Sequence

from .status import Status

_SIZE = 44
_MARGIN_X = 4
_TOP = 4
_BOTTOM = 4
_BASELINE = 3  # ground line under the bars, px
_MIN_FILL = 4  # shortest coloured fill, px: status stays visible at ~0%
_MAX_BARS = 6
_NO_DATA_COLOR = (0x8F, 0x8F, 0x8F)
_BASE_COLOR = (0x5A, 0x5E, 0x64)
_PANEL_BG = (0x26, 0x28, 0x2B)  # typical dark top bar, used to dim tracks


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _mix(rgb: tuple[int, int, int], other: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    """Mix rgb towards other: t=0 keeps rgb, t=1 gives other."""
    return tuple(int(a + (b - a) * t) for a, b in zip(rgb, other))  # type: ignore[return-value]


def _brighten(rgb: tuple[int, int, int], amount: float = 0.3) -> tuple[int, int, int]:
    """Mix towards white: the top bar is dark and small, so the icon needs more punch."""
    return _mix(rgb, (255, 255, 255), amount)


def _track(color: tuple[int, int, int]) -> tuple[int, int, int]:
    """The unfilled part of a bar: its (brightened) status colour, dimmed hard."""
    return _mix(color, _PANEL_BG, 0.78)


def _encode_png(w: int, h: int, rgba: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + rgba[y * w * 4 : (y + 1) * w * 4] for y in range(h))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def _decode_png(png: bytes) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    """Decode the 8-bit RGBA PNGs this module produces (filters are all 0)."""
    import re

    m = re.search(b"IDAT", png)
    idat = b""
    for cm in re.finditer(b"\x49\x44\x41\x54", png):
        pos = cm.start()
        length = int.from_bytes(png[pos - 4 : pos], "big")
        idat += png[pos + 4 : pos + 4 + length]
    raw = zlib.decompress(idat)
    w = int.from_bytes(png[16:20], "big")
    h = int.from_bytes(png[20:24], "big")
    px: list[tuple[int, int, int, int]] = []
    for y in range(h):
        row = raw[y * (w * 4 + 1) + 1 : (y + 1) * (w * 4 + 1)]
        for x in range(w):
            o = x * 4
            px.append((row[o], row[o + 1], row[o + 2], row[o + 3]))
    return w, h, px


def render_png(bars: Sequence[tuple[float, Status | None]], colors: dict[Status, str]) -> bytes:
    """Render the level meter. Each bar is (fraction 0..1, status or None)."""
    size = _SIZE
    buf = bytearray(size * size * 4)  # transparent

    def rect(x0: int, y0: int, x1: int, y1: int, rgb: tuple[int, int, int]) -> None:
        for yy in range(y0, y1):
            row_off = yy * size * 4
            for xx in range(x0, x1):
                off = row_off + xx * 4
                buf[off : off + 3] = bytes(rgb)
                buf[off + 3] = 255

    bars = list(bars)[:_MAX_BARS] or [(0.0, None)] * 3
    n = len(bars)
    left, right = _MARGIN_X, size - _MARGIN_X
    top, bottom = _TOP, size - _BOTTOM
    baseline_top = bottom - _BASELINE
    plot_h = baseline_top - top
    step = (right - left) / n
    bar_w = max(2.0, step * 0.8)  # thick: the icon renders at ~22px in the panel

    for i, (frac, status) in enumerate(bars):
        frac = max(0.0, min(1.0, frac or 0.0))
        x0 = int(left + i * step + (step - bar_w) / 2)
        x1 = max(x0 + 1, min(right, int(x0 + bar_w)))
        if status is None:
            rect(x0, top, x1, bottom, _NO_DATA_COLOR)
            continue
        fill = _brighten(_hex_to_rgb(colors[status]))
        rect(x0, top, x1, baseline_top, _track(fill))  # dimmed track behind the fill
        fill_h = _MIN_FILL + frac * (plot_h - _MIN_FILL)
        rect(x0, int(baseline_top - fill_h), x1, baseline_top, fill)

    # Ground line under the bars: ties them together into one chart silhouette.
    rect(left, baseline_top, right, bottom, _BASE_COLOR)
    return _encode_png(size, size, bytes(buf))


class IconWriter:
    """Writes the icon PNG to disk, only when its content actually changes.

    Alternates between two file paths on each change: the shell only reloads
    an appindicator icon when the D-Bus icon property changes, so writing the
    same path over and over would keep showing the very first frame.
    """

    def __init__(self, path: str) -> None:
        base, ext = os.path.splitext(path)
        self._paths = (base + ext, base + "-2" + ext)
        self._idx = 0
        self.path = self._paths[0]
        self._key: tuple | None = None

    def update(self, bars: Sequence[tuple[float, Status | None]], colors: dict[Status, str]) -> str | None:
        """Render if the bars changed; return the new icon path, else None."""
        key = tuple((round(frac, 2), status.value if status else None) for frac, status in bars)
        if key == self._key:
            return None
        self._idx ^= 1
        self.path = self._paths[self._idx]
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "wb") as f:
            f.write(render_png(bars, colors))
        self._key = key
        return self.path
