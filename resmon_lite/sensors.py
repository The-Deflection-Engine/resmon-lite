"""CPU and RAM metrics from /proc and sysfs. No external processes."""
from __future__ import annotations

import glob
import os

from . import sysfs

_PROC_STAT = "/proc/stat"
_MEMINFO = "/proc/meminfo"
_HWMON_GLOB = "/sys/class/hwmon/hwmon*"
_CPU_CHIP_NAMES = {"k10temp", "coretemp", "cpu_thermal"}


def _read_cpu_times() -> tuple[int, int] | None:
    """Return (busy_jiffies, total_jiffies) for all CPUs combined."""
    try:
        with open(_PROC_STAT) as f:
            for line in f:
                if line.startswith("cpu "):
                    fields = [int(x) for x in line.split()[1:]]
                    idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
                    total = sum(fields)
                    return total - idle, total
    except (OSError, ValueError):
        pass
    return None


class CpuReader:
    """Computes CPU utilisation from /proc/stat deltas between reads.

    Prime the reader on construction so the first read_percent() call
    already returns a real value.
    """

    def __init__(self) -> None:
        self._prev = _read_cpu_times()

    def read_percent(self) -> float | None:
        cur = _read_cpu_times()
        prev, self._prev = self._prev, cur
        if prev is None or cur is None:
            return None
        prev_busy, prev_total = prev
        busy, total = cur
        dtotal = total - prev_total
        if dtotal <= 0:
            return None
        return max(0.0, min(100.0, 100.0 * (busy - prev_busy) / dtotal))


def read_ram() -> tuple[int | None, int | None]:
    """Return (used_bytes, total_bytes) from /proc/meminfo."""
    info: dict[str, int] = {}
    try:
        with open(_MEMINFO) as f:
            for line in f:
                key, _, rest = line.partition(":")
                parts = rest.split()
                if parts:
                    info[key] = int(parts[0]) * 1024
    except (OSError, ValueError):
        return None, None
    total = info.get("MemTotal")
    available = info.get("MemAvailable")
    if total is None or available is None:
        return None, None
    return max(0, total - available), total


def read_cpu_temp_c() -> float | None:
    """CPU package temperature from k10temp / coretemp / cpu_thermal hwmon."""
    for chip in sorted(glob.glob(_HWMON_GLOB)):
        try:
            with open(os.path.join(chip, "name")) as f:
                name = f.read().strip()
        except OSError:
            continue
        if name not in _CPU_CHIP_NAMES:
            continue
        raw = sysfs.read_int(os.path.join(chip, "temp1_input"))
        if raw is not None:
            return raw / 1000.0
    return None
