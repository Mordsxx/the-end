"""Finds the rife-ncnn-vulkan executable and its models. Supports any number of model versions."""
import os
import re
from dataclasses import dataclass
from pathlib import Path

from core.config import load_settings
from core.errors import ModelMissingError
from core.paths import exe_dir, resource_path

_EXE = "rife-ncnn-vulkan" + (".exe" if os.name == "nt" else "")

_LABELS = {
    "rife-v4.6": "RIFE v4.6 — best all-round (recommended)",
    "rife-v4": "RIFE v4.0",
    "rife-anime": "RIFE Anime — cartoons / anime (2× only)",
    "rife-HD": "RIFE HD (2× only)",
    "rife-UHD": "RIFE UHD (2× only)",
    "rife": "RIFE v1 (2× only)",
}
_PREFERENCE = ["rife-v4.6", "rife-v4", "rife-anime", "rife-HD", "rife-UHD", "rife"]


@dataclass
class RifeModel:
    name: str
    path: Path

    @property
    def supports_arbitrary_multiplier(self) -> bool:
        """v4+ models accept an arbitrary timestep, so 3×/4×/5×… are exact in a single pass."""
        m = re.match(r"rife-v(\d+)", self.name)
        return bool(m and int(m.group(1)) >= 4)

    @property
    def label(self) -> str:
        return _LABELS.get(self.name, self.name)


def _candidate_roots() -> list:
    s = load_settings().get("rife_dir", "")
    roots = [Path(s)] if s else []
    for base in (resource_path("models"), exe_dir() / "models", Path.cwd() / "models"):
        roots.append(base)
        if base.is_dir():
            roots.extend(p for p in base.iterdir() if p.is_dir())
    return roots


def find_rife_dir() -> Path | None:
    for r in _candidate_roots():
        if (r / _EXE).is_file():
            return r
    return None


def rife_executable() -> Path:
    d = find_rife_dir()
    if not d:
        raise ModelMissingError(
            "rife-ncnn-vulkan was not found.\n\nDownload it from https://github.com/nihui/rife-ncnn-vulkan/releases, "
            "extract it into the 'models' folder (models/rife-ncnn-vulkan/...), or set its folder in Settings.")
    return d / _EXE


def list_models() -> list:
    d = find_rife_dir()
    if not d:
        return []
    found = [RifeModel(p.name, p) for p in d.iterdir() if p.is_dir() and (p / "flownet.param").is_file()]
    order = {n: i for i, n in enumerate(_PREFERENCE)}
    return sorted(found, key=lambda m: (order.get(m.name, 99), m.name))


def get_model(name: str) -> RifeModel:
    for m in list_models():
        if m.name == name:
            return m
    raise ModelMissingError(f"RIFE model '{name}' is not installed. See docs/MODELS.md.")
