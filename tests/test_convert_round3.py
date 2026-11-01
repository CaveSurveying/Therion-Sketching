"""Converter changes from the GoSouth draft 2 review: notation, guessed
steps, smoothing, gours, line ends on wall nodes, water, review sheets."""

import math
import os
import unittest

try:
    from shapely.geometry import LineString, Polygon
    from tools.sketch2therion import notation, marks, nodes, floor, settings, tidy, review, xvi
except ImportError:
    notation = None

from tools.sketch2therion.project import REPO     # the test cave
THERION_LINES = {"wall", "border", "floor-step", "pit", "overhang", "ceiling-step", "rock-border", "rock-edge",
                 "rimstone-dam", "rimstone-pool", "flowstone", "chimney", "slope", "contour", "label", "section",
                 "water-flow", "gradient", "arrow", "survey"}


def ticked(side=+1, n=4):
    """A 3 m line along x with n ticks on its left (+1) or right (-1)."""
    line = [(x / 10, 0.0) for x in range(31)]
    ticks = [[(0.5 + k * 0.6, 0.0), (0.5 + k * 0.6, 0.2 * side)] for k in range(n)]
    return line, ticks


@unittest.skipUnless(notation, "needs shapely")
class NotationTest(unittest.TestCase):
    def test_ticked_line_is_a_step_ticks_on_left(self):
        for side in (+1, -1):
            line, ticks = ticked(side)
            feats, used = notation.find([("BROWN", line)] + [("BROWN", t) for t in ticks])
            self.assertEqual([k for k, _, _ in feats], ["step"])
            pts = feats[0][1]
            # Therion puts ticks on the left of the direction: low side (the ticks) on the left
            d = (pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])
            left_is_up = d[0] > 0
            self.assertEqual(left_is_up, side > 0)
            self.assertEqual(len(used), 1 + len(ticks))

    def test_one_tick_is_not_a_step(self):
        line, ticks = ticked(n=1)
        feats, _ = notation.find([("GRAY", line), ("GRAY", ticks[0])])
        self.assertEqual(feats, [])

    def test_dashed_with_ticks_is_overhang(self):
        dashes = [[(k * 0.5, 0.0), (k * 0.5 + 0.25, 0.0)] for k in range(5)]
        ticks = [[(k * 0.5 + 0.12, 0.0), (k * 0.5 + 0.12, -0.15)] for k in range(5)]
        feats, used = notation.find([("GRAY", d) for d in dashes] + [("GRAY", t) for t in ticks])
        self.assertEqual([k for k, _, _ in feats], ["overhang"])
        self.assertEqual(len(used), 10)

    def test_overhang_pieces_joined_through_the_turn(self):
        down = [[(0.0, -k * 0.5), (0.0, -k * 0.5 - 0.25)] for k in range(5)]          # x = 0, going down
        up = [[(0.8, -k * 0.5 - 0.25), (0.8, -k * 0.5)] for k in range(5)]            # x = 0.8
        tick_d = [[(0.0, -k * 0.5 - 0.12), (-0.15, -k * 0.5 - 0.12)] for k in range(5)]
        tick_u = [[(0.8, -k * 0.5 - 0.12), (0.95, -k * 0.5 - 0.12)] for k in range(5)]
        turn = [[(0.2, -2.7), (0.6, -2.7)]]                                            # the dash at the bottom
        lines = [("GRAY", p) for p in down + up + tick_d + tick_u + turn]
        feats, _ = notation.find(lines)
        self.assertEqual([k for k, _, _ in feats], ["overhang"])

    def test_dashes_without_ticks_are_not_overhang(self):
        dashes = [[(k * 0.5, 0.0), (k * 0.5 + 0.25, 0.0)] for k in range(5)]
        feats, _ = notation.find([("GRAY", d) for d in dashes])
        self.assertEqual(feats, [])

    def test_gosouth_sketch(self):
        s = xvi.read(os.path.join(REPO, "TestCave", "GoSouth", "Notes", "GoSouthP.xvi"))
        feats, _ = notation.find(s.lines)
        kinds = sorted(k for k, _, _ in feats)
        # the two overhang pieces are one; the two short ticked lines by 17 to 18 are steps too
        self.assertEqual(kinds, ["overhang", "step", "step", "step", "step", "step", "step"])

    def test_pitch_from_elevation(self):
        passage = Polygon([(-1, -2), (4, -2), (4, 2), (-1, 2)])
        line, _ = ticked()
        out = notation.th2([("step", line, "BROWN")], passage, lambda p: p, [((1.5, 0.5), 3.0)], 2.0)
        self.assertEqual(out[0], "line pit")
        out = notation.th2([("step", line, "BROWN")], passage, lambda p: p, [((1.5, 0.5), 1.0)], 2.0)
        self.assertEqual(out[0], "line floor-step")


@unittest.skipUnless(notation, "needs shapely")
class GuessedStepTest(unittest.TestCase):
    def tearDown(self):
        settings.load()

    def run_floor(self, height, notes=()):
        # the guessing itself (other caves); LongwoodValleySink turns elevation data off
        settings.use({"elevation_step_min": 1.0, "pitch_min": 2.0, "climb_whole": True})
        data = {"climbs": [("1", "2", 0.5, height)], "gradients": []}
        stations = {"1": (0.0, 0.0), "2": (10.0, 0.0)}
        passage = Polygon([(-1, -2), (11, -2), (11, 2), (-1, 2)])
        return "\n".join(floor.th2(data, stations, passage, lambda p: p, [], notes))

    def test_small_drop_label_only(self):
        out = self.run_floor(0.96)
        self.assertNotIn("line floor-step", out)
        self.assertIn('label -text "C1m"', out)

    def test_big_drop_guessed(self):
        self.assertIn("line floor-step", self.run_floor(1.4))
        self.assertIn("line pit", self.run_floor(3.2))

    def test_notation_near_wins(self):
        out = self.run_floor(3.2, [LineString([(4.5, -1), (5.5, 1)])])
        self.assertNotIn("line pit", out)
        self.assertIn('label -text "C3m"', out)


@unittest.skipUnless(notation, "needs shapely")
class OnlyWhatIsDrawnTest(unittest.TestCase):
    def tearDown(self):
        settings.load()

    def test_cave_ignores_elevation_data(self):
        settings.load()
        self.assertFalse(settings.SETTINGS["elevation_data"])

    def test_lone_marks_ignored_groups_are_sand(self):
        settings.load()
        # the size rules, on the marks' own extent (mud patches grown round their marks: test_scraps)
        settings.use(dict(settings.SETTINGS, mud_grow=0.0, mud_near=0.0, dash_max=0.0, rock_curves=False,
                          area_grow=0.0, area_inside_min=0.0))
        passage = Polygon([(-3, -3), (3, -3), (3, 3), (-3, 3)])
        tiny = lambda x, y: [(x + 0.05 * math.cos(a), y + 0.05 * math.sin(a)) for a in range(7)] + [(x + 0.05, y)]
        _, areas, _ = marks.brown([tiny(0, 0)], passage, 0.6)
        self.assertEqual(areas, [])                                   # one mark: dirt, ignored
        group = [tiny(x * 0.35, y * 0.35) for x in range(4) for y in range(4)]   # 1 m square of dirt
        _, areas, _ = marks.brown(group, passage, 0.6)
        self.assertEqual([k for k, _ in areas], ["sand"])
        _, areas, _ = marks.brown([tiny(0, 0), tiny(0.3, 0), tiny(0.15, 0.25)], passage, 0.6)
        self.assertEqual(areas, [])                                   # too small to draw sand in
        _, areas, _ = marks.brown([[(0, 0), (0.2, 0.01), (0.4, 0)]], passage, 0.6)
        self.assertEqual(areas, [])                                   # one dash: ignored


class RockEdgeTest(unittest.TestCase):
    def tearDown(self):
        settings.load()

    def edges(self, size):
        from tools.sketch2therion import details
        settings.load()
        K = 100.0
        r = size * K / 2
        ring = [(r * math.cos(2 * math.pi * i / 7), r * math.sin(2 * math.pi * i / 7)) for i in range(7)]
        o = tidy.Obj("line", "line rock-border -close on", [])
        o.set_segments([[x, y] for x, y in ring + [ring[0]]])
        objs = [o]
        details.boulders(objs, K)
        return objs[0], [x for x in objs[1:] if x.head == "line rock-edge"]

    def test_edges_inside_ending_on_corners(self):
        # a rock's edges (block, peak or ridge, the user 2026-10-09) lie inside it, each with an
        # end on one of its corners, and come after it in the file
        for size in (0.6, 1.4, 2.2):
            border, edges = self.edges(size)
            self.assertTrue(edges, size)
            corners = {(round(s[-2], 2), round(s[-1], 2)) for s in border.segments()}
            ring = Polygon([tuple(s[-2:]) for s in border.segments()]).buffer(0.5)
            for e in edges:
                ends = [(round(s[-2], 2), round(s[-1], 2)) for s in (e.segments()[0], e.segments()[-1])]
                self.assertTrue(any(x in corners for x in ends), (size, ends))
                self.assertTrue(ring.contains(LineString([tuple(s[-2:]) for s in e.segments()])), size)

    def test_styles_vary_from_rock_to_rock(self):
        from tools.sketch2therion import details
        settings.load()
        K = 100.0
        shapes = set()
        for i in range(12):
            ring = [(i * 300 + 60 * math.cos(2 * math.pi * k / 7), 60 * math.sin(2 * math.pi * k / 7))
                    for k in range(7)]
            corners, edges = details.rock(ring + [ring[0]], K)
            shapes.add(tuple(len(e) for e in edges))
        self.assertGreater(len(shapes), 1)                            # not all drawn alike


class SmoothAndGourTest(unittest.TestCase):
    def test_points_only_at_bends(self):
        settings.load()
        pp = [(x / 100, math.sin(x / 100)) for x in range(400)]          # a gentle 4 m curve
        rows = marks.smooth_rows(pp, lambda p: p)
        self.assertLess(len(rows), 9)                                   # not hundreds of points
        self.assertGreater(len(rows), 2)
        wobbly = [(x / 100, 0.02 * (-1) ** x) for x in range(300)]       # straight, hand wobble
        self.assertEqual(len(marks.smooth_rows(wobbly, lambda p: p)), 2)

    def test_corner_kept(self):
        settings.load()
        pp = [(x / 20, 0.0) for x in range(21)] + [(1.0, y / 20) for y in range(1, 21)]
        self.assertGreaterEqual(len(marks.smooth_rows(pp, lambda p: p)), 3)

    def test_gour_or_formation(self):
        self.assertTrue(marks.is_gour([(0, 0), (0.5, 0.2), (1.0, 0.0)]))
        curl = [(math.cos(a / 10) * 0.3, math.sin(a / 10) * 0.3) for a in range(50)]
        self.assertFalse(marks.is_gour(curl))

    def test_area_stops_at_barrier(self):
        passage = Polygon([(-3, -3), (3, -3), (3, 3), (-3, 3)])
        loops = [[(x + 0.1 * math.cos(a), y + 0.1 * math.sin(a)) for a in range(7)] for x, y in
                 [(1.0, 0.0), (1.4, 0.3), (1.2, -0.4)]]
        loops = [l + [l[0]] for l in loops]
        settings.load()
        _, areas, _ = marks.brown(loops, passage, 0.6, [LineString([(0.5, -3), (0.5, 3)])])
        self.assertTrue(areas)
        self.assertGreaterEqual(min(x for k, g in areas for x, _ in g.exterior.coords), 0.5)


@unittest.skipUnless(notation, "needs shapely")
class NodeTest(unittest.TestCase):
    def wall(self):
        return tidy.Obj("line", "line wall", ["  0.00 0.00", "  100.00 0.00", "  200.00 0.00"])

    def test_end_put_on_new_node(self):
        w, b = self.wall(), tidy.Obj("line", "line border", ["  50.00 100.00", "  50.00 10.00"])
        self.assertEqual(nodes.snap_scrap([w, b], 100.0), 1)
        self.assertEqual(b.segments()[-1][-2:], [50.0, 0.0])
        self.assertIn([50.0, 0.0], [s[-2:] for s in w.segments()])

    def test_existing_node_used(self):
        w, b = self.wall(), tidy.Obj("line", "line border", ["  98.00 100.00", "  98.00 3.00"])
        nodes.snap_scrap([w, b], 100.0)
        self.assertEqual(b.segments()[-1][-2:], [100.0, 0.0])
        self.assertEqual(len(w.segments()), 3)

    def test_far_end_left(self):
        w, b = self.wall(), tidy.Obj("line", "line border", ["  50.00 100.00", "  50.00 40.00"])
        self.assertEqual(nodes.snap_scrap([w, b], 100.0), 0)

    def test_split_keeps_curve(self):
        a, b = nodes.split_segment((0, 0), [0, 10, 10, 10, 10, 0], 0.5)
        self.assertEqual(a[-2:], [5.0, 7.5])
        self.assertEqual(b[-2:], [10, 0])


@unittest.skipUnless(notation, "needs shapely")
class WaterAndAreasTest(unittest.TestCase):
    def tearDown(self):
        settings.load()

    def scrap(self):
        return ("encoding  utf-8\nscrap XSP1 -projection plan\n"
                "line wall -subtype invisible -close on\n  0 0\n  400 0\n  400 400\n  0 400\n  0 0\nendline\n"
                "line border -id XSP1-water1 -close on -clip off\n  100 100\n  150 100\n  150 150\n  100 150\nendline\n"
                "area water -clip off\n  XSP1-water1\nendarea\n"
                "line border -subtype invisible -id XSP1-debris1 -close on\n  200 200\n  230 200\n  230 230\nendline\n"
                "area debris\n  XSP1-debris1\nendarea\n"
                "endscrap\n")

    def test_debris_border_not_treated_as_water(self):
        settings.load()
        out = tidy.tidy_text(self.scrap())
        self.assertIn("area debris", out)
        self.assertIn("XSP1-debris1", out)


@unittest.skipUnless(notation, "needs shapely")
class LineTypesTest(unittest.TestCase):
    def test_converter_writes_therion_line_types(self):
        import glob
        src = "".join(open(f, encoding="utf-8").read()
                      for f in glob.glob(os.path.join(REPO, "tools", "sketch2therion", "*.py"))
                      if os.path.basename(f) != "th2lint.py")      # its messages are not line types
        import re
        used = set(re.findall(r'"line ([a-z-]+)', src)) | set(re.findall(r"'line ([a-z-]+)", src))
        self.assertLessEqual(used, THERION_LINES, used - THERION_LINES)


if __name__ == "__main__":
    unittest.main()
