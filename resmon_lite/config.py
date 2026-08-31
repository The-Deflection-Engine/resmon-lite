"""Configuration: built-in defaults, optionally overridden by a TOML file."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, fields


@dataclass
class Config:
    # Polling interval in seconds.
    poll_interval: float = 2.0
    # Utilisation thresholds (percent) for CPU %, GPU % and VRAM %.
    util_warn: float = 50.0
    util_crit: float = 75.0
    # Temperature thresholds (degrees C) for CPU and GPU temps.
    temp_warn: float = 75.0
    temp_crit: float = 90.0
    # Status colours (hex).
    color_ok: str = "#81C784"
    color_warn: str = "#FFD54F"
    color_crit: str = "#EF5350"
    # Pinned overlay window ("Pin to screen"): starting background alpha, where
    # 1.0 is solid and 0.35 is barely there, the text size in points, and the
    # base text colour (hex). Once the user scrolls or picks a level these are
    # overridden by saved UI state.
    overlay_opacity: float = 0.7
    overlay_font_pt: float = 12.0
    overlay_text_color: str = "#ffffff"


def config_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".config", "resmon-lite", "config.toml")


def load_config(path: str | None = None) -> Config:
    """Load config from `path` (default: ~/.config/resmon-lite/config.toml).

    Unknown keys are ignored so the file stays forward-compatible.
    """
    path = path or config_path()
    data: dict = {}
    if os.path.exists(path):
        with open(path, "rb") as f:
            data = tomllib.load(f)
    valid = {f.name for f in fields(Config)}
    kwargs = {k: v for k, v in data.items() if k in valid}
    return Config(**kwargs)
