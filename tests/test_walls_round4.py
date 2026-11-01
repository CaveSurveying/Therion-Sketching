"""Converter changes from the GoSouth draft 4 review: outer walls the
passage fill bridged, a wall drawn on through the passage with a border
off it, walls joined through overlaps without steps or zigzags, refits
kept close to the sketch, borders joined across the sketcher's gaps."""

import contextlib
import io
import math
import os
import re
import shutil
import tempfile
import unittest

try:
    from shapely.geometry import LineString, Point, Polygon
    from tools.sketch2therion import convert, jogs, nodes, settings, smooth, tidy
except ImportError:
    convert = None

from tools.sketch2therion.project import REPO     # the test cave
PROJECT = {"interior_borders": True, "smooth_lines": False, "join_local": True}


def segs_of(rows):
    return [list(r) for r in rows]


@unittest.skipUnless(convert, "needs shapely")
class OuterWallTest(unittest.TestCase):
    """cut_back and the tests it uses: the fill cut back to an outer wall it bridged."""

    def setUp(self):
        settings.use(PROJECT)

    def tearDown(self):
        settings.use({})

    def test_splay_supported(self):
        run = [(0.0, 0.0), (4.0, 0.0)]
        self.assertTrue(convert.splay_supported(run, [(1.0, 0.1), (3.0, -0.1)]))
        self.assertFalse(convert.splay_supported(run, [(1.0, 0.1)]))              # one is not enough
        self.assertFalse(convert.splay_supported(run, [(1.0, 1.0), (3.0, 1.0)]))  # too far off

    def test_traced_outer_finds_the_side_away_from_the_legs(self):
        # the fill reaches 1 m past the wall at y = 0; the leg is at y = -2
        poly = Polygon([(-1, -3), (5, -3), (5, 1), (-1, 1)])
        legs = LineString([(0, -2), (4, -2)])
        side, width = convert.traced_outer([(0.0, 0.0), (4.0, 0.0)], poly, LineString(), legs)
        self.assertEqual(side, 1)                       # left of the stroke's direction: +y
        self.assertAlmostEqual(width, 1.0, delta=0.1)

    def test_traced_outer_none_through_a_pillar(self):
        # another wall stroke beyond: tracing out meets it (a pillar's far wall)
        poly = Polygon([(-1, -3), (5, -3), (5, 3), (-1, 3)])
        legs = LineString([(0, -2), (4, -2)])
        far = LineString([(-1, 1.5), (5, 1.5)])
        self.assertIsNone(convert.traced_outer([(0.0, 0.0), (4.0, 0.0)], poly, far, legs))

    def test_cut_back_puts_the_wall_on_the_edge(self):
        poly = Polygon([(-1, -3), (5, -3), (5, 1), (-1, 1)])
        walls = [[(0.0, 0.0), (4.0, 0.0)]]
        legs = [[(0.0, -2.0), (4.0, -2.0)]]
        cut = convert.cut_back(poly, walls, legs, [])
        self.assertFalse(cut.contains(Point(2, 0.5)))       # nothing left beyond the wall
        self.assertTrue(cut.contains(Point(2, -2)))         # the passage is kept
        self.assertLess(cut.exterior.distance(Point(2, 0)), 0.15)   # the wall is on the edge

    def test_cut_back_keeps_a_strip_with_a_leg_in_it(self):
        poly = Polygon([(-1, -3), (5, -3), (5, 1), (-1, 1)])
        walls = [[(0.0, 0.0), (4.0, 0.0)]]
        legs = [[(0.0, -2.0), (4.0, -2.0)], [(2.0, -2.0), (2.0, 0.8)]]   # a leg goes out past it
        self.assertTrue(convert.cut_back(poly, walls, legs, []).equals(poly))


@unittest.skipUnless(convert, "needs shapely")
class WallRunsTest(unittest.TestCase):
    """wall_runs: a stroke mostly along the fill's edge is wall all along."""

    # the fill: a 6 m x 4 m passage; the stroke runs along its top edge
    # for 5 m, then 1 m down into it
    POLY = Polygon([(0, 0), (6, 0), (6, 4), (0, 4)])
    STROKE = [(0.0, 4.0), (2.0, 4.0), (5.0, 4.0), (5.0, 3.5), (5.0, 3.0), (5.0, 2.5)]
    STEP = [(1.0, 1.0), (1.5, 1.5), (2.0, 2.0), (2.5, 2.5)]       # a line inside, on its own

    def tearDown(self):
        settings.use({})

    def kinds(self):
        out = []
        for wall, run in convert.wall_runs([self.STROKE, self.STEP], self.POLY):
            out.append((wall, round(LineString(run).length, 1)))
        return sorted(out)

    def test_upstream_splits_the_stroke(self):
        settings.use({})
        self.assertIn((False, 1.0), [(w, round(l)) for w, l in self.kinds()])

    def test_project_keeps_the_whole_stroke_wall(self):
        settings.use(PROJECT)
        k = self.kinds()
        self.assertEqual(sum(1 for w, _ in k if w), len([x for x in k if x[1] >= 5.0]) + 1)
        self.assertNotIn(False, [w for w, l in k if l >= 0.9 and l <= 1.1])
        self.assertIn((False, 2.1), k)                 # the line on its own inside stays a border


@unittest.skipUnless(convert, "needs shapely")
class JoinTest(unittest.TestCase):
    """Joining walls: refits stay within TOL, only near the join; zigzags go."""

    K = 78.74

    def test_doubles_back(self):
        p0 = (0.0, 0.0)
        self.assertTrue(jogs.doubles_back(p0, [1.0, 0.5, -3.0, 0.5, 10.0, 0.0]))   # second control point behind
        self.assertFalse(jogs.doubles_back(p0, [3.0, 1.0, 7.0, 1.0, 10.0, 0.0]))
        self.assertFalse(jogs.doubles_back(p0, [10.0, 0.0]))

    def test_unzigzag_straightens_only_the_bad_segment(self):
        segs = [[0.0, 0.0], [3.0, 1.0, 7.0, 1.0, 10.0, 0.0], [11.0, 0.5, -2.0, 0.5, 20.0, 0.0]]
        self.assertEqual(jogs.unzigzag(segs), 1)
        self.assertEqual(segs[1], [3.0, 1.0, 7.0, 1.0, 10.0, 0.0])
        self.assertEqual(segs[2], [20.0, 0.0])

    def test_fit_within_tolerance(self):
        # a long gentle curve: the fit must not stray more than TOL from it
        K = self.K
        pts = [[x * K / 10, (0.004 * (x - 50) ** 2) * K / 10] for x in range(101)]
        segs = smooth._fit_within(pts, K)
        line = LineString([p for p in pts])
        worst = max(line.distance(Point(p)) for p in tidy.bezier_points(segs, 20))
        self.assertLessEqual(worst, smooth.TOL * K + 1e-6)

    def test_join_local_keeps_far_nodes(self):
        K = self.K
        sa = [[0.0, 0.0]] + [[x * K, 0.0] for x in range(1, 6)]               # 5 m along x, a node a metre
        sb = [[5.2 * K, 0.1 * K]] + [[(5.2 + x) * K, 0.1 * K] for x in range(1, 6)]
        segs = smooth._join_local(sa, sb, (5 * K, 0.0), (5.2 * K, 0.1 * K), K)
        ends = [tuple(round(v, 6) for v in s[-2:]) for s in segs]
        for kept in [(0.0, 0.0), (K, 0.0), (2 * K, 0.0), (3 * K, 0.0)]:        # more than 1 m before the join
            self.assertIn(tuple(round(v, 6) for v in kept), ends)
        for kept in [(7.2 * K, 0.1 * K), (8.2 * K, 0.1 * K), (10.2 * K, 0.1 * K)]:
            self.assertIn(tuple(round(v, 6) for v in kept), ends)
        self.assertTrue(LineString(tidy.bezier_points(segs, 8)).is_simple)


@unittest.skipUnless(convert, "needs shapely")
class BorderJoinTest(unittest.TestCase):
    """join_runs: border pieces carrying on across a small gap are one line."""

    def obj(self, pts):
        o = tidy.Obj('line', 'line border', [])
        o.set_segments([[x, y] for x, y in pts])
        return o

    def test_joined_across_gap(self):
        K = 78.74
        objs = [self.obj([(0, 0), (K, 0)]), self.obj([(1.2 * K, 0), (2 * K, 0)])]
        self.assertEqual(nodes.join_runs(objs, K), 1)
        self.assertEqual(len([o for o in objs if o.kind == 'line']), 1)

    def test_not_joined_round_a_corner(self):
        K = 78.74
        objs = [self.obj([(0, 0), (K, 0)]), self.obj([(1.1 * K, 0.1 * K), (1.1 * K, K)])]
        self.assertEqual(nodes.join_runs(objs, K), 0)


@unittest.skipUnless(convert, "needs shapely")
class GoSouthStation21Test(unittest.TestCase):
    """The GoSouth plan through plan and smooth: near station 21 the upper
    wall is one wall (strokes 182, 192 and 194 of the sketch), stroke 148
    beside it is a wall too (an outer line), and the lower wall has no step."""

    @classmethod
    def setUpClass(cls):
        from tools.sketch2therion.__main__ import main
        settings.load()                     # the project's settings (other tests leave upstream's)
        cls.tmp = tempfile.mkdtemp()
        out = os.path.join(cls.tmp, "g.th2")
        sketch = os.path.join(REPO, "TestCave", "GoSouth", "Notes", "GoSouthP.xvi")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            main(["plan", sketch, "--survey", "GoSouth", "-o", out])
        smooth.redo_file(out)
        text = open(out, encoding="utf-8").read()
        # every scrap: station 21 is in GoSouthSP2 since the scraps were chosen by hand
        cls.objs = [o for body in re.findall(r"(?ms)^scrap GoSouthSP\d[^\n]*\n(.*?)^endscrap", text)
                    for o in tidy.parse_scrap(body)]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)
        settings.use({})

    def lines(self, kind):
        return [LineString(tidy.bezier_points(o.segments(), 8)) for o in self.objs
                if o.kind == 'line' and o.head.split()[1] == kind and '-subtype invisible' not in o.head
                and len(o.segments()) > 1]

    def test_upper_wall_continuous_past_station_21(self):
        K = 78.74
        # points on strokes 182 and 192 of the sketch (sketch units)
        walls = self.lines('wall')
        for p in [(450, -1395), (520, -1411), (600, -1457)]:
            self.assertLess(min(w.distance(Point(p)) for w in walls), 0.15 * K, p)

    def test_stroke_148_a_wall(self):
        # stroke 148 was a border off the upper wall (round 4); the user has since confirmed the
        # lines near 16 and 21 are walls (2026-10-09, log row 141): every outer line is a wall
        K = 78.74
        walls = self.lines('wall')
        self.assertLess(min(w.distance(Point(470, -1385)) for w in walls), 0.15 * K)   # stroke 148

    def test_lower_wall_follows_the_sketch(self):
        K = 78.74
        walls = self.lines('wall')
        # stroke 193 at x = 500 and stroke 195 just past station 22
        for p in [(502, -1508), (580, -1541), (700, -1597)]:
            self.assertLess(min(w.distance(Point(p)) for w in walls), 0.15 * K, p)


if __name__ == "__main__":
    unittest.main()
