"""
Native, streaming ISO-BMFF (MP4) box parser.

Only box *headers* are read while walking the tree, so multi-GB files cost almost nothing.
Handles 32-bit and 64-bit (largesize) boxes, size==0 (box extends to EOF) and uuid boxes.
Absolute file offsets are recorded so that numeric fields can later be patched in place.
"""
import struct
from dataclasses import dataclass, field
from fractions import Fraction
from typing import BinaryIO, Iterator, Optional

from core.errors import CorruptedFileError, UnsupportedFormatError

CONTAINERS = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"edts", b"dinf"}


@dataclass
class Box:
    type: bytes
    offset: int
    size: int
    header_size: int
    children: list = field(default_factory=list)

    @property
    def payload_offset(self) -> int:
        return self.offset + self.header_size

    @property
    def payload_size(self) -> int:
        return self.size - self.header_size

    @property
    def end(self) -> int:
        return self.offset + self.size

    @property
    def name(self) -> str:
        return self.type.decode("latin-1")

    def find(self, t: bytes) -> Optional["Box"]:
        return next((c for c in self.children if c.type == t), None)

    def findall(self, t: bytes) -> list:
        return [c for c in self.children if c.type == t]

    def walk(self) -> Iterator["Box"]:
        yield self
        for c in self.children:
            yield from c.walk()


def read_at(f: BinaryIO, offset: int, n: int) -> bytes:
    f.seek(offset)
    data = f.read(n)
    if len(data) != n:
        raise CorruptedFileError(f"Unexpected end of file at offset {offset} (wanted {n} bytes).")
    return data


def u32(f, off): return struct.unpack(">I", read_at(f, off, 4))[0]
def i32(f, off): return struct.unpack(">i", read_at(f, off, 4))[0]
def u64(f, off): return struct.unpack(">Q", read_at(f, off, 8))[0]
def u16(f, off): return struct.unpack(">H", read_at(f, off, 2))[0]


def _parse_range(f: BinaryIO, start: int, end: int, depth: int = 0) -> list:
    boxes, pos = [], start
    while pos < end:
        if end - pos < 8:
            # Some muxers leave <8 bytes of zero padding; anything else is corruption.
            if read_at(f, pos, end - pos).strip(b"\x00") == b"":
                break
            raise CorruptedFileError(f"Trailing garbage at offset {pos}.")
        size, typ = struct.unpack(">I4s", read_at(f, pos, 8))
        hdr = 8
        if size == 1:
            size = u64(f, pos + 8)
            hdr = 16
        elif size == 0:
            size = end - pos
        if typ == b"uuid":
            hdr += 16
        if size < hdr or pos + size > end:
            raise CorruptedFileError(f"Invalid box '{typ.decode('latin-1')}' at offset {pos} (size {size}).")
        box = Box(typ, pos, size, hdr)
        if typ in CONTAINERS and depth < 12:
            box.children = _parse_range(f, box.payload_offset, box.end, depth + 1)
        boxes.append(box)
        pos += size
    return boxes


def parse(f: BinaryIO) -> list:
    f.seek(0, 2)
    size = f.tell()
    if size < 16:
        raise CorruptedFileError("File is too small to be an MP4.")
    boxes = _parse_range(f, 0, size)
    if not boxes or boxes[0].type not in (b"ftyp", b"styp", b"moov", b"free", b"skip", b"wide", b"mdat"):
        raise UnsupportedFormatError("Not an ISO-BMFF / MP4 file (no ftyp box).")
    return boxes


# ----------------------------------------------------------------------------- tracks

@dataclass
class TrackInfo:
    trak: Box
    track_id: int
    handler: str
    mdhd: Box
    mdhd_version: int
    timescale: int
    media_duration: int            # mdhd duration (media timescale units)
    stts: list                     # [(count, delta)]
    sample_count: int
    stts_box: Box
    ctts_box: Optional[Box]
    elst_box: Optional[Box]
    tkhd_box: Box
    stsd_box: Optional[Box]
    stsz_box: Optional[Box]

    @property
    def stts_total_units(self) -> int:
        return sum(c * d for c, d in self.stts)

    @property
    def duration(self) -> Fraction:
        """Exact duration in seconds, derived from the sample table (not from the header)."""
        return Fraction(self.stts_total_units, self.timescale)

    @property
    def fps(self) -> Fraction:
        d = self.duration
        return Fraction(self.sample_count) / d if d else Fraction(0)

    @property
    def is_video(self) -> bool: return self.handler == "vide"
    @property
    def is_audio(self) -> bool: return self.handler == "soun"

    @property
    def is_vfr(self) -> bool:
        return len({d for _, d in self.stts}) > 1


def read_stts(f, box: Box) -> list:
    n = u32(f, box.payload_offset + 4)
    if 8 + n * 8 > box.payload_size:
        raise CorruptedFileError("stts entry count exceeds box size.")
    data = read_at(f, box.payload_offset + 8, n * 8)
    return [struct.unpack_from(">II", data, i * 8) for i in range(n)]


def read_tracks(f, moov: Box) -> list:
    tracks = []
    for trak in moov.findall(b"trak"):
        tkhd = trak.find(b"tkhd")
        mdia = trak.find(b"mdia")
        if not tkhd or not mdia:
            raise CorruptedFileError("trak without tkhd/mdia.")
        mdhd, hdlr, minf = mdia.find(b"mdhd"), mdia.find(b"hdlr"), mdia.find(b"minf")
        stbl = minf.find(b"stbl") if minf else None
        if not (mdhd and hdlr and stbl):
            raise CorruptedFileError("trak is missing mdhd/hdlr/minf/stbl.")
        stts = stbl.find(b"stts")
        if not stts:
            raise CorruptedFileError("stbl has no stts box.")
        ver = read_at(f, mdhd.payload_offset, 1)[0]
        if ver not in (0, 1):
            raise UnsupportedFormatError(f"Unsupported mdhd version {ver}.")
        ts = u32(f, mdhd.payload_offset + (12 if ver == 0 else 20))
        dur = u32(f, mdhd.payload_offset + 16) if ver == 0 else u64(f, mdhd.payload_offset + 24)
        if ts == 0:
            raise CorruptedFileError("Media timescale is zero.")
        tver = read_at(f, tkhd.payload_offset, 1)[0]
        tid = u32(f, tkhd.payload_offset + (12 if tver == 0 else 20))
        handler = read_at(f, hdlr.payload_offset + 8, 4).decode("latin-1")
        entries = read_stts(f, stts)
        stsz = stbl.find(b"stsz")
        count = sum(c for c, _ in entries)
        if stsz:
            sz_count = u32(f, stsz.payload_offset + 8)
            if sz_count != count:
                raise CorruptedFileError(f"Track {tid}: stsz sample count ({sz_count}) != stts sample count ({count}).")
        edts = trak.find(b"edts")
        tracks.append(TrackInfo(trak, tid, handler, mdhd, ver, ts, dur, entries, count, stts,
                                stbl.find(b"ctts"), edts.find(b"elst") if edts else None, tkhd,
                                stbl.find(b"stsd"), stsz))
    return tracks


def check_supported(top: list) -> Box:
    """Reject structures we cannot patch safely. Returns the moov box."""
    types = [b.type for b in top]
    moov = next((b for b in top if b.type == b"moov"), None)
    if moov is None:
        raise UnsupportedFormatError("No 'moov' box found (incomplete or non-MP4 file).")
    if types.count(b"moov") > 1:
        raise UnsupportedFormatError("Multiple 'moov' boxes are not supported.")
    for t in (b"moof", b"sidx", b"mfra"):
        if t in types:
            raise UnsupportedFormatError("Fragmented MP4 (fMP4/DASH) is not supported — remux to a regular MP4 first.")
    if moov.find(b"mvex"):
        raise UnsupportedFormatError("Fragmented MP4 ('mvex' present) is not supported.")
    if not moov.find(b"mvhd"):
        raise CorruptedFileError("moov has no mvhd box.")
    if not moov.findall(b"trak"):
        raise CorruptedFileError("moov contains no tracks.")
    return moov


# ----------------------------------------------------------------------------- sample access

def iter_samples(f, t: TrackInfo) -> Iterator[tuple]:
    """Yield (file_offset, size) for every sample of a track, in decode order."""
    stbl = t.trak.find(b"mdia").find(b"minf").find(b"stbl")
    stsz, stsc = stbl.find(b"stsz"), stbl.find(b"stsc")
    co64 = stbl.find(b"co64")
    co = co64 or stbl.find(b"stco")
    if not (stsz and stsc and co):
        raise CorruptedFileError("Sample tables (stsz/stsc/stco) are incomplete.")
    p = stsz.payload_offset
    fixed, count = u32(f, p + 4), u32(f, p + 8)
    sizes = None if fixed else struct.unpack(f">{count}I", read_at(f, p + 12, count * 4))
    n = u32(f, stsc.payload_offset + 4)
    sc = [struct.unpack_from(">III", d, 0) for d in
          (read_at(f, stsc.payload_offset + 8 + i * 12, 12) for i in range(n))]
    nco = u32(f, co.payload_offset + 4)
    offs = struct.unpack(f">{nco}{'Q' if co64 else 'I'}", read_at(f, co.payload_offset + 8, nco * (8 if co64 else 4)))
    k, si = 0, 0
    for ci, base in enumerate(offs, start=1):
        while k + 1 < len(sc) and sc[k + 1][0] <= ci:
            k += 1
        pos = base
        for _ in range(sc[k][1]):
            if si >= count:
                return
            size = fixed or sizes[si]
            yield pos, size
            pos += size
            si += 1


def sample_digest(f, t: TrackInfo, progress=None) -> tuple:
    """SHA-256 over (size, bytes) of every sample, in order. Returns (hexdigest, sample_count)."""
    import hashlib
    h, n = hashlib.sha256(), 0
    for off, size in iter_samples(f, t):
        f.seek(off)
        data = f.read(size)
        if len(data) != size:
            raise CorruptedFileError("Sample extends past end of file.")
        h.update(size.to_bytes(4, "big"))
        h.update(data)
        n += 1
        if progress and n % 512 == 0:
            progress(n / max(t.sample_count, 1))
    return h.hexdigest(), n
