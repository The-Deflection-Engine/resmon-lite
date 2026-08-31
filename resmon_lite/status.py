"""Status classification and Pango markup helpers."""
from __future__ import annotations

from enum import Enum


class Status(Enum):
    OK = "ok"
    WARN = "warn"
    CRIT = "crit"


def classify(value: float | None, warn: float, crit: float) -> Status:
    """Map a numeric value to a status using warn/crit thresholds."""
    if value is None:
        return Status.OK
    if value >= crit:
        return Status.CRIT
    if value >= warn:
        return Status.WARN
    return Status.OK


def colored(text: str, status: Status, colors: dict[Status, str]) -> str:
    """Wrap visible text in a Pango foreground-colour span."""
    return f'<span foreground="{colors.get(status, "#ffffff")}">{text}</span>'


def mono(text: str) -> str:
    """Wrap text in a monospace Pango span (for aligned metric rows)."""
    return f'<span font_family="monospace">{text}</span>'


def gib(nbytes: float | None) -> float | None:
    if nbytes is None:
        return None
    return nbytes / 2**30
