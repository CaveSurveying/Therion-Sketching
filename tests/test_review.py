"""tools/sketch2therion review: the parts that need no Therion."""

import math
import os
import unittest

from tools.sketch2therion.project import REPO     # the test cave

try:
    import numpy  # noqa: F401
    from tools.sketch2therion import review
except ImportError:
    review = None


@unittest.skipUnless(review, "needs shapely and numpy")
class ReviewConfigTest(unittest.TestCase):
    def test_needs_a_plan_export(self):
        with self.assertRaises(ValueError):
            review.review_config("source x.th\nexport model -o x.3d\n", "o.pdf")


@unittest.skipUnless(review, "needs shapely and numpy")
class CalibrateTest(unittest.TestCase):
    def page(self, x, y, scale=500, rot=45, shift=(300.0, 200.0)):
        k = 72 / 25.4 * 1000 / scale
        th = math.radians(rot)
        return (shift[0] + k * (math.cos(th) * x - math.sin(th) * y),
                shift[1] - k * (math.sin(th) * x + math.cos(th) * y))

    def test_finds_transform_despite_repeated_names(self):
        # Stations 1-6 in two surveys; only survey A's names are printed.
        a = {str(i): (10.0 * i, 3.0 * i) for i in range(1, 7)}
        b = {str(i): (-40.0 + 7 * i, 25.0 - 2 * i) for i in range(1, 7)}
        names = {n: [a[n], b[n]] for n in a}
        words = [(*self.page(*a[n]), n) for n in a] + [(10.0, 10.0, "Colossus")]
        to_page = review.calibrate(words, names, 500, 45)
        for n, p in a.items():
            got, want = to_page(p), self.page(*p)
            self.assertAlmostEqual(got[0], want[0], places=3)
            self.assertAlmostEqual(got[1], want[1], places=3)
        self.assertAlmostEqual(review.page_angle(to_page), math.radians(45), places=6)

    def test_other_rotation_sign(self):
        a = {str(i): (5.0 * i, -2.0 * i * i) for i in range(1, 6)}
        words = [(*self.page(*a[n], rot=-30), n) for n in a]
        to_page = review.calibrate(words, {n: [p] for n, p in a.items()}, 500, 30)
        self.assertAlmostEqual(to_page(a["3"])[0], self.page(*a["3"], rot=-30)[0], places=3)

    def test_no_names_on_page(self):
        with self.assertRaises(ValueError):
            review.calibrate([(1.0, 1.0, "Colossus")], {"1": [(0.0, 0.0)]})

    def test_turn(self):
        x, y = review._turn((1.0, 0.0), math.pi / 2)
        self.assertAlmostEqual(x, 0.0)
        self.assertAlmostEqual(y, 1.0)


@unittest.skipUnless(review, "needs shapely and numpy")
class SketchesForTest(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        os.chdir(REPO)
        self.addCleanup(os.chdir, self.cwd)

    def test_plan_view_only_plan_sketches_of_the_survey(self):
        files = review.sketches_for(["1", "2", "3"], "plan", survey="GoSouth")
        self.assertTrue(files)
        self.assertTrue(all("/GoSouth/" in f for f in files))
        self.assertTrue(all(review.PROJECT.is_plan_sketch(f) for f in files))

    def test_elevation_view(self):
        files = review.sketches_for(["1", "2"], "elevation", survey="GoSouth")
        self.assertTrue(files)
        self.assertFalse(any(review.PROJECT.is_plan_sketch(f) for f in files))


if __name__ == "__main__":
    unittest.main()
