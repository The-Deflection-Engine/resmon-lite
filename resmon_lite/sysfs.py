"""Small shared helpers for reading kernel files (/proc, sysfs)."""
from __future__ import annotations


def read_int(path: str) -> int | None:
    """Read a single integer from a kernel file, or None if unavailable."""
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None
