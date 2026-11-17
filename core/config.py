"""Persistent settings and processing history (JSON in the user's AppData folder)."""
import json
import threading
from pathlib import Path

from .paths import user_data_dir, default_output_dir

_LOCK = threading.Lock()
_DEFAULTS = {
    "output_dir": str(default_output_dir()),
    "ffmpeg_path": "",
    "ffprobe_path": "",
    "rife_dir": "",
    "device": "auto",
}


def _settings_file() -> Path:
    return user_data_dir() / "settings.json"


def _history_file() -> Path:
    return user_data_dir() / "history.json"


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def load_settings() -> dict:
    data = dict(_DEFAULTS)
    data.update(_read(_settings_file(), {}))
    return data


def save_settings(data: dict) -> None:
    with _LOCK:
        _settings_file().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_history() -> list:
    return _read(_history_file(), [])


def add_history(entry: dict, limit: int = 50) -> None:
    with _LOCK:
        hist = _read(_history_file(), [])
        hist.insert(0, entry)
        _history_file().write_text(json.dumps(hist[:limit], indent=2, ensure_ascii=False), encoding="utf-8")


def clear_history() -> None:
    with _LOCK:
        _history_file().write_text("[]", encoding="utf-8")
