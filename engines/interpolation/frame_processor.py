"""
Streaming frame I/O around FFmpeg.

* FrameReader  : one FFmpeg decoder process -> raw RGB frames over a pipe (nothing is loaded in memory at once).
                 Variable-frame-rate sources are normalised to constant frame rate explicitly.
* FrameEncoder : one FFmpeg encoder process <- PNG frames over a pipe, muxing the original audio.
"""
import os
from fractions import Fraction

from core.errors import StudioError
from core.ffmpeg_manager import ffmpeg_path
from core.process_manager import popen

FORMATS = {
    "MP4 · H.264": ("mp4", ["-c:v", "libx264", "-pix_fmt", "yuv420p"], ["-movflags", "+faststart"]),
    "MP4 · H.265": ("mp4", ["-c:v", "libx265", "-pix_fmt", "yuv420p", "-tag:v", "hvc1"], ["-movflags", "+faststart"]),
    "MKV · H.264": ("mkv", ["-c:v", "libx264", "-pix_fmt", "yuv420p"], []),
}
PRESETS = {  # quality preset -> (crf, x264 preset, rife extra args)
    "fast": (23, "veryfast", []),
    "balanced": (18, "medium", []),
    "high": (14, "slow", ["-x"]),   # spatial TTA: slower, fewer artefacts
}
RESOLUTIONS = {"Original": None, "2160p": 2160, "1440p": 1440, "1080p": 1080, "720p": 720, "480p": 480}


def frac_str(fr: Fraction) -> str:
    return f"{fr.numerator}/{fr.denominator}"


class FrameReader:
    def __init__(self, path: str, width: int, height: int, fps: Fraction, normalise_cfr: bool,
                 max_frames: int | None, log_path: str, cancel=None):
        self.w, self.h = width, height
        self.frame_bytes = width * height * 3
        cmd = [ffmpeg_path(), "-v", "error", "-i", path, "-an", "-sn", "-dn"]
        if normalise_cfr:
            cmd += ["-vf", f"fps={frac_str(fps)}"]
        if max_frames:
            cmd += ["-frames:v", str(max_frames)]
        cmd += ["-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]
        self._log = open(log_path, "w+", encoding="utf-8")
        self.proc = popen(cmd, stdout=__import__("subprocess").PIPE, stderr=self._log, bufsize=self.frame_bytes * 2)
        if cancel:
            cancel.register(self.proc)

    def read(self) -> bytes | None:
        buf = self.proc.stdout.read(self.frame_bytes)
        if len(buf) < self.frame_bytes:
            return None
        return buf

    def close(self) -> str:
        try:
            self.proc.stdout.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()
        self._log.seek(0)
        msg = self._log.read().strip()
        self._log.close()
        return msg


class FrameEncoder:
    def __init__(self, out_path: str, in_fps: Fraction, out_fps: Fraction, src_path: str, has_audio: bool,
                 audio_codec: str, fmt: str, preset: str, out_height: int | None, preview_seconds: float | None,
                 log_path: str, cancel=None):
        ext, vargs, margs = FORMATS[fmt]
        crf, x_preset, _ = PRESETS[preset]
        cmd = [ffmpeg_path(), "-v", "error", "-y", "-f", "image2pipe", "-framerate", frac_str(in_fps),
               "-c:v", "png", "-i", "pipe:0"]
        if has_audio:
            cmd += ["-i", src_path]
        cmd += ["-map", "0:v:0"]
        if has_audio:
            cmd += ["-map", "1:a:0"]
        vf = []
        if out_fps != in_fps:
            vf.append(f"fps={frac_str(out_fps)}")
        if out_height:
            vf.append(f"scale=-2:{out_height}:flags=lanczos")
        if vf:
            cmd += ["-vf", ",".join(vf)]
        cmd += vargs + ["-crf", str(crf)]
        if vargs[1] == "libx264":
            cmd += ["-preset", x_preset]
        elif vargs[1] == "libx265":
            cmd += ["-preset", x_preset, "-x265-params", "log-level=error"]
        if has_audio:
            if audio_codec in ("aac", "mp3", "ac3", "eac3", "opus", "flac") and not (ext == "mp4" and audio_codec in ("flac",)):
                cmd += ["-c:a", "copy"]
            else:
                cmd += ["-c:a", "aac", "-b:a", "192k"]
        if preview_seconds:
            cmd += ["-t", f"{preview_seconds:.3f}"]
        cmd += margs + ["-f", {"mp4": "mp4", "mkv": "matroska"}[ext], out_path]
        self._log = open(log_path, "w+", encoding="utf-8")
        self.proc = popen(cmd, stdin=__import__("subprocess").PIPE, stdout=self._log, stderr=self._log)
        if cancel:
            cancel.register(self.proc)

    def write_file(self, path: str, times: int = 1) -> None:
        with open(path, "rb") as f:
            data = f.read()
        self.write(data, times)

    def write(self, data: bytes, times: int = 1) -> None:
        try:
            for _ in range(times):
                self.proc.stdin.write(data)
        except (BrokenPipeError, OSError):
            raise StudioError("The FFmpeg encoder stopped unexpectedly:\n" + self._read_log())

    def _read_log(self) -> str:
        try:
            self._log.flush()
            self._log.seek(0)
            return self._log.read().strip()[-1000:]
        except ValueError:
            return ""

    def finish(self) -> None:
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        rc = self.proc.wait()
        msg = self._read_log()
        self._log.close()
        if rc != 0:
            raise StudioError(f"FFmpeg encoder failed (exit code {rc}):\n{msg}")
