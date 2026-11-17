"""Shared media analysis built on FFprobe. VFR is detected explicitly, never assumed away."""
import json
import os
from dataclasses import dataclass
from fractions import Fraction

from .errors import CorruptedFileError, UnsupportedFormatError
from .ffmpeg_manager import ffprobe_path
from .process_manager import run


def parse_rate(s: str | None) -> Fraction | None:
    if not s or s in ("0/0", "N/A"):
        return None
    try:
        f = Fraction(s)
        return f if f > 0 else None
    except (ValueError, ZeroDivisionError):
        return None


def _f(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


@dataclass
class VideoInfo:
    path: str
    container: str
    size_bytes: int
    duration: float
    width: int
    height: int
    video_codec: str
    pix_fmt: str
    fps_nominal: Fraction | None      # r_frame_rate
    fps_average: Fraction | None      # avg_frame_rate
    frame_count: int | None
    frame_count_exact: bool
    video_bitrate: int | None
    total_bitrate: int | None
    is_vfr: bool
    has_audio: bool
    audio_codec: str
    audio_rate: int | None
    audio_channels: int | None
    audio_duration: float | None
    video_duration: float | None

    @property
    def fps(self) -> Fraction:
        """Best single FPS value: the average rate (correct for VFR), else the nominal rate."""
        return self.fps_average or self.fps_nominal or Fraction(30)

    @property
    def fps_float(self) -> float:
        return float(self.fps)

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"

    def summary_lines(self) -> list:
        fc = f"{self.frame_count}" + ("" if self.frame_count_exact else " (estimated)") if self.frame_count else "unknown"
        return [
            ("Resolution", self.resolution),
            ("Video codec", f"{self.video_codec} · {self.pix_fmt}"),
            ("FPS", f"{self.fps_float:.3f}" + ("  · VARIABLE frame rate" if self.is_vfr else "  · constant")),
            ("Duration", f"{self.duration:.3f} s"),
            ("Frames", fc),
            ("Audio", f"{self.audio_codec} · {self.audio_rate} Hz · {self.audio_channels} ch" if self.has_audio else "none"),
            ("Bitrate", f"{(self.total_bitrate or 0) / 1e6:.2f} Mbps"),
            ("Size", f"{self.size_bytes / 1024 ** 2:.1f} MB"),
        ]


def analyze(path: str, exact_frames: bool = False) -> VideoInfo:
    if not os.path.isfile(path):
        raise UnsupportedFormatError(f"File not found: {path}")
    probe = ffprobe_path()
    cmd = [probe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams"]
    if exact_frames:
        cmd += ["-count_frames"]
    cmd.append(path)
    r = run(cmd, timeout=600)
    if r.returncode != 0:
        raise CorruptedFileError(f"FFprobe could not read this file:\n{r.stderr.strip()[:500]}")
    try:
        data = json.loads(r.stdout)
    except ValueError as e:
        raise CorruptedFileError(f"FFprobe returned invalid data: {e}")
    streams = data.get("streams", [])
    fmt = data.get("format", {})
    v = next((s for s in streams if s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic", 0) == 0), None)
    if v is None:
        raise UnsupportedFormatError("No video stream found in this file.")
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)

    nominal = parse_rate(v.get("r_frame_rate"))
    average = parse_rate(v.get("avg_frame_rate"))
    duration = _f(v.get("duration")) or _f(fmt.get("duration"), 0.0)
    count = None
    exact = False
    for key in ("nb_read_frames", "nb_frames"):
        if v.get(key, "N/A").isdigit():
            count, exact = int(v[key]), True
            break
    if count is None and duration and (average or nominal):
        count = int(round(duration * float(average or nominal)))
    is_vfr = bool(nominal and average and abs(float(nominal) - float(average)) / float(nominal) > 0.01)

    return VideoInfo(
        path=path, container=fmt.get("format_name", ""), size_bytes=int(fmt.get("size", os.path.getsize(path))),
        duration=duration or 0.0, width=int(v.get("width", 0)), height=int(v.get("height", 0)),
        video_codec=v.get("codec_name", "?"), pix_fmt=v.get("pix_fmt", "?"),
        fps_nominal=nominal, fps_average=average, frame_count=count, frame_count_exact=exact,
        video_bitrate=int(v["bit_rate"]) if str(v.get("bit_rate", "")).isdigit() else None,
        total_bitrate=int(fmt["bit_rate"]) if str(fmt.get("bit_rate", "")).isdigit() else None,
        is_vfr=is_vfr, has_audio=a is not None,
        audio_codec=(a or {}).get("codec_name", ""),
        audio_rate=int(a["sample_rate"]) if a and str(a.get("sample_rate", "")).isdigit() else None,
        audio_channels=a.get("channels") if a else None,
        audio_duration=_f((a or {}).get("duration")),
        video_duration=_f(v.get("duration")),
    )


def extract_thumbnail(path: str, out_png: str, at: float = 0.0, width: int = 480) -> bool:
    from .ffmpeg_manager import ffmpeg_path
    r = run([ffmpeg_path(), "-v", "error", "-y", "-ss", f"{at:.3f}", "-i", path, "-frames:v", "1",
             "-vf", f"scale={width}:-2", out_png], timeout=60)
    return r.returncode == 0 and os.path.isfile(out_png)
