"""Filesystem helpers that work both from source and from a PyInstaller bundle."""
import os
import sys
from pathlib import Path

APP_NAME = "FlowframesTikTok60FPSStudio"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def bundle_root() -> Path:
    """Folder holding bundled read-only resources (assets, bin, models)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return project_root()


def exe_dir() -> Path:
    return Path(sys.executable).parent if is_frozen() else project_root()


def resource_path(*parts: str) -> Path:
    return bundle_root().joinpath(*parts)


def user_data_dir() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    p = Path(base) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def default_output_dir() -> Path:
    videos = Path.home() / "Videos"
    p = (videos if videos.exists() else Path.home()) / "Flowframes TikTok Studio"
    return p


def open_in_file_manager(path: str | os.PathLike) -> None:
    import subprocess
    path = str(path)
    if sys.platform == "win32":
        if os.path.isfile(path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path] if os.path.isfile(path) else ["open", path])
    else:
        subprocess.Popen(["xdg-open", path if os.path.isdir(path) else os.path.dirname(path)])


def open_file(path: str | os.PathLike) -> None:
    import subprocess
    path = str(path)
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
