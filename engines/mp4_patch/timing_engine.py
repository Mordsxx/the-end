"""
Rational timing mathematics for the MP4 patcher. No floating point is used for the patch itself.

Slowdown ratio  r = p/q   (new_duration = old_duration * r).

Per media track there are two exact strategies:

* TIMESCALE mode  - possible when ts*q is divisible by p.  The media timescale becomes ts*q/p and
                    every sample table (stts/ctts/elst media_time) stays byte-identical.
* DELTA mode      - otherwise: timescale -> ts*q, every sample delta / ctts offset / media_time * p.

Movie-level durations (mvhd, tkhd, elst segment_duration) are in the movie timescale and are simply
multiplied by r (rounded to the nearest unit).

Audio is NOT retimed in place: AAC scale-factor-band tables depend on the sample rate, so rewriting the rate
corrupts the bitstream (verified with FFmpeg's decoder). Audio is slowed by a separate resample + re-encode of the
audio stream only (see mp4_patcher.patch, audio_mode).
"""
from dataclasses import dataclass
from fractions import Fraction

from core.errors import StudioError

U32 = 0xFFFFFFFF


class TimingError(StudioError):
    pass


@dataclass(frozen=True)
class SlowFactor:
    ratio: Fraction  # new_duration / old_duration

    def __post_init__(self):
        if not (Fraction(1, 32) <= self.ratio <= 32):
            raise TimingError("Speed factor must be between 1/32x and 32x.")

    @property
    def p(self) -> int: return self.ratio.numerator
    @property
    def q(self) -> int: return self.ratio.denominator

    @classmethod
    def from_multiplier(cls, mult) -> "SlowFactor":
        return cls(_snap(Fraction(str(mult))))

    @classmethod
    def from_fps(cls, original_fps: Fraction, target_fps) -> "SlowFactor":
        t = Fraction(str(target_fps))
        if t <= 0:
            raise TimingError("Target FPS must be positive.")
        return cls(_snap(Fraction(original_fps) / t))

    def target_fps(self, original_fps: Fraction) -> Fraction:
        return Fraction(original_fps) / self.ratio

    def scale_movie_units(self, value: int) -> int:
        """Round-half-up scaling of a movie-timescale duration."""
        x = Fraction(value) * self.ratio
        return int(x + Fraction(1, 2))

    def media_plan(self, timescale: int) -> "MediaPlan":
        num = timescale * self.q
        if num % self.p == 0:
            return MediaPlan("timescale", num // self.p, 1)
        new_ts = timescale * self.q
        if new_ts > U32:
            raise TimingError(f"Timescale {timescale} cannot be represented after scaling by {self.ratio}.")
        return MediaPlan("delta", new_ts, self.p)


@dataclass(frozen=True)
class MediaPlan:
    mode: str       # "timescale" | "delta"
    new_timescale: int
    multiplier: int  # applied to sample deltas / ctts / media_time (1 in timescale mode)


def _snap(r: Fraction) -> Fraction:
    """Snap values like 1.998 (59.94/30) to 2, otherwise use a small exact fraction."""
    nearest = round(r)
    if nearest >= 1 and abs(r - nearest) <= Fraction(2, 1000) * nearest:
        return Fraction(nearest)
    return r.limit_denominator(1000)
