"""UI state that resmon-lite remembers for itself (pin, opacity, position).

Deliberately separate from ``config.toml``: that file is authored by the user
and may contain comments we must not clobber, whereas this one is machine-owned
and rewritten whenever the overlay moves or changes opacity.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields


@dataclass
class UIState:
    pinned: bool = False
    # Alpha of the overlay background: 1.0 = solid, 0.2 = barely there.
    opacity: float | None = None
    # Overlay top-left corner; None means "place it automatically".
    x: int | None = None
    y: int | None = None


def state_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".config", "resmon-lite", "state.json")


def load_state(path: str | None = None) -> UIState:
    """Read saved UI state, ignoring anything unrecognised or malformed."""
    path = path or state_path()
    try:
        with open(path, "rb") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return UIState()
    if not isinstance(data, dict):
        return UIState()
    valid = {f.name for f in fields(UIState)}
    return UIState(**{k: v for k, v in data.items() if k in valid})


def save_state(state: UIState, path: str | None = None) -> None:
    """Write UI state atomically (temp file + rename), never raising."""
    path = path or state_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(state), f, indent=1, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
    except OSError:
        pass  # read-only home, full disk, ...: not worth killing the tray for
