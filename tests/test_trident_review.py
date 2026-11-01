"""Converter changes from the review of Trident draft 1 (docs/lvs-phase5-log.md)."""
import math
import os
import re
import unittest

from tools.sketch2therion import marks, nodes, scale, settings, tidy

from tools.sketch2therion.project import REPO     # the test cave


class Scale(unittest.TestCase):
    def tearDown(self):
        scale.clear()

    def test_mean_of_the_three_nearest_legs(self):
        scale.use([((0, 0), (2, 0)), ((2, 0), (4, 0)), ((4, 0), (8, 0)), ((100, 0), (200, 0))])
        self.assertAlmostEqual(scale.at((1, 1)), (2 + 2 + 4) / 3)

    def test_relative_or_absolute(self):
        scale.use([((0, 0), (3, 0))], K=1.0)
        self.assertAlmostEqual(scale.tol((0, 0), 0.05, 0.1), 0.15)
        self.assertEqual(scale.tol((0, 0), 0.0, 0.1), 0.1)
        scale.clear()
        self.assertEqual(scale.tol((0, 0), 0.05, 0.1), 0.1)


class FewerPoints(unittest.TestCase):
    def tearDown(self):
        settings.load()
        scale.clear()

    def test_longer_legs_fewer_points(self):
        settings.load()
        wobbly = [(x * 0.1, 0.25 * math.sin(x * 0.25)) for x in range(80)]   # bends 0.25 m either side
        px = lambda p: p
        scale.use([((0, -1), (2, -1))])                 # 2 m legs
        short = len(marks.smooth_rows(wobbly, px))
        scale.use([((0, -1), (8, -1))])                 # 8 m legs
        long_ = len(marks.smooth_rows(wobbly, px))
        self.assertLess(long_, short)


class WallsMeet(unittest.TestCase):
    def wall(self, pts):
        o = tidy.Obj('line', 'line wall', [])
        o.set_segments([[x, y] for x, y in pts])
        return o

    def test_ends_close_together_meet(self):
        a, b = self.wall([(0, 0), (100, 0)]), self.wall([(110, 5), (200, 5)])
        self.assertEqual(nodes.walls_meet([a, b], 100.0, 0.2), 2)
        self.assertEqual(tuple(a.segments()[-1][-2:]), tuple(b.segments()[0][-2:]))

    def test_not_across_a_survey_leg(self):
        a, b = self.wall([(0, 0), (100, 0)]), self.wall([(110, 5), (200, 5)])
        self.assertEqual(nodes.walls_meet([a, b], 100.0, 0.2, legs=[((105, -10), (105, 20))]), 0)

    def test_undone_if_the_outline_suffers(self):
        a, b = self.wall([(0, 0), (100, 0)]), self.wall([(110, 5), (200, 5)])
        before = (a.rows, b.rows)
        self.assertEqual(nodes.walls_meet([a, b], 100.0, 0.2, ok=lambda: False), 0)
        self.assertEqual((a.rows, b.rows), before)

    def test_long_segment_measured_closely(self):
        # a 12 m Bezier segment: the nearest point is found to within a few cm
        segs = [[0, 0], [400, 0, 800, 0, 1200, 0]]
        d = nodes.nearest_on(segs, (613, 5))[0]
        self.assertAlmostEqual(d, 5, delta=1.5)


class Curls(unittest.TestCase):
    def test_a_curl_is_a_closed_loop(self):
        c = [(0.3 * math.cos(a / 10), 0.3 * math.sin(a / 10)) for a in range(0, 52)]      # 300 degrees round
        self.assertTrue(marks.is_open_loop(c))
        self.assertFalse(marks.is_open_loop([(0, 0), (0.5, 0.02), (1.0, 0)]))


class SectionInPlace(unittest.TestCase):
    def test_section_drawn_by_its_mark(self):
        import subprocess, sys, tempfile
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "t.th2")
            subprocess.run([sys.executable, "-m", "tools.sketch2therion", "plan",
                            os.path.join(REPO, "TestCave", "Trident", "Notes", "TridentP.xvi"),
                            "--survey", "Trident", "-o", out], cwd=REPO, check=True, capture_output=True)
            text = open(out).read()
        mark = re.search(r"point (\S+) (\S+) section -scrap (\S+)", text)
        # (its first wall: closed, or the stroke as drawn with a floor across its ends)
        xs = re.search(r"(?ms)^scrap %s .*?^line wall[^\n]*\n\s*(\S+) (\S+)" % mark.group(3), text)
        self.assertLess(math.dist(tuple(map(float, mark.groups()[:2])), tuple(map(float, xs.groups()))), 2 * 78.74)


if __name__ == "__main__":
    unittest.main()


class NodeGap(unittest.TestCase):
    """No two nodes too close to pick apart when editing (nodes.thin)."""

    def test_close_nodes_go_ends_stay(self):
        out = nodes.thin([[0, 0], [10, 0], [11, 0], [20, 0], [30, 0], [30.5, 0]], 3)
        self.assertEqual([tuple(s[-2:]) for s in out], [(0, 0), (10, 0), (20, 0), (30.5, 0)])

    def test_merged_segment_follows_the_shape(self):
        # a sweep sampled with an extra node: the node goes and the curve barely moves
        import math as m
        arc = [(10 * m.cos(a), 10 * m.sin(a)) for a in (0, 0.5, 0.55, 1.1)]
        segs = [[*arc[0]]] + [[*p] for p in arc[1:]]
        out = nodes.thin(segs, 1.0, maxerr=0.5)
        self.assertEqual(len(out), 3)

    def test_s_bend_keeps_its_node_a_sweep_does_not(self):
        # the user's point: sweeps need few nodes, S bends more
        s_bend = [[0, 0], [0.2, 0.8, 0.8, 0.8, 1, 0], [1.2, -0.8, 1.8, -0.8, 2, 0]]
        sweep = [[0, 0], [0.2, 0.3, 0.8, 0.5, 1, 0.55], [1.2, 0.6, 1.8, 0.5, 2, 0.2]]
        self.assertEqual(len(nodes.thin(s_bend, 1.5, maxerr=0.1)), 3)
        self.assertEqual(len(nodes.thin(s_bend, 1.5)), 2)              # with no limit it would go
        self.assertEqual(len(nodes.thin(sweep, 1.5, maxerr=0.05)), 2)

    def test_nothing_to_thin(self):
        segs = [[0, 0], [10, 0], [20, 0]]
        self.assertEqual(nodes.thin(segs, 3), segs)

    def test_closed_line_stays_closed(self):
        o = tidy.Obj('line', 'line border -close on', [])
        o.set_segments([[0, 0], [10, 0], [10.5, 0], [10, 10], [0, 10], [0, 0]])
        nodes.thin_scrap([o], 1.0, lambda o: 2.0)
        s = o.segments()
        self.assertEqual(tuple(s[0][-2:]), tuple(s[-1][-2:]))
        self.assertEqual(len(s), 5)


class RelativeJoin(unittest.TestCase):
    def wall(self, pts):
        o = tidy.Obj('line', 'line wall', [])
        o.set_segments([[x, y] for x, y in pts])
        return o

    def test_reach_can_depend_on_where(self):
        a, b = self.wall([(0, 0), (100, 0)]), self.wall([(130, 0), (200, 0)])     # 0.3 m apart (K = 100)
        self.assertEqual(nodes.walls_meet([a, b], 100.0, lambda p: 0.2), 0)
        self.assertEqual(nodes.walls_meet([a, b], 100.0, lambda p: 0.4), 2)


class RockFaces(unittest.TestCase):
    """The fill without the rock its closing-up took in (convert.drop_rock_faces)."""

    def test_face_with_no_leg_across_bridged_edge_goes(self):
        from shapely.geometry import box
        from tools.sketch2therion.convert import drop_rock_faces
        fill = box(0, 0, 10, 4)                     # closed up across rock above y = 2.5
        wall = [(0, 2.5), (10, 2.5)]
        out = drop_rock_faces(fill, [wall], [[(0, 1), (10, 1)]], [(0, 1), (10, 1)])
        self.assertAlmostEqual(out.area, 25.0, delta=0.5)

    def test_pillar_stays(self):
        from shapely.geometry import box
        from tools.sketch2therion.convert import drop_rock_faces
        fill = box(0, 0, 10, 4)
        pillar = [(4, 1.5), (6, 1.5), (6, 2.5), (4, 2.5), (4, 1.5)]
        out = drop_rock_faces(fill, [pillar], [[(0, 0.5), (10, 0.5)], [(0, 3.5), (10, 3.5)]], [(0, 0.5)])
        self.assertAlmostEqual(out.area, 40.0, delta=0.5)

    def test_alcove_along_a_sketched_wall_stays(self):
        # a ledge line cuts off a side with no leg, but its edge there is the sketched wall
        from shapely.geometry import box
        from tools.sketch2therion.convert import drop_rock_faces
        fill = box(0, 0, 10, 4)
        outer = [(0, 4), (10, 4)]
        ledge = [(1, 4), (1, 3), (9, 3), (9, 4)]       # from the wall round and back to it
        out = drop_rock_faces(fill, [outer, ledge], [[(0, 1), (10, 1)]], [(0, 1)])
        self.assertAlmostEqual(out.area, 40.0, delta=0.5)


class WallHooks(unittest.TestCase):
    def tearDown(self):
        settings.load()

    def test_open_loop_at_a_wall_is_wall(self):
        from tools.sketch2therion.convert import wall_strokes
        settings.load()
        wall = [(0, 0), (3, 0)]
        hook = [(3.05, 0), (3.3, 0.25), (3.3, 0.5), (3.0, 0.55), (2.8, 0.35), (2.9, 0.15)]   # open, starts at the wall
        walls, boulders, _ = wall_strokes([('BLACK', wall), ('BLACK', hook)])
        self.assertEqual(len(boulders), 0)
        self.assertEqual(len(walls), 2)
        settings.use(dict(settings.SETTINGS, wall_hooks=False))
        walls, boulders, _ = wall_strokes([('BLACK', wall), ('BLACK', hook)])
        self.assertEqual(len(boulders), 1)


class JoinRuns(unittest.TestCase):
    """Lines joined into the line of their kind they run on into (user, draft 5; 2026-10-22)."""

    def line(self, head, pts):
        o = tidy.Obj('line', head, [])
        o.set_segments([[x, y] for x, y in pts])
        return o

    def test_touching_line_joined(self):
        a = self.line('line border', [(0, 0), (100, 0), (200, 0)])
        b = self.line('line border', [(210, 0), (300, 10)])
        objs = [a, b]
        self.assertEqual(nodes.join_runs(objs, 100.0, 0.2), 1)
        self.assertEqual(len(objs), 1)
        self.assertEqual(tuple(objs[0].segments()[-1][-2:]), (300.0, 10.0))

    def test_other_kinds_and_gours_left(self):
        a = self.line('line border', [(0, 0), (100, 0), (200, 0)])
        b = self.line('line floor-step', [(200, 0), (300, 0)])
        g1 = self.line('line rimstone-dam', [(0, 50), (50, 60), (100, 50)])
        g2 = self.line('line rimstone-dam', [(100, 50), (150, 60)])
        self.assertEqual(nodes.join_runs([a, b, g1, g2], 100.0, 0.2), 0)

    def test_touching_joined_whatever_the_angle(self):
        a = self.line('line border', [(0, 0), (100, 0), (200, 0)])
        back = self.line('line border', [(200, 0), (150, 20), (100, 30)])      # turns sharply
        self.assertEqual(nodes.join_runs([a, back], 100.0, 0.2), 1)

    def test_across_a_gap_only_carrying_on(self):
        long = [(0, 0), (100, 0), (200, 0), (300, 0), (400, 0), (500, 0)]      # length does not matter
        a, b = self.line('line border', long), self.line('line border', [(525, 2), (700, 5), (800, 10)])
        self.assertEqual(nodes.join_runs([a, b], 100.0, 0.05), 1)               # 25 cm, carrying on
        a, b = self.line('line border', long), self.line('line border', [(525, 0), (525, 200)])
        self.assertEqual(nodes.join_runs([a, b], 100.0, 0.05), 0)               # 25 cm, turning 90 degrees
        a, b = self.line('line border', long), self.line('line border', [(540, 0), (700, 0)])
        self.assertEqual(nodes.join_runs([a, b], 100.0, 0.05), 0)               # 40 cm: too far

    def test_not_at_a_junction_nor_a_named_line(self):
        a = self.line('line border', [(0, 0), (100, 0), (200, 0)])
        b = self.line('line border', [(200, 0), (300, 0)])
        c = self.line('line border', [(200, 0), (200, 100)])                    # a third ends there
        self.assertEqual(nodes.join_runs([a, b, c], 100.0, 0.2), 0)
        a = self.line('line border -id B1', [(0, 0), (100, 0), (200, 0)])
        b = self.line('line border', [(200, 0), (300, 0)])
        self.assertEqual(nodes.join_runs([a, b], 100.0, 0.2, named={'B1'}), 0)    # a join names it
        self.assertEqual(nodes.join_runs([a, b], 100.0, 0.2), 1)                  # an id nothing names

    def test_walls_joined_on_their_own(self):
        a = self.line('line wall', [(0, 0), (100, 0), (200, 0), (300, 0), (400, 0)])
        b = self.line('line wall', [(400, 0), (500, 50), (600, 50), (700, 50), (800, 0)])
        c = self.line('line border', [(0, 50), (100, 50)])
        self.assertEqual(nodes.join_runs([a, b, c], 100.0, 0.05), 0)            # walls only when asked
        objs = [a, b, c]
        self.assertEqual(nodes.join_runs(objs, 100.0, 0.05, walls=True), 1)
        self.assertEqual(len(objs), 2)
        b = self.line('line wall', [(1200, 0), (800, 0)])                        # ends where it ends: the other way round
        self.assertEqual(nodes.join_runs([objs[0], b], 100.0, 0.05, walls=True), 0)


class StepsKeepTheirTicks(unittest.TestCase):
    def line(self, head, pts):
        o = tidy.Obj('line', head, [])
        o.set_segments([[x, y] for x, y in pts])
        return o

    def test_steps_joined_only_running_the_same_way(self):
        a = self.line('line floor-step', [(0, 0), (100, 0), (200, 0)])
        b = self.line('line floor-step', [(300, 0), (210, 0)])          # runs the other way: ticks the other side
        self.assertEqual(nodes.join_runs([a, b], 100.0, 0.2), 0)
        c = self.line('line floor-step', [(210, 0), (300, 0)])
        objs = [a, c]
        self.assertEqual(nodes.join_runs(objs, 100.0, 0.2), 1)
        s = objs[0].segments()
        self.assertEqual((tuple(s[0][-2:]), tuple(s[-1][-2:])), ((0.0, 0.0), (300.0, 0.0)))   # not turned round


class EndsMeet(unittest.TestCase):
    def line(self, head, pts):
        o = tidy.Obj('line', head, [])
        o.set_segments([[x, y] for x, y in pts])
        return o

    def test_border_floor_step_pit_share_ends(self):
        b = self.line('line border', [(0, 0), (100, 0)])
        f = self.line('line floor-step', [(110, 5), (200, 0)])
        p = self.line('line pit', [(205, -8), (300, 0)])
        objs = [b, f, p]
        self.assertEqual(nodes.ends_meet(objs, 100.0, 0.2), 2)
        self.assertEqual(tuple(b.segments()[-1][-2:]), tuple(f.segments()[0][-2:]))
        self.assertEqual(tuple(f.segments()[-1][-2:]), tuple(p.segments()[0][-2:]))

    def test_end_on_a_wall_stays(self):
        w = self.line('line wall', [(0, -50), (100, 0), (100, 100)])
        b = self.line('line border', [(100, 0), (200, 0)])               # ends on the wall's node
        f = self.line('line floor-step', [(110, 5), (110, 80)])
        nodes.ends_meet([w, b, f], 100.0, 0.2)
        self.assertEqual(tuple(b.segments()[0][-2:]), (100.0, 0.0))
        self.assertEqual(tuple(f.segments()[0][-2:]), (100.0, 0.0))


class HandlesInLine(unittest.TestCase):
    def test_smooth_node_unless_a_corner(self):
        segs = [[0, 0], [1, 1, 2, 1, 3, 0], [3.5, -0.2, 4, -1, 5, -1]]
        out, n = nodes.align_handles(segs, 60)
        self.assertEqual(n, 1)
        p = out[1][-2:]
        a, b = out[1][2:4], out[2][0:2]
        cross = (p[0] - a[0]) * (b[1] - p[1]) - (p[1] - a[1]) * (b[0] - p[0])
        self.assertAlmostEqual(cross, 0, places=6)
        corner = [[0, 0], [1, 0, 2, 0, 3, 0], [3, 1, 3, 2, 3, 3]]          # a right angle stays
        self.assertEqual(nodes.align_handles(corner, 60)[1], 0)


class DetachedTicks(unittest.TestCase):
    def tearDown(self):
        settings.load()

    def test_grey_ticks_clear_of_a_grey_line(self):
        from tools.sketch2therion import notation
        settings.load()
        line = ('GRAY', [(x * 0.2, 0) for x in range(16)])
        ticks = [('GRAY', [(x, -0.25), (x, -0.55)]) for x in (0.5, 1.2, 1.9, 2.6)]   # 0.25 m clear
        feats, used = notation.find([line] + ticks)
        self.assertEqual([k for k, _, _ in feats], ['step'])
        settings.use(dict(settings.SETTINGS, tick_reach=0.0))
        self.assertEqual(notation.find([line] + ticks)[0], [])
        settings.load()
        black = ('BLACK', line[1])                                       # a black line is wall
        self.assertEqual(notation.find([black] + ticks)[0], [])


class Discontinuities(unittest.TestCase):
    """Overshoots where strokes overlap are not corners (user: discontinuities)."""

    def wall(self, segs):
        o = tidy.Obj('line', 'line wall', [])
        o.set_segments(segs)
        return o

    def test_spike_removed(self):
        w = self.wall([[0, 0], [100, 0], [92, 2], [200, 4]])       # runs on 0.08 m and back
        self.assertEqual(nodes.despike([w], 100.0, 0.3), 1)
        self.assertEqual(len(w.segments()), 3)

    def test_small_step_removed_real_corner_kept(self):
        w = self.wall([[0, 0], [100, 0], [100, 5], [200, 5]])      # a 5 cm sideways step
        nodes.despike([w], 100.0, 0.3)
        self.assertLess(len(w.segments()), 4)
        c = self.wall([[0, 0], [100, 0], [100, 100]])               # a real corner, 1 m each way
        self.assertEqual(nodes.despike([c], 100.0, 0.3), 0)

    def test_hook_within_a_segment_fixed(self):
        # the end handle lies past the end point: the curve overshoots and comes back
        w = self.wall([[0, 0], [30, 0, 130, 0, 100, 0]])
        self.assertEqual(nodes.fix_handles([w], 1.0), 1)
        s = w.segments()[1]
        self.assertTrue(0 <= s[2] <= 100)

    def test_kinked_handles_on_a_smooth_line_aligned(self):
        # the wall runs straight through the node, but the handles meet at a sharp angle
        segs = [[0, 0], [30, 10, 80, 20, 100, 0], [120, 20, 170, 10, 200, 0]]
        out, n = nodes.align_handles(segs, 60)
        self.assertEqual(n, 1)


class Notation(unittest.TestCase):
    def tearDown(self):
        settings.load()

    def test_overhang_of_two_ticked_dashes_and_short_steps(self):
        from tools.sketch2therion import notation
        settings.load()
        dashes = [('GRAY', [(0, 0), (0.45, 0)]), ('GRAY', [(0.9, 0), (1.35, 0)])]
        ticks = [('GRAY', [(0.22, 0.02), (0.22, -0.4)]), ('GRAY', [(1.12, 0.02), (1.12, -0.4)])]
        feats, _ = notation.find(dashes + ticks)
        self.assertEqual([k for k, _, _ in feats], ['overhang'])
        brown = [('BROWN', pp) for _, pp in dashes + ticks]          # mud dashes are not an overhang
        self.assertEqual(notation.find(brown)[0], [])
        short = [('GRAY', [(0, 0), (0.5, 0)])] + [('GRAY', [(x, 0.01), (x, -0.15)]) for x in (0.1, 0.25, 0.4)]
        self.assertEqual([k for k, _, _ in notation.find(short)[0]], ['step'])
        self.assertEqual(notation.find(short[:3])[0], [])            # two ticks: too few for a short line


class Elevations(unittest.TestCase):
    def test_brown_floor_counts_in_elevations_only(self):
        from tools.sketch2therion.convert import wall_strokes
        settings.load()
        self.assertEqual(settings.SETTINGS['wall_colours'], ['BLACK'])
        self.assertIn('BROWN', settings.SETTINGS['elevation_wall_colours'])
        floor = ('BROWN', [(x * 0.5, 0) for x in range(10)])
        walls, _, _ = wall_strokes([floor])
        self.assertEqual(walls, [])                                    # plan: brown is mud, not wall

    def test_green_lumpy_is_blocks_smooth_is_flowstone(self):
        from tools.sketch2therion.convert import _lumpy
        import math
        smooth = [(x * 0.1, 0.02 * x * 0.1) for x in range(30)]
        bumps = [(x * 0.05, 0.15 * abs(math.sin(x * 0.05 * math.pi / 0.3))) for x in range(60)]
        loop = [(0, 0), (0.3, 0), (0.3, 0.3), (0, 0.3), (0, 0)]
        self.assertFalse(_lumpy(smooth))
        self.assertTrue(_lumpy(bumps))
        self.assertTrue(_lumpy(loop))

    def test_extended_scraps_by_hand(self):
        from tools.sketch2therion import project
        P = project.load()
        self.assertEqual(P.scraps_extended.get('GoSouth'), ['1-16', '17-29'])
        self.assertEqual(len(P.scraps_extended.get('Trident')), 4)      # the user's split, log row 150
