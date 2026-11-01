"""Elevation rules from the user's redrawn 2026 extended elevations:
overhangs from lines with ticks, pillars the survey goes round, green
strokes carrying a wall on as flowstone."""

import math
import unittest

try:
    from tools.sketch2therion import elevation as el, convert
except ImportError:          # shapely missing
    el = None


@unittest.skipUnless(el, "needs shapely")
class Overhang(unittest.TestCase):
    def test_line_with_ticks_below(self):
        main = [(2.0 - 0.1 * i, 0.0) for i in range(21)]          # drawn right to left
        ticks = [[(0.3 * k, 0.0), (0.3 * k + 0.02, -0.18)] for k in range(1, 6)]
        lines = [('GRAY', main)] + [('GRAY', t) for t in ticks]
        out, rest = el._overhangs(lines)
        self.assertEqual(len(out), 1)
        self.assertEqual(rest, [])
        a, b = out[0][0], out[0][1]
        # ticks below a line running right to left: on its left, kept that way
        self.assertLess(b[0], a[0])

    def test_brown_curls_under_a_floor_are_not_ticks(self):
        floor = [(0.1 * i, 0.0) for i in range(21)]
        curls = [[(0.3 * k, 0.0), (0.3 * k + 0.02, -0.18)] for k in range(1, 6)]
        out, _ = el._overhangs([('BROWN', floor)] + [('BROWN', c) for c in curls])
        self.assertEqual(out, [])


@unittest.skipUnless(el, "needs shapely")
class Pillar(unittest.TestCase):
    def loop(self, cx, cy, r):
        pts = [(cx + r * math.cos(2 * math.pi * i / 16), cy + r * math.sin(2 * math.pi * i / 16)) for i in range(16)]
        return pts + [pts[0]]

    def test_loop_between_legs_above_and_below(self):
        f = el.Features()
        f.rocks = [self.loop(5, 0, 0.5), self.loop(20, 0, 0.5)]
        legs = [((0, 1.5), (10, 1.5)), ((0, -1.5), (10, -1.5)), ((15, -1.5), (25, -1.5))]
        el.pillars_apart(f, legs)
        self.assertEqual(len(f.pillars), 1)       # the first: legs over and under it
        self.assertEqual(len(f.rocks), 1)         # the second: only a leg below, a rock


@unittest.skipUnless(el, "needs shapely")
class GreenWall(unittest.TestCase):
    def test_green_stroke_carrying_a_wall_on(self):
        wall = [(0.0, 0.0), (2.0, 0.0)]
        green = [(2.1, 0.0), (4.0, 0.1)]
        stray = [(8.0, 3.0), (10.0, 3.0)]
        out = convert.green_walls([('GREEN', green), ('GREEN', stray)], [wall])
        self.assertEqual(out, [green])


if __name__ == "__main__":
    unittest.main()
