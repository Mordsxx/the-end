"""CPU / RAM / GPU detection (NVIDIA via nvidia-smi, any vendor via Windows CIM)."""
import os
import platform
import shutil
import sys
from dataclasses import dataclass

from .process_manager import run


@dataclass
class GpuInfo:
    index: int
    name: str
    vram_mb: int | None = None
    driver: str = ""
    vendor: str = ""

    @property
    def label(self) -> str:
        vram = f" ({self.vram_mb // 1024} GB)" if self.vram_mb else ""
        return f"GPU {self.index}: {self.name}{vram}"


@dataclass
class HardwareInfo:
    cpu: str
    cores: int
    ram_gb: float | None
    gpus: list
    os_name: str

    @property
    def has_nvidia(self) -> bool:
        return any("nvidia" in (g.vendor + g.name).lower() for g in self.gpus)


def _ram_gb() -> float | None:
    try:
        if sys.platform == "win32":
            import ctypes

            class MEMSTAT(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("avail", ctypes.c_ulonglong), ("tpf", ctypes.c_ulonglong), ("apf", ctypes.c_ulonglong),
                            ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("ave", ctypes.c_ulonglong)]
            m = MEMSTAT()
            m.l = ctypes.sizeof(MEMSTAT)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.total / 1024 ** 3, 1)
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3, 1)
    except Exception:
        return None


def _cpu_name() -> str:
    if sys.platform == "win32":
        try:
            out = run(["powershell", "-NoProfile", "-Command",
                       "(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)"], timeout=15).stdout.strip()
            if out:
                return out
        except Exception:
            pass
    return platform.processor() or platform.machine()


def _gpus() -> list:
    gpus: list[GpuInfo] = []
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            out = run([smi, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"], timeout=10).stdout
            for i, line in enumerate(l for l in out.splitlines() if l.strip()):
                name, mem, drv = [x.strip() for x in line.split(",")[:3]]
                gpus.append(GpuInfo(i, name, int(float(mem)), drv, "NVIDIA"))
        except Exception:
            pass
    if not gpus and sys.platform == "win32":
        try:
            out = run(["powershell", "-NoProfile", "-Command",
                       "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name + '|' + $_.AdapterRAM + '|' + $_.DriverVersion }"],
                      timeout=15).stdout
            for i, line in enumerate(l for l in out.splitlines() if l.strip()):
                parts = line.split("|")
                name = parts[0].strip()
                ram = int(parts[1]) // (1024 * 1024) if len(parts) > 1 and parts[1].strip().isdigit() else None
                gpus.append(GpuInfo(i, name, ram, parts[2].strip() if len(parts) > 2 else "", name.split()[0]))
        except Exception:
            pass
    return gpus


_cache: HardwareInfo | None = None


def detect(refresh: bool = False) -> HardwareInfo:
    global _cache
    if _cache is None or refresh:
        _cache = HardwareInfo(_cpu_name(), os.cpu_count() or 1, _ram_gb(), _gpus(), f"{platform.system()} {platform.release()}")
    return _cache
