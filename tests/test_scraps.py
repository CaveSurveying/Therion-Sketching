"""Plan scraps chosen by hand ([scraps] in tools/project.toml)."""
import math
import os
import re
import subprocess
import sys
import tempfile
import unittest

from tools.sketch2therion import project
from tools.sketch2therion import scraps

from tools.sketch2therion.project import REPO     # the test cave
NAMES = [str(n) for n in range(1, 30) if n != 25]


class Parse(unittest.TestCase):
    def test_ranges_take_only_existing_stations(self):
        g = scraps.parse(["1-16", "17-29"], NAMES)
        self.assertEqual(g[0], [str(n) for n in range(1, 17)])
        self.assertNotIn("25", g[1])
        self.assertEqual(len(g[1]), 12)

    def test_names_and_commas(self):
        self.assertEqual(scraps.parse(["19, 21-23 1"], NAMES), [["19", "21", "22", "23", "1"]])

    def test_unknown_station_fails(self):
        with self.assertRaisesRegex(ValueError, "no station 99"):
            scraps.parse(["99"], NAMES)

    def test_station_in_two_scraps_fails(self):
        with self.assertRaisesRegex(ValueError, "station 5 is in more than one"):
            scraps.parse(["1-5", "5-9"], NAMES)

    def test_unlisted_stations_follow_their_legs(self):
        g = scraps.complete([["1", "2"], ["5"]], ["1", "2", "3", "4", "5"], [("2", "3"), ("3", "4"), ("5", "6")])
        self.assertEqual(sorted(g[0]), ["1", "2", "3", "4"])

    def test_station_with_no_way_in_fails(self):
        with self.assertRaisesRegex(ValueError, "stations 9 are in no scrap"):
            scraps.complete([["1", "2"]], ["1", "2", "9"], [("1", "2")])


class Assign(unittest.TestCase):
    # two parallel passages 2 m apart, joined by a leg 2-3 that is in neither scrap
    pos = {"1": (0, 0), "2": (10, 0), "3": (10, -2), "4": (0, -2)}
    legs = [("1", "2"), ("2", "3"), ("3", "4")]
    groups = [["1", "2"], ["3", "4"]]

    def test_strokes_go_with_their_nearest_leg(self):
        lines = [("BLACK", [(0, 1), (10, 1)]), ("BLACK", [(0, -3), (10, -3)])]
        out = scraps.assign(lines, self.groups, self.pos, self.legs)
        self.assertEqual([k for k, _, _ in out], [0, 1])

    def test_wall_between_passages_cut_where_scrap_changes(self):
        # one stroke along the top passage, then turning down along the bottom one
        pp = [(x, 0.3) for x in range(0, 6)] + [(5, -1.0), (5, -2.3)] + [(x, -2.3) for x in range(6, 10)]
        out = scraps.assign([("BLACK", pp)], self.groups, self.pos, self.legs)
        self.assertEqual([k for k, _, _ in out], [0, 1])
        self.assertEqual(out[0][2][-1], out[1][2][0])      # the pieces meet

    def test_short_wavering_piece_not_split_off(self):
        pp = [(0, 0.5), (3, 0.5), (3.1, -1.1), (3.2, 0.5), (8, 0.5)]
        out = scraps.assign([("BLACK", pp)], self.groups, self.pos, self.legs)
        self.assertEqual(len(out), 1)

    def test_closed_loop_kept_whole(self):
        loop = [(4, 0.2), (5, 0.2), (5, -1.6), (4, -1.6), (4, 0.2)]
        out = scraps.assign([("BROWN", loop)], self.groups, self.pos, self.legs)
        self.assertEqual(len(out), 1)


class OneWallEachSide(unittest.TestCase):
    """Hard rule 2: a scrap has one outer wall each side of its passage; of
    two lying one behind the other, the one that is also another scrap's goes
    (FairyChimneys 13 to 20)."""

    def setUp(self):
        # scrap 0: a crawl along y = 0 (stations 1, 2); scrap 1: a passage over it (3, 4)
        self.groups = [['1', '2'], ['3', '4']]
        self.pos = {'1': (0.0, 0.0), '2': (4.0, 0.0), '3': (0.0, 1.0), '4': (4.0, 1.0)}
        self.crawl_roof = [(0.0, 0.3), (2.0, 0.3), (4.0, 0.3)]
        self.crawl_floor = [(0.0, -0.3), (2.0, -0.3), (4.0, -0.3)]
        self.upper_floor = [(0.0, 0.5), (2.0, 0.5), (4.0, 0.5)]

    def test_shared_wall_behind_goes(self):
        pieces = [(0, 'BLACK', self.crawl_roof), (0, 'BROWN', self.crawl_floor),
                  (1, 'BLACK', self.upper_floor), (1, 'BROWN', self.crawl_floor)]
        out = scraps.one_wall_each_side(pieces, self.groups, self.pos, {'BLACK', 'BROWN'})
        self.assertNotIn((1, 'BROWN', self.crawl_floor), out)
        self.assertIn((0, 'BROWN', self.crawl_floor), out)
        self.assertIn((1, 'BLACK', self.upper_floor), out)

    def test_shared_wall_in_front_goes(self):
        # the upper passage's own floor drawn just under the crawl's roof: the roof (the crawl's) goes
        low_floor = [(0.0, 0.1), (2.0, 0.1), (4.0, 0.1)]
        pieces = [(0, 'BLACK', self.crawl_roof), (1, 'BLACK', self.crawl_roof), (1, 'BLACK', low_floor)]
        out = scraps.one_wall_each_side(pieces, self.groups, self.pos, {'BLACK'})
        self.assertEqual(out, [(0, 'BLACK', self.crawl_roof), (1, 'BLACK', low_floor)])

    def test_own_walls_and_continuations_stay(self):
        on = [(4.0, 0.3), (4.3, 0.8)]                   # carries on from the roof's end
        pieces = [(0, 'BLACK', self.crawl_roof), (1, 'BLACK', self.crawl_roof), (0, 'BLACK', on)]
        out = scraps.one_wall_each_side(pieces, self.groups, self.pos, {'BLACK'})
        self.assertEqual(len(out), 3)


class MeetEnds(unittest.TestCase):
    TEXT = """scrap A -projection plan
line wall
  0.00 0.00
  100.00 0.00
endline
line wall -subtype invisible -close on
  0 0
  1 1
endline
endscrap
scrap B -projection plan
line wall
  110.00 4.00
  200.00 0.00 210.00 0.00 300.00 0.00
endline
line wall
  0.00 50.00
  500.00 50.00
endline
endscrap
"""

    def test_walls_in_two_scraps_meet_at_the_midpoint(self):
        out = scraps.meet_ends(self.TEXT, 20)
        self.assertEqual(out.count("105.00 2.00"), 2)
        self.assertIn("  0.00 50.00", out)          # too far from any other scrap's wall end
        self.assertIn("  0.00 0.00", out)

    def test_walls_in_one_scrap_left_alone(self):
        text = self.TEXT.replace("endscrap\nscrap B -projection plan\n", "")
        self.assertEqual(scraps.meet_ends(text, 20), text)


class GoSouth(unittest.TestCase):
    def test_config(self):
        self.assertEqual(project.load().scraps.get("GoSouth"), ["1-16", "17-29"])

    def test_two_scraps_and_no_leg_15_17(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "GoSouth.plan.th2")
            subprocess.run([sys.executable, "-m", "tools.sketch2therion", "plan",
                            os.path.join(REPO, "TestCave", "GoSouth", "Notes", "GoSouthP.xvi"),
                            "--survey", "GoSouth", "-o", out], cwd=REPO, check=True, capture_output=True)
            text = open(out).read()
        bodies = dict(re.findall(r"(?ms)^scrap (\S+)[^\n]*\n(.*?)^endscrap", text))
        self.assertEqual(sorted(bodies), ["GoSouthSP1", "GoSouthSP2"])
        st = {k: set(re.findall(r"station -name (\S+)", b)) for k, b in bodies.items()}
        self.assertTrue({"9", "10", "11", "12", "15", "16"} <= st["GoSouthSP1"])
        self.assertTrue({"17", "18", "19", "20", "21"} <= st["GoSouthSP2"])
        self.assertFalse(st["GoSouthSP1"] & st["GoSouthSP2"])
        # the north wall by 21 is one wall across the two scraps: its pieces meet
        def ends(body):
            out = []
            for m in re.finditer(r"(?ms)^line wall(?! -subtype)[^\n]*\n(.*?)^endline", body):
                rows = [r.split() for r in m.group(1).strip().splitlines() if re.match(r"\s*-?\d", r)]
                out += [tuple(rows[0][-2:]), tuple(rows[-1][-2:])]
            return set(out)
        self.assertTrue(ends(bodies["GoSouthSP1"]) & ends(bodies["GoSouthSP2"]))


if __name__ == "__main__":
    unittest.main()


class Areas(unittest.TestCase):
    """Areas: few nodes, splines, run out over the walls (Style.md)."""

    def tearDown(self):
        from tools.sketch2therion import settings
        settings.load()

    def test_area_over_the_wall_as_a_spline(self):
        from shapely.geometry import box
        from tools.sketch2therion import marks, settings
        settings.load()
        settings.SETTINGS["drawn_rocks"] = False        # (areas of rocks: the upstream way)
        passage = box(0, 0, 6, 2)
        loops = []
        for k in range(8):                    # boulders along the wall at y = 0
            x = 0.5 + 0.6 * k
            loops.append(("BROWN", [(x, 0.05), (x + 0.4, 0.05), (x + 0.4, 0.45), (x, 0.45), (x, 0.05)]))
        o = marks.th2(loops, passage, lambda p: (100 * p[0], 100 * p[1]), "XSP1", ["BLACK"], 0.3)
        text = "\n".join(o)
        m = re.search(r"(?ms)^line border -subtype invisible -id (\S+) -close on\n(.*?)^endline", text)
        self.assertIsNotNone(m, text)
        rows = m.group(2).strip().splitlines()
        self.assertLessEqual(len(rows), 10)
        self.assertTrue(all(len(r.split()) == 6 for r in rows[1:]))        # Bezier segments
        ys = [float(r.split()[-1]) for r in rows]
        self.assertLess(min(ys), 0)                                         # over the wall

    def test_brown_lines_in_rock_areas_dropped(self):
        from shapely.geometry import box
        from tools.sketch2therion import marks, settings
        settings.load()
        settings.SETTINGS["drawn_rocks"] = False
        passage = box(0, 0, 6, 2)
        loops = [("BROWN", [(x, 0.6), (x + 0.4, 0.6), (x + 0.4, 1.0), (x, 1.0), (x, 0.6)])
                 for x in (0.5 + 0.6 * k for k in range(6))]
        rock_line = ("BROWN", [(1.2, 0.8), (1.4, 0.75), (1.6, 0.85), (1.8, 0.8)])       # among the rocks
        ledge = ("BROWN", [(0.5, 1.7), (2.0, 1.75), (3.5, 1.7), (5.0, 1.75)])           # well clear of them
        px = lambda p: (100 * p[0], 100 * p[1])

        settings.use(dict(settings.SETTINGS, dash_max=0.0, mud_grow=0.0, mud_near=0.0, rock_curves=False,
                          area_grow=0.0, barrier_min=0.0))   # the rock line is not mud (nor a rock) here

        def borders():
            text = "\n".join(marks.th2(loops + [rock_line, ledge], passage, px, "XSP1", ["BLACK"], 0.3))
            return [m for m in re.findall(r"(?ms)^line border(?: -id \S+)?\n(.*?)^endline", text)]
        self.assertEqual(len(borders()), 1)                 # the ledge only
        settings.use(dict(settings.SETTINGS, area_lines=True))
        self.assertEqual(len(borders()), 2)


class Mud(unittest.TestCase):
    """Brown dashes are mud: one patch along the passage, off the rocks (Trident review)."""

    def tearDown(self):
        from tools.sketch2therion import settings
        settings.load()

    def test_dashes_along_a_passage_are_one_patch_off_the_rocks(self):
        from shapely.geometry import box
        from tools.sketch2therion import marks, settings
        settings.load()
        settings.SETTINGS["drawn_rocks"] = False
        passage = box(0, 0, 12, 2)
        dashes = [[(x, 1.0), (x + 0.9, 1.05)] for x in (0.5, 2.0, 3.6, 5.1, 6.5)]      # 0.9 m dashes, 0.6 m apart
        rocks = [[(x, 0.3), (x + 0.4, 0.3), (x + 0.4, 0.7), (x, 0.7), (x, 0.3)] for x in (9.0, 9.6, 10.2, 10.8)]
        _, areas, lines = marks.brown(dashes + rocks, passage, 0.3)
        mud = [g for k, g in areas if k == 'sand']                            # mud is drawn as sand
        self.assertEqual(len(mud), 1)
        self.assertGreater(mud[0].bounds[2] - mud[0].bounds[0], 6.5)            # the whole stretch
        rock = [g for k, g in areas if k in ('blocks', 'debris')]
        self.assertTrue(rock and mud[0].intersection(rock[0]).area < 0.01)
        self.assertEqual(lines, [])

    def test_a_lone_long_dash_stays_a_line(self):
        from shapely.geometry import box
        from tools.sketch2therion import marks, settings
        settings.load()
        _, areas, lines = marks.brown([[(1, 1), (1.9, 1.05)]], box(0, 0, 4, 2), 0.3)
        self.assertEqual(areas, [])
        self.assertEqual(len(lines), 1)


class Corner(unittest.TestCase):
    def test_leg_off_to_one_side(self):
        from shapely.geometry import LineString, Point
        from tools.sketch2therion.convert import _leg_in_cone
        leg = LineString([(1, 1), (5, 1)])
        self.assertTrue(_leg_in_cone(Point(0, 0), (0, 1), leg, 8, 60))      # 45 degrees off
        self.assertFalse(_leg_in_cone(Point(0, 0), (0, 1), leg, 8, 30))
        self.assertFalse(_leg_in_cone(Point(0, 0), (0, -1), leg, 8, 60))    # behind
        self.assertFalse(_leg_in_cone(Point(0, 0), (0, 1), leg, 1, 60))     # too far

    def test_gosouth_corner_by_2_and_3_is_wall(self):
        from shapely.geometry import LineString, Point
        from tools.sketch2therion import tidy
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "GoSouth.plan.th2")
            subprocess.run([sys.executable, "-m", "tools.sketch2therion", "plan",
                            os.path.join(REPO, "TestCave", "GoSouth", "Notes", "GoSouthP.xvi"),
                            "--survey", "GoSouth", "-o", out], cwd=REPO, check=True, capture_output=True)
            body = re.search(r"(?ms)^scrap GoSouthSP1[^\n]*\n(.*?)^endscrap", open(out).read()).group(1)
        corner = Point(-46, -430)          # the sketch's wall turning west there (drawing units)
        kinds = [o.head for o in tidy.parse_scrap(body) if o.kind == "line" and len(o.segments()) > 1
                 and LineString(tidy.bezier_points(o.segments(), 6)).distance(corner) < 8]
        self.assertTrue(kinds and all(h.startswith("line wall") and "-outline none" not in h for h in kinds), kinds)


class DoubledWallsCheck(unittest.TestCase):
    """review check: a second outer wall on one side of the passage is reported (hard rule 2)."""

    TH2 = """scrap S1 -projection extended -scale [0 0 787.40 787.40 0.0 0.0 10 10 m]

line wall
  0 -40
  400 -40
endline

line wall -subtype debris
  0 -60
  400 -60
endline

line wall
  400 60
  0 60
endline

point 0 0 station -name 1

point 400 0 station -name 2

endscrap
"""

    def check(self, text):
        from tools.sketch2therion import review
        with tempfile.NamedTemporaryFile('w', suffix='.th2', delete=False) as f:
            f.write(text)
        try:
            return review.doubled_walls(f.name)
        finally:
            os.unlink(f.name)

    def test_second_floor_reported(self):
        found = self.check(self.TH2)
        self.assertEqual(len(found), 1)
        self.assertGreater(found[0][1], 4.0)

    def test_one_floor_clean(self):
        text = self.TH2.replace("line wall -subtype debris\n  0 -60\n  400 -60\nendline\n", "")
        self.assertEqual(self.check(text), [])


class CarriedThrough(unittest.TestCase):
    """A short run of wall pieces between two pieces of another scrap's wall,
    carrying on in line, is that scrap's (FairyChimneys 9: the floor under it)."""

    def test_bridge_moved(self):
        a, b, c = [(0.0, 0.0), (2.0, 0.0)], [(2.1, 0.0), (3.0, 0.0)], [(3.1, 0.0), (6.0, 0.0)]
        out = scraps.carried_through([(0, 'BROWN', a), (1, 'GREEN', b), (0, 'BROWN', c)], {'BROWN', 'GREEN'})
        self.assertEqual([k for k, _, _ in out], [0, 0, 0])

    def test_turning_piece_stays(self):
        a, b, c = [(0.0, 0.0), (2.0, 0.0)], [(2.1, 0.0), (2.1, 1.0)], [(2.1, 1.1), (5.0, 1.1)]
        out = scraps.carried_through([(0, 'BLACK', a), (1, 'BLACK', b), (0, 'BLACK', c)], {'BLACK'})
        self.assertEqual([k for k, _, _ in out], [0, 1, 0])


class MeetOnWalls(unittest.TestCase):
    """A wall ending on another scrap's wall ends at a node of it."""

    TH2 = """scrap A -projection extended
line wall
  0.00 0.00
  100.00 0.00
endline
endscrap
scrap B -projection extended
line wall
  50.00 5.00
  50.00 80.00
endline
endscrap
"""

    def test_node_added(self):
        out = scraps.meet_on_walls(self.TH2, 10.0)
        self.assertIn("  50.00 0.00\n  100.00 0.00", out)        # A split at 50 0
        self.assertIn("  50.00 0.00\n  50.00 80.00", out)        # B's end moved onto it

    def test_far_end_left(self):
        self.assertEqual(scraps.meet_on_walls(self.TH2, 3.0), self.TH2)
