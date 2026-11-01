"""The cave-specific converter settings: brown floor marks, interior
borders, wall steps, pools and whole-metre labels."""

import math
import os
import unittest

try:
    from shapely.geometry import Polygon
    from tools.sketch2therion import settings, marks, jogs, features, floor, tidy
except ImportError:          # shapely missing
    settings = None



def loop(cx, cy, r, n=12):
    pts = [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    return pts + [pts[0]]


@unittest.skipUnless(settings, "needs shapely")
class SettingsTest(unittest.TestCase):
    def tearDown(self):
        settings.load()

    def test_cave_settings_loaded(self):
        settings.load()
        self.assertEqual(settings.SETTINGS["wall_colours"], ["BLACK"])
        self.assertEqual(settings.SETTINGS["brown"], "floor")
        self.assertTrue(settings.SETTINGS["climb_whole"])

    def test_house_rules_then_cave(self):
        # the cave's [convert] changes a house rule; the rest stay
        from tools.sketch2therion import project
        p = project.load()
        p.convert = {"boulder_min": 0.5}
        settings.load(p)
        self.assertEqual(settings.SETTINGS["boulder_min"], 0.5)
        self.assertEqual(settings.SETTINGS["wall_colours"], ["BLACK"])
        self.assertEqual(settings.house_rules()["boulder_min"], 0.3)

    def test_empty_is_upstream(self):
        settings.use({})
        self.assertEqual(settings.SETTINGS, settings.UPSTREAM)

    def test_unknown_and_bad_values(self):
        with self.assertRaisesRegex(ValueError, "unknown nope"):
            settings.use({"nope": 1})
        with self.assertRaisesRegex(ValueError, "brown"):
            settings.use({"brown": "mud"})


@unittest.skipUnless(settings, "needs shapely")
class BrownTest(unittest.TestCase):
    # the basic brown reading, without the cave's area and mark settings
    def setUp(self):
        settings.use({"brown": "floor"})

    def tearDown(self):
        settings.load()

    def test_kind_of(self):
        self.assertEqual(marks.kind_of([(0, 0), (0.05, 0.02)], 0.6), "sand")              # a dot
        self.assertEqual(marks.kind_of(loop(0, 0, 0.15), 0.6), "debris")                 # small loop
        self.assertEqual(marks.kind_of(loop(0, 0, 0.5), 0.6), "boulder")                 # 1 m across
        self.assertEqual(marks.kind_of([(0, 0), (0.15, 0.01), (0.3, 0.0)], 0.6), "sand")  # a dash: mud, drawn as sand
        self.assertEqual(marks.kind_of([(0, 0), (1, 0.4), (2, 0)], 0.6), "line")          # a step in mud

    def test_areas_need_enough_marks(self):
        passage = Polygon([(-5, -5), (5, -5), (5, 5), (-5, 5)])
        dots = [[(x, 0), (x + 0.03, 0.01)] for x in (0.0, 0.2, 0.4)]
        _, areas, _ = marks.brown(dots, passage, 0.6)
        self.assertEqual([k for k, _ in areas], ["sand"])
        _, areas, _ = marks.brown(dots[:2], passage, 0.6)
        self.assertEqual(areas, [])
        _, areas, _ = marks.brown([loop(1, 1, 0.15)], passage, 0.6)
        self.assertEqual([k for k, _ in areas], ["debris"])

    def test_th2(self):
        passage = Polygon([(-5, -5), (5, -5), (5, 5), (-5, 5)])
        lines = [("BROWN", loop(0, 0, 0.6)), ("BROWN", loop(3, 3, 0.15)),
                 ("GRAY", [(-4, -4), (-2, -3), (0, -4)]), ("BLUE", [(-4, 4), (0, 4)]), ("BLACK", [(-4, 2), (4, 2)])]
        text = "\n".join(marks.th2(lines, passage, lambda p: p, "S1", ["BLACK"], 0.6))
        rock = text[text.index("line rock-border -close on"):text.index("endline")].strip().split("\n")[1:]
        self.assertEqual(rock[0], rock[-1])                          # ends on its first point
        self.assertIn("line border -subtype invisible -id S1-debris1 -close on", text)
        self.assertIn("area debris\n  S1-debris1\nendarea", text)
        self.assertEqual(text.count("\nline border\n"), 1)           # the grey line only
        self.assertNotIn("4.00 2.00", text)                         # black is a wall, not interior

    def test_interior_excludes(self):
        passage = Polygon([(-5, -5), (5, -5), (5, 5), (-5, 5)])
        lines = [("GRAY", [(0, 0), (1, 0)]), ("GREEN", [(0, 1), (1, 1)]), ("BROWN", [(0, 2), (1, 2)]),
                 ("BLACK", [(0, 3), (1, 3)]), ("GRAY", [(0, 4), (0.1, 4)])]
        self.assertEqual(len(marks.interior(lines, passage, ["BLACK"])), 1)


@unittest.skipUnless(settings, "needs shapely")
class JogTest(unittest.TestCase):
    def test_z_step_found(self):
        pts = [(0, 0), (10, 0), (10, -3), (20, -3)]
        self.assertEqual(jogs.jogs(pts, 5), [1])

    def test_bend_and_long_piece_not(self):
        self.assertEqual(jogs.jogs([(0, 0), (10, 0), (13, -2), (20, -6)], 5), [])     # a gentle bend
        self.assertEqual(jogs.jogs([(0, 0), (10, 0), (10, -30), (20, -30)], 5), [])   # too long: a real corner
        self.assertEqual(jogs.jogs([(0, 0), (10, 0), (10, -3), (10, -20)], 5), [])    # turns and keeps going

    def test_join(self):
        o = tidy.Obj("line", "line wall", ["  0.00 0.00", "  10.00 0.00", "  10.00 -3.00", "  20.00 -3.00"])
        self.assertEqual(jogs.join_scrap([o], 1.0, 5), 1)
        self.assertEqual(o.rows, ["  0.00 0.00", "  10.00 -1.50", "  20.00 -3.00"])

    def test_join_keeps_curves(self):
        o = tidy.Obj("line", "line wall", ["  0.00 0.00", "  3.00 1.00 7.00 1.00 10.00 0.00", "  10.00 -3.00",
                                           "  13.00 -4.00 17.00 -4.00 20.00 -3.00"])
        jogs.join_scrap([o], 1.0, 5)
        self.assertEqual(o.rows, ["  0.00 0.00", "  3.00 1.00 7.00 1.00 10.00 -1.50",
                                  "  13.00 -4.00 17.00 -4.00 20.00 -3.00"])

    def test_end_piece_dropped(self):
        o = tidy.Obj("line", "line wall", ["  0.00 3.00", "  0.00 0.00", "  10.00 0.00", "  20.00 0.00"])
        jogs.join_scrap([o], 1.0, 5)
        self.assertEqual(o.rows, ["  0.00 0.00", "  10.00 0.00", "  20.00 0.00"])

    def test_end_step(self):
        self.assertEqual(jogs.jogs([(0, 3), (0, 0), (10, 0), (20, 0)], 5), [0])


@unittest.skipUnless(settings, "needs shapely")
class PoolTest(unittest.TestCase):
    def tearDown(self):
        settings.load()

    def test_small_closed_blue_is_a_pool(self):
        blue = [("BLUE", loop(0, 0, 0.25, 16))]                      # about 0.2 m2
        settings.load()
        pools, flows, _ = features.classify(blue)
        self.assertEqual((len(pools), len(flows)), (1, 0))
        settings.use({})                                             # upstream: too small, a flow arrow
        pools, flows, _ = features.classify(blue)
        self.assertEqual((len(pools), len(flows)), (0, 1))


@unittest.skipUnless(settings, "needs shapely")
class LabelTest(unittest.TestCase):
    def tearDown(self):
        settings.load()

    def test_whole_metres_half_up(self):
        settings.load()
        self.assertEqual([floor._label(h) for h in (0.3, 1.5, 2.5, 3.4, 3.5)], ["C1m", "C2m", "C3m", "C3m", "C4m"])
        settings.use({})
        self.assertEqual(floor._label(1.5), "C1.5m")


if __name__ == "__main__":
    unittest.main()
