"""End-to-end tests of the native MP4 patcher. Needs ffmpeg/ffprobe on PATH (or in ./bin) to create sample files."""
import os
import shutil
import subprocess
import tempfile
import unittest
from fractions import Fraction

from core.ffmpeg_manager import ffmpeg_path
from engines.mp4_patch import mp4_parser as P
from engines.mp4_patch import mp4_patcher as M
from engines.mp4_patch.timing_engine import SlowFactor

FF = ffmpeg_path(required=False)


def make(path, audio=True, rate="60", seconds=2, bframes=2):
    cmd = [FF, "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size=320x180:rate={rate}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100"]
    cmd += ["-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast", "-bf", str(bframes)]
    if audio:
        cmd += ["-c:a", "aac"]
    subprocess.run(cmd + [path], check=True)


@unittest.skipUnless(FF, "ffmpeg not available")
class PatchTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _patch(self, name, factor, **kw):
        src, dst = os.path.join(self.d, name), os.path.join(self.d, "out_" + name)
        return src, dst, M.patch(src, dst, factor, **kw)

    def test_video_only_is_byte_exact_outside_timing_fields(self):
        make(os.path.join(self.d, "v.mp4"), audio=False)
        src, dst, r = self._patch("v.mp4", SlowFactor.from_multiplier(2))
        self.assertTrue(r.report.passed, r.report.text())
        self.assertEqual(r.output_fps, 30)
        self.assertEqual(r.output_duration, 2 * r.original_duration)

    def test_with_audio_video_samples_identical_and_sync(self):
        make(os.path.join(self.d, "av.mp4"))
        src, dst, r = self._patch("av.mp4", SlowFactor.from_multiplier(2))
        self.assertTrue(r.report.passed, r.report.text())
        with open(src, "rb") as a, open(dst, "rb") as b:
            ta = next(t for t in P.read_tracks(a, P.check_supported(P.parse(a))) if t.is_video)
            tb = next(t for t in P.read_tracks(b, P.check_supported(P.parse(b))) if t.is_video)
            self.assertEqual(P.sample_digest(a, ta)[0], P.sample_digest(b, tb)[0])

    def test_ntsc_rate(self):
        make(os.path.join(self.d, "n.mp4"), rate="60000/1001")
        _, _, r = self._patch("n.mp4", SlowFactor.from_fps(Fraction(60000, 1001), 30))
        self.assertTrue(r.report.passed, r.report.text())

    def test_refuses_to_overwrite_source(self):
        make(os.path.join(self.d, "v.mp4"), audio=False)
        p = os.path.join(self.d, "v.mp4")
        with self.assertRaises(Exception):
            M.patch(p, p, SlowFactor.from_multiplier(2))

    def test_rejects_garbage(self):
        p = os.path.join(self.d, "bad.mp4")
        with open(p, "wb") as f:
            f.write(os.urandom(4096))
        with self.assertRaises(Exception):
            M.patch(p, os.path.join(self.d, "o.mp4"), SlowFactor.from_multiplier(2))
        self.assertFalse(os.path.exists(os.path.join(self.d, "o.mp4")))


if __name__ == "__main__":
    unittest.main()
