"""GPU metrics: AMD from sysfs (amdgpu), NVIDIA from NVML. No external
processes per poll.

AMD utilisation comes from /sys/class/drm/cardN/device/gpu_busy_percent,
which requires the amdgpu.gpu_busy_percent=1 kernel parameter. If it is
missing, the field shows "n/a".

NVIDIA needs the optional `nvidia-ml-py` dependency (`pip install
resmon-lite[nvidia]`) plus the proprietary driver; if either is absent,
NVIDIA GPUs are silently skipped rather than crashing the app.
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
from dataclasses import dataclass

from . import sysfs

try:  # optional: only needed for NVIDIA GPUs
    import pynvml
except ImportError:  # pragma: no cover - NVIDIA extra not installed
    pynvml = None

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


def _pci_address(dev_dir: str) -> str:
    """PCI address of a cardN/device link, e.g. '0000:03:00.0'."""
    return os.path.basename(os.path.realpath(dev_dir))


def _hwmon_dir(dev_dir: str) -> str | None:
    for d in sorted(glob.glob(os.path.join(dev_dir, "hwmon", "*"))):
        if os.path.isdir(d):
            return d
    return None


@dataclass
class _CardPaths:
    pci_id: str
    vram_used: str
    vram_total: tuple[str, str]
    busy: str
    power: tuple[str, ...]
    temp: str | None


_card_cache: dict[str, _CardPaths | None] = {}


def _resolve_temp_sensor(hm: str | None) -> str | None:
    """Find best GPU temp sensor path (prefer junction, then edge, else first)."""
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
                if sysfs.read_int(f) is not None:
                    return f
    for f in sensors:
        if sysfs.read_int(f) is not None:
            return f
    return None


def _gpu_temp_c(hm: str | None) -> float | None:
    """GPU temperature: prefer junction, then edge, else first available."""
    sensor = _resolve_temp_sensor(hm)
    if sensor is None:
        return None
    v = sysfs.read_int(sensor)
    return v / 1000.0 if v is not None else None


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
    """Read metrics for all AMD + NVIDIA GPUs currently present."""
    if names is None:
        names = device_names()
    gpus: list[Gpu] = []
    # Order by PCI address, not DRM card number: the kernel can probe cards
    # out of bus order (card0 may be 07:00.0 and card1 03:00.0), whereas
    # rocm-smi / amd-smi / nvtop number GPUs by bus, so follow them.
    for dev in sorted(glob.glob(_DRM_GLOB), key=_pci_address):
        card = _read_card(dev, names)
        if card is not None:
            card.index = len(gpus)
            gpus.append(card)
    for i, card in enumerate(_read_nvidia_gpus()):
        card.index = len(gpus) + i
        gpus.append(card)
    return gpus


# -- NVIDIA (NVML) -----------------------------------------------------------

_nvml_ready: bool | None = None  # None = not attempted yet


def _nvml_init() -> bool:
    """Initialise NVML once; cache whether it worked (no driver = False)."""
    global _nvml_ready
    if _nvml_ready is None:
        try:
            pynvml.nvmlInit()
            _nvml_ready = True
        except pynvml.NVMLError:
            _nvml_ready = False
    return _nvml_ready


def _read_nvidia_gpus() -> list[Gpu]:
    """Metrics for all NVIDIA GPUs via NVML, or [] if unavailable."""
    if pynvml is None or not _nvml_init():
        return []
    gpus: list[Gpu] = []
    try:
        count = pynvml.nvmlDeviceGetCount()
    except pynvml.NVMLError:
        return []
    for i in range(count):
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode()
        except pynvml.NVMLError:
            continue
        gpus.append(
            Gpu(
                index=i,
                name=name,
                busy_percent=_nvml_util(handle),
                vram_used=_nvml_mem(handle, "used"),
                vram_total=_nvml_mem(handle, "total"),
                power_w=_nvml_power(handle),
                temp_c=_nvml_temp(handle),
            )
        )
    return gpus


def _nvml_util(handle) -> float | None:
    try:
        return float(pynvml.nvmlDeviceGetUtilizationRates(handle).gpu)
    except pynvml.NVMLError:
        return None


def _nvml_mem(handle, field: str) -> int | None:
    try:
        return int(getattr(pynvml.nvmlDeviceGetMemoryInfo(handle), field))
    except pynvml.NVMLError:
        return None


def _nvml_power(handle) -> float | None:
    try:
        return pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0
    except pynvml.NVMLError:
        return None


def _nvml_temp(handle) -> float | None:
    try:
        return float(pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU))
    except pynvml.NVMLError:
        return None


def _get_card_paths(dev: str) -> _CardPaths | None:
    if dev in _card_cache:
        return _card_cache[dev]
    pci_id = _pci_id(dev)
    if not pci_id or not pci_id.startswith(_AMD_VENDOR + ":"):
        _card_cache[dev] = None
        return None
    vram_used = os.path.join(dev, "mem_info_vram_used")
    if not os.path.exists(vram_used):
        _card_cache[dev] = None
        return None
    hwmon = _hwmon_dir(dev)
    power_paths = (
        tuple(os.path.join(hwmon, n) for n in ("power1_average", "power1_input"))
        if hwmon
        else ()
    )
    paths = _CardPaths(
        pci_id=pci_id,
        vram_used=vram_used,
        vram_total=(
            os.path.join(dev, "mem_info_vis_vram_total"),
            os.path.join(dev, "mem_info_vram_total"),
        ),
        busy=os.path.join(dev, "gpu_busy_percent"),
        power=power_paths,
        temp=_resolve_temp_sensor(hwmon),
    )
    _card_cache[dev] = paths
    return paths


def _read_card(dev: str, names: dict[str, str]) -> Gpu | None:
    """Metrics for one /sys/class/drm/cardN/device, or None if not an AMD GPU."""
    paths = _get_card_paths(dev)
    if paths is None:
        return None
    vram_used = sysfs.read_int(paths.vram_used)
    if vram_used is None:
        _card_cache.pop(dev, None)
        return None
    busy = sysfs.read_int(paths.busy)
    vram_total = sysfs.read_int(paths.vram_total[0]) or sysfs.read_int(paths.vram_total[1])
    power_w = None
    for p in paths.power:
        v = sysfs.read_int(p)
        if v is not None:
            power_w = v / 1e6
            break
    temp_v = sysfs.read_int(paths.temp) if paths.temp else None
    return Gpu(
        index=0,  # assigned by read_gpus in PCI order
        name=_KNOWN_NAMES.get(paths.pci_id) or names.get(paths.pci_id) or f"AMD GPU {paths.pci_id}",
        busy_percent=float(busy) if busy is not None else None,
        vram_used=vram_used,
        vram_total=vram_total,
        power_w=power_w,
        temp_c=temp_v / 1000.0 if temp_v is not None else None,
    )
