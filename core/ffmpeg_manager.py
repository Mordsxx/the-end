"""Locates FFmpeg / FFprobe (user override -> bundled -> next to exe -> PATH)."""
import os
import shutil
from pathlib import Path

from .config import load_settings
from .errors import ToolMissingError
from .paths import resource_path, exe_dir
from .process_manager import run

_EXT = ".exe" if os.name == "nt" else ""


def _find(name: str, override: str = "") -> str | None:
    if override and Path(override).is_file():
        return override
    for base in (resource_path("bin"), exe_dir() / "bin", exe_dir()):
        cand = Path(base) / (name + _EXT)
        if cand.is_file():
            return str(cand)
    return shutil.which(name)


def ffmpeg_path(required: bool = True) -> str | None:
    p = _find("ffmpeg", load_settings().get("ffmpeg_path", ""))
    if not p and required:
        raise ToolMissingError("FFmpeg was not found. Place ffmpeg.exe in the 'bin' folder or set its path in Settings.")
    return p


def ffprobe_path(required: bool = True) -> str | None:
    p = _find("ffprobe", load_settings().get("ffprobe_path", ""))
    if not p and required:
        raise ToolMissingError("FFprobe was not found. Place ffprobe.exe in the 'bin' folder or set its path in Settings.")
    return p


def ffmpeg_version() -> str:
    p = ffmpeg_path(required=False)
    if not p:
        return "not found"
    try:
        out = run([p, "-version"], timeout=10).stdout.splitlines()
        return out[0] if out else "unknown"
    except Exception:
        return "unknown"
