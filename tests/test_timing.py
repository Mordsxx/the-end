import unittest
from fractions import Fraction

from engines.mp4_patch.timing_engine import SlowFactor, TimingError


class TimingTests(unittest.TestCase):
    def test_multiplier(self):
        f = SlowFactor.from_multiplier(2)
        self.assertEqual((f.p, f.q), (2, 1))
        self.assertEqual(f.media_plan(15360).new_timescale, 7680)
        self.assertEqual(f.media_plan(15360).mode, "timescale")

    def test_ntsc_snaps_to_exact_2x(self):
        f = SlowFactor.from_fps(Fraction(60000, 1001), 30)
        self.assertEqual(f.ratio, 2)

    def test_delta_mode_when_not_divisible(self):
        f = SlowFactor.from_multiplier(2)
        plan = f.media_plan(25)           # 25*1 % 2 != 0
        self.assertEqual((plan.mode, plan.new_timescale, plan.multiplier), ("delta", 25, 2))

    def test_fractional_ratio(self):
        f = SlowFactor.from_multiplier("1.5")
        self.assertEqual(f.ratio, Fraction(3, 2))
        self.assertEqual(f.scale_movie_units(1000), 1500)

    def test_out_of_range(self):
        with self.assertRaises(TimingError):
            SlowFactor.from_multiplier(100)


if __name__ == "__main__":
    unittest.main()
