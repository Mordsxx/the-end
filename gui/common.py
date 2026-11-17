"""Helpers shared by both workspaces (UI-level only; no engine imports from the other engine)."""
import os
import time

from core import config
from core.video_analyzer import analyze


def summarize_output(path: str, mode: str, elapsed: float, extra: dict | None = None) -> dict:
    """Runs in the worker thread: probe the finished file for the completion screen."""
    info = analyze(path, exact_frames=True)
    d = {
        "Output filename": os.path.basename(path),
        "Output FPS": f"{float(info.fps):.3f}",
        "Output duration": f"{info.duration:.3f} s",
        "Output frame count": str(info.frame_count if info.frame_count is not None else "n/a"),
        "Video codec": f"{info.video_codec} ({info.resolution}, {info.pix_fmt})",
        "Audio codec": info.audio_codec or "none",
        "Output file size": f"{info.size_bytes / 1024 ** 2:.2f} MB",
        "Processing time": f"{elapsed:.1f} s",
        "Processing mode": mode,
    }
    if extra:
        d.update(extra)
    return {"path": path, "rows": d, "mode": mode}


def record_history(summary: dict, source: str) -> None:
    config.add_history({"mode": summary["mode"], "input": os.path.basename(source), "output": summary["path"],
                        "fps": summary["rows"].get("Output FPS", ""), "when": time.strftime("%Y-%m-%d %H:%M")})


def unique_path(directory: str, stem: str, suffix: str, ext: str) -> str:
    os.makedirs(directory, exist_ok=True)
    base = os.path.join(directory, f"{stem}_{suffix}")
    cand, n = base + ext, 1
    while os.path.exists(cand):
        n += 1
        cand = f"{base}_{n}{ext}"
    return cand


def fmt_fps(x: float) -> str:
    return f"{x:.3f}".rstrip("0").rstrip(".")
