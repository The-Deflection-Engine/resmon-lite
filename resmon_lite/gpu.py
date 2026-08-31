"""AMD GPU metrics from sysfs (amdgpu). No external processes per poll.

Utilisation comes from /sys/class/drm/cardN/device/gpu_busy_percent, which
requires the amdgpu.gpu_busy_percent=1 kernel parameter. If it is missing,
the field shows "n/a".
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
from dataclasses import dataclass

from . import sysfs

_DRM_GLOB = "/sys/class/drm/card[0-9]*/device"
_AMD_VENDOR = "1002"

# Curated names that take precedence over lspci (which may be stale or
# ambiguous, e.g. the RX 9070 / 9070 XT / 9070 GRE share one PCI ID).
_KNOWN_NAMES = {
    "1002:7550": "Radeon RX 9070 XT",
    "1002:7551": "Radeon AI PRO R9700",
    "1002:164E": "AMD Raphael iGPU",
}


@dataclass
class Gpu:
    index: int
    name: str
    busy_percent: float | None = None
    vram_used: int | None = None
    vram_total: int | None = None
    power_w: float | None = None
    temp_c: float | None = None

    @property
    def vram_percent(self) -> float | None:
        if self.vram_used is None or not self.vram_total:
            return None
        return 100.0 * self.vram_used / self.vram_total


def _pci_id(dev_dir: str) -> str | None:
    try:
        with open(os.path.join(dev_dir, "uevent")) as f:
            for line in f:
                if line.startswith("PCI_ID="):
                    return line.strip().split("=", 1)[1]
    except OSError:
        pass
    return None


def _hwmon_dir(dev_dir: str) -> str | None:
    for d in sorted(glob.glob(os.path.join(dev_dir, "hwmon", "*"))):
        if os.path.isdir(d):
            return d
    return None


def _gpu_temp_c(hm: str | None) -> float | None:
    """GPU temperature: prefer junction, then edge, else first available."""
    if hm is None:
        return None
    sensors = sorted(glob.glob(os.path.join(hm, "temp*_input")))
    labels: dict[str, str] = {}
    for f in glob.glob(os.path.join(hm, "temp*_label")):
        try:
            with open(f) as fh:
                labels[os.path.basename(f)] = fh.read().strip().lower()
        except OSError:
            pass
    for wanted in ("junction", "edge"):
        for f in sensors:
            label_file = os.path.basename(f).replace("_input", "_label")
            if labels.get(label_file, "") == wanted:
                v = sysfs.read_int(f)
                if v is not None:
                    return v / 1000.0
    for f in sensors:
        v = sysfs.read_int(f)
        if v is not None:
            return v / 1000.0
    return None


def _gpu_power_w(hm: str | None) -> float | None:
    """GPU power draw in watts (PPT), from hwmon microwatts."""
    if hm is None:
        return None
    for name in ("power1_average", "power1_input"):
        v = sysfs.read_int(os.path.join(hm, name))
        if v is not None:
            return v / 1e6
    return None


def device_names() -> dict[str, str]:
    """Map 'vendor:device' PCI IDs to human product names (best effort).

    Runs lspci once; safe to cache for the lifetime of the app.
    """
    try:
        nmm = subprocess.run(["lspci", "-nmm"], capture_output=True, text=True, timeout=5)
        mm = subprocess.run(["lspci", "-mm"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return {}
    # -nmm: 03:00.0 "0300" "1002" "7551" (slot unquoted, no 0x prefixes)
    by_slot: dict[str, tuple[str, str | None]] = {}
    for line in nmm.stdout.splitlines():
        p = line.split('"')
        if len(p) >= 6 and p[3] == "1002":
            by_slot[p[0].strip()] = (f"1002:{p[5]}", None)
    # -mm: 03:00.0 "VGA compatible controller" "AMD/ATI" "Product" ...
    for line in mm.stdout.splitlines():
        p = line.split('"')
        slot = p[0].strip()
        if len(p) >= 6 and slot in by_slot:
            pci_id, _ = by_slot[slot]
            product = p[5]
            # "Navi 48 [Radeon AI PRO R9700]" -> "Radeon AI PRO R9700"
            m = re.search(r"\[(.+)\]\s*$", product)
            if m:
                product = m.group(1)
            by_slot[slot] = (pci_id, product)
    return {pci_id: name for pci_id, name in by_slot.values() if name}


def read_gpus(names: dict[str, str] | None = None) -> list[Gpu]:
    """Read metrics for all AMD GPUs currently present."""
    if names is None:
        names = device_names()
    gpus: list[Gpu] = []
    for dev in sorted(glob.glob(_DRM_GLOB)):
        card = _read_card(dev, names)
        if card is not None:
            gpus.append(card)
    return gpus


def _read_card(dev: str, names: dict[str, str]) -> Gpu | None:
    """Metrics for one /sys/class/drm/cardN/device, or None if not an AMD GPU."""
    pci_id = _pci_id(dev)
    if not pci_id or not pci_id.startswith(_AMD_VENDOR + ":"):
        return None
    if not os.path.exists(os.path.join(dev, "mem_info_vram_used")):
        return None
    try:
        index = int(os.path.basename(os.path.dirname(dev)).replace("card", ""))
    except ValueError:
        return None
    hwmon = _hwmon_dir(dev)
    busy = sysfs.read_int(os.path.join(dev, "gpu_busy_percent"))
    vram_total = (
        sysfs.read_int(os.path.join(dev, "mem_info_vis_vram_total"))
        or sysfs.read_int(os.path.join(dev, "mem_info_vram_total"))
    )
    return Gpu(
        index=index,
        name=_KNOWN_NAMES.get(pci_id) or names.get(pci_id) or f"AMD GPU {pci_id}",
        busy_percent=float(busy) if busy is not None else None,
        vram_used=sysfs.read_int(os.path.join(dev, "mem_info_vram_used")),
        vram_total=vram_total,
        power_w=_gpu_power_w(hwmon),
        temp_c=_gpu_temp_c(hwmon),
    )
