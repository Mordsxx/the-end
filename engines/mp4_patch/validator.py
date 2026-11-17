"""
Independent validation of a patched MP4 against its source.

Nothing here trusts the patcher: both files are re-parsed from disk and compared.
Graft mode replaces the audio track while proving every video sample is identical. Audio may be kept unchanged or slowed.
"""
import hashlib

from core.errors import StudioError
from core.report import Check, ValidationReport  # noqa: F401  (re-exported)
from . import mp4_parser as P
from .timing_engine import SlowFactor


def _diff_outside(fa, fb, ranges, progress=None, cancel=None) -> tuple:
    """(sizes_equal, count of differing bytes that lie outside the allowed ranges)."""
    fa.seek(0, 2); fb.seek(0, 2)
    size = fa.tell()
    if size != fb.tell():
        return False, -1
    fa.seek(0); fb.seek(0)
    CH = 8 * 1024 * 1024
    pos = bad = 0
    while pos < size:
        if cancel:
            cancel.check()
        a, b = fa.read(CH), fb.read(CH)
        if a != b:
            for i, (x, y) in enumerate(zip(a, b)):
                if x != y and not any(s <= pos + i < e for s, e in ranges):
                    bad += 1
        pos += len(a)
        if progress:
            progress(pos / size)
    return True, bad


def _box_hash(f, box) -> bytes:
    h = hashlib.sha256()
    f.seek(box.payload_offset)
    left = box.payload_size
    while left:
        d = f.read(min(left, 4 * 1024 * 1024))
        if not d:
            break
        h.update(d)
        left -= len(d)
    return h.digest()


def _stbl(t):
    return t.trak.find(b"mdia").find(b"minf").find(b"stbl")


def validate(src_path: str, out_path: str, factor: SlowFactor, patched_ranges=None, mode: str = "inplace",
             progress=None, cancel=None, use_ffprobe: bool = True) -> ValidationReport:
    rep = ValidationReport()
    r = factor.ratio
    with open(src_path, "rb") as fs, open(out_path, "rb") as fo:
        try:
            top_s, top_o = P.parse(fs), P.parse(fo)
            moov_s, moov_o = P.check_supported(top_s), P.check_supported(top_o)
            tr_s, tr_o = P.read_tracks(fs, moov_s), P.read_tracks(fo, moov_o)
            rep.add("MP4 structural integrity", True, "output re-parsed without errors")
        except StudioError as e:
            rep.add("MP4 structural integrity", False, str(e))
            return rep

        vs = next((t for t in tr_s if t.is_video), None)
        vo = next((t for t in tr_o if t.is_video), None)
        as_ = next((t for t in tr_s if t.is_audio), None)
        ao = next((t for t in tr_o if t.is_audio), None)
        if not vs or not vo:
            rep.add("Video track present", False)
            return rep

        # ---- video timing (identical rules in both modes) -----------------------------------------
        rep.add("Video frame count preserved", vs.sample_count == vo.sample_count, f"{vo.sample_count} frames")
        exp_fps = vs.fps / r
        rep.add("Video duration scaled exactly", vo.duration == vs.duration * r,
                f"{float(vs.duration):.6f}s → {float(vo.duration):.6f}s (expected {float(vs.duration * r):.6f}s)")
        rep.add("Output FPS", vo.fps == exp_fps, f"{float(vs.fps):.3f} → {float(vo.fps):.3f} FPS (expected {float(exp_fps):.3f})")
        if vs.is_vfr:
            rep.add("Variable frame rate", True, "VFR source: per-sample timing scaled uniformly", "info")

        # ---- encoded video samples ------------------------------------------------------------------
        if mode == "inplace":
            rep.add("Top-level box layout unchanged", [(b.type, b.size) for b in top_s] == [(b.type, b.size) for b in top_o])
            for t in (b"stsz", b"stco", b"co64", b"stsc", b"stss", b"stsd"):
                a, b = _stbl(vs).find(t), _stbl(vo).find(t)
                if a or b:
                    rep.add(f"Video '{t.decode()}' table identical", bool(a and b and _box_hash(fs, a) == _box_hash(fo, b)))
            if as_ and ao:
                rep.add("Audio sample count preserved", as_.sample_count == ao.sample_count)
            if patched_ranges is not None:
                ok, bad = _diff_outside(fs, fo, patched_ranges, progress, cancel)
                rep.add("Every encoded sample preserved", ok and bad == 0,
                        f"all bytes outside {len(patched_ranges)} patched timing field(s) are identical" if ok and bad == 0
                        else f"{bad} unexpected byte difference(s)")
        else:
            ds, n1 = P.sample_digest(fs, vs, (lambda x: progress(x * 0.5)) if progress else None)
            do, n2 = P.sample_digest(fo, vo, (lambda x: progress(0.5 + x * 0.5)) if progress else None)
            rep.add("Every encoded video sample preserved", ds == do and n1 == n2,
                    f"{n2} samples bit-identical to the source (SHA-256 of all sample bytes)")
            rep.add("Video codec config (stsd) identical", _box_hash(fs, _stbl(vs).find(b"stsd")) == _box_hash(fo, _stbl(vo).find(b"stsd")),
                    "", "warn")

        # ---- audio / sync -------------------------------------------------------------------------
        if as_ is not None:
            if ao is None:
                rep.add("Audio track present", False, "audio was lost")
            else:
                if mode == "keep_audio":
                    rep.add("Original audio duration preserved", abs(float(ao.duration - as_.duration)) <= 0.02,
                            f"{float(as_.duration):.3f}s → {float(ao.duration):.3f}s (unchanged)")
                    before, after = float(as_.duration - vs.duration), float(ao.duration - vo.duration)
                    expected_after = float(as_.duration - vs.duration * r)
                    drift = abs(after - expected_after)
                    rep.add("Audio remains at original speed", drift <= 0.05,
                            f"audio/video end offset {after * 1000:.1f} ms (expected {expected_after * 1000:.1f} ms)")
                else:
                    exp_a = as_.duration * r
                    if mode == "inplace":
                        rep.add("Audio duration scaled exactly", ao.duration == exp_a, f"{float(ao.duration):.6f}s")
                    else:
                        rep.add("Audio duration scaled", abs(float(ao.duration - exp_a)) <= 0.1,
                                f"{float(as_.duration):.3f}s → {float(ao.duration):.3f}s (expected ≈ {float(exp_a):.3f}s)")
                    before, after = float(as_.duration - vs.duration), float(ao.duration - vo.duration)
                    drift = abs(after - before * float(r))
                    rep.add("Audio/video synchronisation", drift <= (1e-6 if mode == "inplace" else 0.1),
                            f"A−V offset {before * 1000:.1f} ms → {after * 1000:.1f} ms (drift {drift * 1000:.2f} ms)")
        else:
            rep.add("Audio track", True, "source has no audio", "info")

        mv = lambda f, m: _movie(f, m)
        ts_s, du_s = mv(fs, moov_s)
        ts_o, du_o = mv(fo, moov_o)
        if mode == "inplace":
            rep.add("Movie header duration scaled", abs(du_o - factor.scale_movie_units(du_s) * ts_o // ts_s) <= 1 and ts_s == ts_o,
                    f"{du_s / ts_s:.3f}s → {du_o / ts_o:.3f}s")

    if use_ffprobe:
        _ffprobe_check(rep, src_path, out_path, factor)
    return rep


def _movie(f, moov):
    b = moov.find(b"mvhd")
    ver = P.read_at(f, b.payload_offset, 1)[0]
    ts = P.u32(f, b.payload_offset + (12 if ver == 0 else 20))
    du = P.u32(f, b.payload_offset + 16) if ver == 0 else P.u64(f, b.payload_offset + 24)
    return ts, du


def _ffprobe_check(rep, src, out, factor):
    try:
        from core.video_analyzer import analyze
        a, b = analyze(src), analyze(out)
    except Exception as e:  # FFprobe is an optional second opinion
        rep.add("FFprobe cross-check", True, f"skipped ({e})", "info")
        return
    exp_d = a.duration * float(factor.ratio)
    rep.add("FFprobe: duration", abs(b.duration - exp_d) < max(0.1, exp_d * 0.003), f"{b.duration:.3f}s (expected ≈ {exp_d:.3f}s)", "warn")
    exp_fps = float(a.fps) / float(factor.ratio)
    rep.add("FFprobe: average FPS", abs(float(b.fps) - exp_fps) < max(0.05, exp_fps * 0.005), f"{float(b.fps):.3f} (expected ≈ {exp_fps:.3f})", "warn")
    rep.add("FFprobe: codecs unchanged", (a.video_codec, a.audio_codec) == (b.video_codec, b.audio_codec),
            f"{b.video_codec} / {b.audio_codec or '—'}", "warn")
    rep.add("FFprobe: resolution & pixel format unchanged", (a.resolution, a.pix_fmt) == (b.resolution, b.pix_fmt),
            f"{b.resolution} {b.pix_fmt}", "warn")
