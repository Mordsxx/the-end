"""
Native audio-track replacement.

The slowed audio (re-encoded by FFmpeg into a stand-alone MP4) is grafted into the patched video file WITHOUT
touching the video samples or their offsets:

    [ original file bytes ............ ][ new mdat (audio samples) ][ new moov ]
      ^ old moov is turned into a 'free' box in place, so every video chunk offset stays valid

The new moov = patched video trak(s) copied verbatim + the new audio trak with its chunk offsets shifted.
"""
import struct
from fractions import Fraction

from core.errors import CorruptedFileError, StudioError, UnsupportedFormatError
from . import mp4_parser as P

U32 = 0xFFFFFFFF


def _box(typ: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), typ) + payload


def _movie_ts(f, moov):
    b = moov.find(b"mvhd")
    ver = P.read_at(f, b.payload_offset, 1)[0]
    ts = P.u32(f, b.payload_offset + (12 if ver == 0 else 20))
    return ts, b, ver


def _prepare_audio_trak(fa, a_moov, a_trak, a_tracks, mvts_main, new_track_id, shift):
    ts_a, _, _ = _movie_ts(fa, a_moov)
    t = a_tracks[0]
    raw = bytearray(P.read_at(fa, a_trak.offset, a_trak.size))
    rel = lambda off: off - a_trak.offset

    # tkhd: track id + duration (movie timescale of the *main* file)
    tp = t.tkhd_box.payload_offset
    tver = raw[rel(tp)]
    id_off = rel(tp + (12 if tver == 0 else 20))
    raw[id_off:id_off + 4] = new_track_id.to_bytes(4, "big")
    dur_off, dsz = (rel(tp + 20), 4) if tver == 0 else (rel(tp + 28), 8)
    new_dur = int(Fraction(t.media_duration, t.timescale) * mvts_main + Fraction(1, 2))
    raw[dur_off:dur_off + dsz] = new_dur.to_bytes(dsz, "big")

    # edit list (movie timescale -> main file's movie timescale)
    if t.elst_box is not None:
        ep = t.elst_box.payload_offset
        ev = raw[rel(ep)]
        n = int.from_bytes(raw[rel(ep) + 4:rel(ep) + 8], "big")
        stride, ssz = (12, 4) if ev == 0 else (20, 8)
        for i in range(n):
            o = rel(ep) + 8 + i * stride
            seg = int.from_bytes(raw[o:o + ssz], "big")
            seg = int(Fraction(seg) * mvts_main / ts_a + Fraction(1, 2))
            raw[o:o + ssz] = seg.to_bytes(ssz, "big")

    # chunk offsets
    stbl = t.trak.find(b"mdia").find(b"minf").find(b"stbl")
    co64, stco = stbl.find(b"co64"), stbl.find(b"stco")
    box = co64 or stco
    if box is None:
        raise CorruptedFileError("Audio track has no chunk offset table.")
    n = int.from_bytes(raw[rel(box.payload_offset) + 4:rel(box.payload_offset) + 8], "big")
    w = 8 if co64 else 4
    for i in range(n):
        o = rel(box.payload_offset) + 8 + i * w
        v = int.from_bytes(raw[o:o + w], "big") + shift
        if v < 0 or v >= 1 << (8 * w):
            raise UnsupportedFormatError("Audio chunk offset does not fit in 32 bits (file > 4 GB).")
        raw[o:o + w] = v.to_bytes(w, "big")
    return bytes(raw), new_dur


def rebuild_with_audio(stage_path: str, audio_path: str | None) -> None:
    """
    Modify `stage_path` in place: drop its audio trak(s) and, if audio_path is given, append that file's audio track.
    """
    with open(stage_path, "r+b") as f:
        top = P.parse(f)
        moov = P.check_supported(top)
        tracks = P.read_tracks(f, moov)
        audio_traks = {t.trak.offset for t in tracks if t.is_audio}
        mvts, mvhd, mver = _movie_ts(f, moov)
        end = f.seek(0, 2)

        new_mdat = b""
        a_trak_bytes, a_dur, payload_src = None, 0, None
        if audio_path:
            with open(audio_path, "rb") as fa:
                a_top = P.parse(fa)
                a_moov = P.check_supported(a_top)
                a_tracks = [t for t in P.read_tracks(fa, a_moov) if t.is_audio]
                mdats = [b for b in a_top if b.type == b"mdat"]
                if len(a_tracks) != 1 or len(mdats) != 1:
                    raise UnsupportedFormatError("Re-encoded audio file has an unexpected layout.")
                md = mdats[0]
                offs = [o for o, _ in P.iter_samples(fa, a_tracks[0])]
                sizes_end = max(o + s for o, s in P.iter_samples(fa, a_tracks[0]))
                if min(offs) < md.payload_offset or sizes_end > md.end:
                    raise CorruptedFileError("Audio samples lie outside the mdat box.")
                hdr = 16 if md.payload_size + 8 > U32 else 8
                new_payload_pos = end + hdr
                shift = new_payload_pos - md.payload_offset
                tid = max((t.track_id for t in tracks if t.is_audio), default=max(t.track_id for t in tracks) + 1)
                a_trak_bytes, a_dur = _prepare_audio_trak(fa, a_moov, a_tracks[0].trak, a_tracks, mvts, tid, shift)
                payload_src = (md.payload_offset, md.payload_size, hdr)

        # video (and other) track durations in movie timescale
        durs = []
        for t in tracks:
            if t.trak.offset in audio_traks:
                continue
            tp = t.tkhd_box.payload_offset
            tv = P.read_at(f, tp, 1)[0]
            durs.append(P.u32(f, tp + 20) if tv == 0 else P.u64(f, tp + 28))
        movie_dur = max(durs + [a_dur])

        parts, placed = [], False
        for ch in moov.children:
            raw = P.read_at(f, ch.offset, ch.size)
            if ch.type == b"mvhd":
                b = bytearray(raw)
                o, s = (8 + 16, 4) if mver == 0 else (8 + 24, 8)
                if ch.header_size != 8:
                    raise UnsupportedFormatError("mvhd with extended size is not supported.")
                if movie_dur >= 1 << (8 * s):
                    raise UnsupportedFormatError("Movie duration overflows its field.")
                b[o:o + s] = movie_dur.to_bytes(s, "big")
                parts.append(bytes(b))
            elif ch.type == b"trak" and ch.offset in audio_traks:
                if a_trak_bytes and not placed:
                    parts.append(a_trak_bytes)
                    placed = True
            else:
                parts.append(raw)
        if a_trak_bytes and not placed:
            parts.append(a_trak_bytes)
        new_moov = _box(b"moov", b"".join(parts))

        # ---- commit: everything below only appends, plus one 4-byte in-place type change ------------------
        f.seek(moov.offset + 4)
        f.write(b"free")
        f.seek(end)
        if payload_src:
            off, size, hdr = payload_src
            f.write(struct.pack(">I4s", 8 + size, b"mdat") if hdr == 8 else struct.pack(">I4sQ", 1, b"mdat", 16 + size))
            with open(audio_path, "rb") as fa:
                fa.seek(off)
                left = size
                while left:
                    d = fa.read(min(left, 8 * 1024 * 1024))
                    if not d:
                        raise CorruptedFileError("Unexpected end of audio file.")
                    f.write(d)
                    left -= len(d)
        f.write(new_moov)
        f.flush()
        import os
        os.fsync(f.fileno())
