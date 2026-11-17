"""
Native MP4 timing patcher: changes playback speed by editing timing metadata only.

No sample is decoded, re-encoded, moved or resized. All edits are fixed-width, in-place numeric
changes at offsets located by a real box parse, so no chunk offset (stco/co64) can ever become stale.
"""
import os
import shutil
import struct
import time
from dataclasses import dataclass, field
from fractions import Fraction

from core.errors import CorruptedFileError, DiskSpaceError, StudioError, UnsupportedFormatError
from . import mp4_parser as P
from .timing_engine import SlowFactor, TimingError, U32
from .validator import ValidationReport, validate


# ------------------------------------------------------------------------------- inspection

@dataclass
class Mp4Summary:
    path: str
    fps: Fraction
    duration: Fraction
    frame_count: int
    is_vfr: bool
    video_timescale: int
    has_audio: bool
    audio_rate: int | None
    audio_duration: Fraction | None
    brand: str
    tracks: int

    @property
    def fps_float(self): return float(self.fps)


def inspect(path: str) -> Mp4Summary:
    """Fast native inspection (reads headers and the sample-timing table only)."""
    with open(path, "rb") as f:
        top = P.parse(f)
        moov = P.check_supported(top)
        tracks = P.read_tracks(f, moov)
        v = next((t for t in tracks if t.is_video), None)
        if v is None:
            raise UnsupportedFormatError("No video track found in this MP4.")
        a = next((t for t in tracks if t.is_audio), None)
        ftyp = next((b for b in top if b.type == b"ftyp"), None)
        brand = P.read_at(f, ftyp.payload_offset, 4).decode("latin-1") if ftyp else "?"
        return Mp4Summary(path, v.fps, v.duration, v.sample_count, v.is_vfr, v.timescale,
                          a is not None, a.timescale if a else None, a.duration if a else None, brand, len(tracks))


# ------------------------------------------------------------------------------- planning

@dataclass
class TableScale:
    offset: int
    count: int
    stride: int
    field_off: int
    mult: int
    signed: bool = False
    what: str = ""


@dataclass
class PatchPlan:
    writes: list = field(default_factory=list)     # (offset, bytes)
    tables: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def ranges(self) -> list:
        r = [(o, o + len(b)) for o, b in self.writes]
        r += [(t.offset, t.offset + t.count * t.stride) for t in self.tables]
        return r


def _uint(value: int, size: int, what: str) -> bytes:
    if value < 0 or value >= 1 << (8 * size):
        raise TimingError(f"{what}: value {value} does not fit in {size * 8} bits after scaling.")
    return value.to_bytes(size, "big")


def build_plan(f, moov: P.Box, tracks: list, factor: SlowFactor, skip_audio: bool = False) -> PatchPlan:
    plan = PatchPlan()
    ratio = factor.ratio

    # movie header
    mvhd = moov.find(b"mvhd")
    ver = P.read_at(f, mvhd.payload_offset, 1)[0]
    if ver not in (0, 1):
        raise UnsupportedFormatError(f"Unsupported mvhd version {ver}.")
    off, size = (mvhd.payload_offset + 16, 4) if ver == 0 else (mvhd.payload_offset + 24, 8)
    old = P.u32(f, off) if ver == 0 else P.u64(f, off)
    if ver == 0 and old == U32:
        plan.notes.append("mvhd duration is 'unknown' (0xFFFFFFFF); left untouched")
    else:
        plan.writes.append((off, _uint(factor.scale_movie_units(old), size, "mvhd duration")))
    plan.notes.append(f"mvhd v{ver}: duration {old} → {factor.scale_movie_units(old)} (movie timescale units)")

    for t in tracks:
        if skip_audio and t.is_audio:
            continue
        tag = f"track {t.track_id} [{t.handler}]"
        mp = factor.media_plan(t.timescale)

        # tkhd duration (movie timescale)
        tp = t.tkhd_box.payload_offset
        tver = P.read_at(f, tp, 1)[0]
        if tver not in (0, 1):
            raise UnsupportedFormatError(f"Unsupported tkhd version {tver}.")
        o, s = (tp + 20, 4) if tver == 0 else (tp + 28, 8)
        old = P.u32(f, o) if tver == 0 else P.u64(f, o)
        if not (tver == 0 and old == U32):
            plan.writes.append((o, _uint(factor.scale_movie_units(old), s, f"{tag} tkhd duration")))

        # edit list
        if t.elst_box is not None:
            ep = t.elst_box.payload_offset
            ev = P.read_at(f, ep, 1)[0]
            if ev not in (0, 1):
                raise UnsupportedFormatError(f"Unsupported elst version {ev}.")
            n = P.u32(f, ep + 4)
            stride, ssz = (12, 4) if ev == 0 else (20, 8)
            if 8 + n * stride > t.elst_box.payload_size:
                raise CorruptedFileError("elst entry count exceeds box size.")
            data = P.read_at(f, ep + 8, n * stride)
            for i in range(n):
                base = ep + 8 + i * stride
                seg = int.from_bytes(data[i * stride:i * stride + ssz], "big")
                plan.writes.append((base, _uint(factor.scale_movie_units(seg), ssz, f"{tag} elst segment_duration")))
                if mp.mode == "delta":
                    fmt = ">i" if ev == 0 else ">q"
                    mt = struct.unpack_from(fmt, data, i * stride + ssz)[0]
                    if mt >= 0:
                        new = mt * mp.multiplier
                        plan.writes.append((base + ssz, struct.pack(fmt, new)))

        # media header
        mp_off = t.mdhd.payload_offset
        ts_off = mp_off + (12 if t.mdhd_version == 0 else 20)
        du_off, du_sz = (mp_off + 16, 4) if t.mdhd_version == 0 else (mp_off + 24, 8)
        plan.writes.append((ts_off, _uint(mp.new_timescale, 4, f"{tag} timescale")))
        if mp.mode == "delta":
            plan.writes.append((du_off, _uint(t.media_duration * mp.multiplier, du_sz, f"{tag} mdhd duration")))
            stbl = t.trak.find(b"mdia").find(b"minf").find(b"stbl")
            if stbl.find(b"cslg"):
                raise UnsupportedFormatError("'cslg' box combined with a non-divisible timescale is not supported.")
            mx = max((d for _, d in t.stts), default=0) * mp.multiplier
            if mx > U32:
                raise TimingError(f"{tag}: sample delta overflows 32 bits after scaling.")
            plan.tables.append(TableScale(t.stts_box.payload_offset + 8, len(t.stts), 8, 4, mp.multiplier, False, "stts"))
            if t.ctts_box is not None:
                cv = P.read_at(f, t.ctts_box.payload_offset, 1)[0]
                plan.tables.append(TableScale(t.ctts_box.payload_offset + 8, P.u32(f, t.ctts_box.payload_offset + 4),
                                              8, 4, mp.multiplier, cv == 1, "ctts"))
        plan.notes.append(f"{tag}: mode={mp.mode}, timescale {t.timescale} → {mp.new_timescale}"
                          + ("" if mp.mode == "timescale" else f", sample tables × {mp.multiplier}"))

    return plan


def _apply_table(f, t: TableScale, cancel=None):
    CH = 65536
    done = 0
    while done < t.count:
        if cancel:
            cancel.check()
        n = min(CH, t.count - done)
        base = t.offset + done * t.stride
        f.seek(base)
        buf = bytearray(f.read(n * t.stride))
        fmt = ">i" if t.signed else ">I"
        for i in range(n):
            pos = i * t.stride + t.field_off
            v = struct.unpack_from(fmt, buf, pos)[0] * t.mult
            try:
                struct.pack_into(fmt, buf, pos, v)
            except struct.error:
                raise TimingError(f"{t.what}: value overflows 32 bits after scaling.")
        f.seek(base)
        f.write(buf)
        done += n


# ------------------------------------------------------------------------------- main entry

@dataclass
class PatchResult:
    output_path: str
    factor: SlowFactor
    original_fps: Fraction
    output_fps: Fraction
    original_duration: Fraction
    output_duration: Fraction
    frame_count: int
    elapsed: float
    report: ValidationReport
    notes: list
    output_size: int


def unique_output_path(directory: str, stem: str, suffix: str, ext: str = ".mp4") -> str:
    os.makedirs(directory, exist_ok=True)
    base = os.path.join(directory, f"{stem}_{suffix}")
    cand, n = base + ext, 1
    while os.path.exists(cand):
        n += 1
        cand = f"{base}_{n}{ext}"
    return cand


def _encode_slowed_audio(src: str, out_audio: str, factor: SlowFactor, progress, cancel):
    """
    Stand-alone slowed audio: resample by the same ratio (pitch drops with speed, like the video) and encode to AAC.
    This is the only re-encoded stream; AAC cannot be slowed losslessly (see timing_engine docstring).
    """
    from core.ffmpeg_manager import ffmpeg_path
    from core.video_analyzer import analyze
    from core.process_manager import popen
    info = analyze(src)
    sr = info.audio_rate or 48000
    slow_rate = max(1000, int(round(sr * factor.q / factor.p)))
    br = 192_000 if (info.audio_channels or 2) > 1 else 128_000
    cmd = [ffmpeg_path(), "-v", "error", "-y", "-i", src, "-vn", "-sn", "-map", "0:a:0",
           "-af", f"asetrate={slow_rate},aresample={sr}", "-c:a", "aac", "-b:a", str(br), "-f", "mp4", out_audio]
    log = open(out_audio + ".log", "w+", encoding="utf-8")
    proc = popen(cmd, stdout=log, stderr=log)
    if cancel:
        cancel.register(proc)
    while proc.poll() is None:
        time.sleep(0.2)
        if cancel:
            cancel.check()
        progress(0.86, "Slowing the audio track…")
    log.seek(0)
    msg = log.read().strip()
    log.close()
    try:
        os.remove(out_audio + ".log")
    except OSError:
        pass
    if proc.returncode != 0:
        raise StudioError(f"FFmpeg failed while slowing the audio track:\n{msg[-800:]}")


def _extract_original_audio(src: str, out_audio: str, progress, cancel):
    """Extract the original audio bitstream unchanged; do not alter speed, pitch, or codec."""
    from core.ffmpeg_manager import ffmpeg_path
    from core.process_manager import popen
    cmd = [ffmpeg_path(), "-v", "error", "-y", "-i", src, "-vn", "-sn", "-dn",
           "-map", "0:a:0", "-c:a", "copy", "-f", "mp4", out_audio]
    log = open(out_audio + ".log", "w+", encoding="utf-8")
    proc = popen(cmd, stdout=log, stderr=log)
    if cancel:
        cancel.register(proc)
    while proc.poll() is None:
        time.sleep(0.2)
        if cancel:
            cancel.check()
        progress(0.86, "Preserving original audio…")
    log.seek(0)
    msg = log.read().strip()
    log.close()
    try:
        os.remove(out_audio + ".log")
    except OSError:
        pass
    if proc.returncode != 0:
        raise StudioError(f"FFmpeg failed while copying the original audio track:\n{msg[-800:]}")


def patch(src: str, dst: str, factor: SlowFactor, progress=None, cancel=None, run_validation: bool = True,
          audio_mode: str = "keep") -> PatchResult:
    """
    audio_mode: "keep"     - preserve original audio speed, pitch, codec and samples (default)
                "reencode" - slow the audio too
                "drop"     - remove audio
    The video is retimed independently. In keep mode, audio ends at its original timestamp;
    if the video is longer, the remaining tail is silent.
    """
    t0 = time.time()
    progress = progress or (lambda *a, **k: None)
    src_abs, dst_abs = os.path.abspath(src), os.path.abspath(dst)
    if os.path.normcase(src_abs) == os.path.normcase(dst_abs) or (os.path.exists(dst_abs) and os.path.samefile(src_abs, dst_abs)):
        raise StudioError("Refusing to overwrite the source video. Choose a different output file.")
    if os.path.exists(dst_abs):
        raise StudioError(f"Output file already exists: {dst_abs}")
    os.makedirs(os.path.dirname(dst_abs) or ".", exist_ok=True)

    size = os.path.getsize(src_abs)
    need = size * 2 + 64 * 1024 * 1024
    free = shutil.disk_usage(os.path.dirname(dst_abs) or ".").free
    if free < need:
        raise DiskSpaceError(f"Not enough free disk space: need ≈ {need / 1024 ** 2:.0f} MB, have {free / 1024 ** 2:.0f} MB.")

    progress(0.0, "Analysing MP4 structure…")
    with open(src_abs, "rb") as f:
        top = P.parse(f)
        moov = P.check_supported(top)
        tracks = P.read_tracks(f, moov)
        video = next((t for t in tracks if t.is_video), None)
        if video is None:
            raise UnsupportedFormatError("No video track found in this MP4.")
        has_audio = any(t.is_audio for t in tracks)
        if audio_mode not in ("keep", "reencode", "drop"):
            raise StudioError(f"Unknown audio mode '{audio_mode}'.")
        # Audio tracks are never retimed in place (would corrupt AAC); they are handled in the remux stage.
        plan = build_plan(f, moov, tracks, factor, skip_audio=has_audio)
        orig_fps, orig_dur, frames = video.fps, video.duration, video.sample_count

    part = dst_abs + ".part"
    stage = dst_abs + ".stage"
    audio_leftover = dst_abs + ".audio"
    try:
        CH = 8 * 1024 * 1024
        buf = bytearray(CH)
        mv = memoryview(buf)
        copied = 0
        target_for_copy = stage if has_audio else part
        with open(src_abs, "rb") as fi, open(target_for_copy, "wb") as fo:
            while True:
                if cancel:
                    cancel.check()
                n = fi.readinto(buf)
                if not n:
                    break
                fo.write(mv[:n])
                copied += n
                progress(0.8 * copied / max(size, 1), f"Copying streams… {copied / 1024 ** 2:.0f} / {size / 1024 ** 2:.0f} MB")
            fo.flush()
            os.fsync(fo.fileno())

        progress(0.82, "Patching timing metadata…")
        with open(target_for_copy, "r+b") as fo:
            for off, data in plan.writes:
                fo.seek(off)
                fo.write(data)
            for tbl in plan.tables:
                _apply_table(fo, tbl, cancel)
            fo.flush()
            os.fsync(fo.fileno())

        mode = "inplace"
        if has_audio:
            mode = "graft"
            audio_tmp = None
            if audio_mode == "reencode":
                audio_tmp = dst_abs + ".audio"
                _encode_slowed_audio(src_abs, audio_tmp, factor, progress, cancel)
            elif audio_mode == "keep":
                audio_tmp = dst_abs + ".audio"
                _extract_original_audio(src_abs, audio_tmp, progress, cancel)
            progress(0.88, "Rebuilding movie header…")
            from .mp4_audio import rebuild_with_audio
            rebuild_with_audio(stage, audio_tmp)
            os.replace(stage, part)
            if audio_tmp and os.path.exists(audio_tmp):
                os.remove(audio_tmp)
            if audio_mode == "reencode":
                plan.notes.append("audio: slowed and re-encoded; video samples untouched")
            elif audio_mode == "keep":
                plan.notes.append("audio: original speed, pitch and codec preserved; audio ends at its original time")
            else:
                plan.notes.append("audio: removed by request")

        progress(0.9, "Validating output…")
        if run_validation:
            validation_mode = "keep_audio" if has_audio and audio_mode == "keep" else ("graft" if has_audio else "inplace")
            report = validate(src_abs, part, factor, plan.ranges() if validation_mode == "inplace" else None, mode=validation_mode,
                              progress=lambda x: progress(0.9 + 0.09 * x, "Validating output…"), cancel=cancel)
        else:
            report = ValidationReport()
            report.add("Validation", True, "skipped by request", "info")
        if audio_mode == "drop":
            report.checks = [c for c in report.checks if not c.name.startswith("Audio")]
        if not report.passed:
            raise StudioError("Validation failed — the output was NOT saved.\n\n" + report.text())
        os.replace(part, dst_abs)
    finally:
        for tmp in (part, stage, audio_leftover):
            try:
                os.remove(tmp)
            except OSError:
                pass

    progress(1.0, "Done")
    return PatchResult(dst_abs, factor, orig_fps, orig_fps / factor.ratio, orig_dur, orig_dur * factor.ratio, frames,
                       time.time() - t0, report, plan.notes, os.path.getsize(dst_abs))
