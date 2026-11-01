"""Elevation features read from the sketch by shape (tools/sketch2therion/elevation.py)."""
import math
import unittest

from tools.sketch2therion import elevation as el, settings
from tools.sketch2therion.tidy import parse_scrap


class Shapes(unittest.TestCase):
    def test_pool_surface_is_straight_and_level(self):
        self.assertTrue(el.is_pool_surface([(0, 0), (0.6, 0.01), (1.2, 0.02)]))
        self.assertFalse(el.is_pool_surface([(0, 0), (0.6, 0.3), (1.2, 0.6)]))      # sloping
        self.assertFalse(el.is_pool_surface([(0, 0), (0.6, 0.3), (1.2, 0)]))        # bent

    def test_curl_is_rubble_floor_line_is_not(self):
        curl = [(0.3 + 0.25 * math.cos(t / 5), 0.25 * math.sin(t / 5)) for t in range(40)]
        self.assertTrue(el.is_squiggle(curl))
        self.assertFalse(el.is_squiggle([(x * 0.5, 0) for x in range(10)]))

    def test_curtain_hangs_and_is_long(self):
        self.assertTrue(el.is_curtain([(0, 0), (0.05, -0.6), (0, -1.3)]))
        self.assertFalse(el.is_curtain([(0, 0), (0, -0.6)]))                      # a stalactite's stroke
        self.assertFalse(el.is_curtain([(0, 0), (1.3, -0.2)]))

    def test_blocks_humpy_and_gentle_flowstone_smooth_steep_or_large(self):
        hump = lambda w: [(x * w / 12, w / 2.4 * math.sin(math.pi * x / 12)) for x in range(13)]
        self.assertTrue(el.is_blocks(hump(0.6)))       # rock-sized
        self.assertFalse(el.is_blocks(hump(1.2)))      # a lump of flowstone (GoSouth)
        self.assertFalse(el.is_blocks([(0, 0), (0.6, 0.02), (1.2, 0.03)]))
        steep = [(0, 0), (0.2, 0.9), (1.2, 1.5)]
        self.assertFalse(el.is_blocks(steep))


class Features(unittest.TestCase):
    def setUp(self):
        settings.load()

    def test_sorted_out(self):
        lines = [('BLUE', [(0, 0), (0.6, 0.0), (1.2, 0.01)]),                 # pool surface
                 ('BLUE', [(5, 1), (5.2, 1.1), (5.4, 0.95), (5.6, 1.05)]),     # flow
                 ('BLACK', [(8, 0), (8.6, 0), (8.6, 0.6), (8, 0.6), (8, 0.02)]),   # rock
                 ('BLACK', [(-5, -1), (15, -1)])]
        f = el.features(lines, [(3, 0.5)])
        self.assertEqual(len(f.pools), 1)
        self.assertEqual(len(f.flows), 1)
        self.assertEqual(len(f.rocks), 1)
        self.assertEqual([c for c, _ in f.lines], ['BLACK'])

    def test_flow_goes_under_the_floor_pointing_downhill(self):
        floor = [(0, 0), (10, -2)]
        (x, y), ori = el._floor_below([floor], (5, -0.5))
        self.assertAlmostEqual(y, -1.0, places=2)
        self.assertTrue(90 < ori < 180)                                       # right and down

    def test_bowl_only_where_no_floor(self):
        f = el.Features()
        f.pools = [(0, 2, 0)]
        self.assertEqual(len(el.bowls(f, [[(-1, -0.4), (3, -0.4)]])), 0)
        self.assertEqual(len(el.bowls(f, [])), 1)


class Adjusted(unittest.TestCase):
    def test_line_with_adjust_is_left_as_drawn(self):
        body = "line border -id p -close on -subtype invisible\n  0 0\n  10 0\n  adjust horizontal\n  5 -3\nendline\n"
        objs = parse_scrap(body)
        self.assertEqual([o.kind for o in objs if o.kind != 'text' or 'adjust' in o.raw][0], 'text')
        self.assertIn('adjust horizontal', ''.join(o.text() for o in objs))


if __name__ == '__main__':
    unittest.main()


class WallSubtypes(unittest.TestCase):
    def setUp(self):
        settings.load()

    def test_one_line_per_subtype_never_a_point_subtype(self):
        from tools.sketch2therion.smooth import wall_subtypes
        K = 100.0
        body = ("# wall-subtype sand: 500 0 1000 0\n\n"
                "line wall\n  0 0\n  250 0\n  500 0\n  750 0\n  1000 0\nendline\n")
        objs = parse_scrap(body)
        wall_subtypes(objs, K)
        text = '\n'.join(o.text() for o in objs)
        self.assertNotIn('  subtype', text)
        heads = [o.head for o in objs if o.kind == 'line']
        self.assertEqual(heads, ['line wall', 'line wall -subtype sand'])
        a, b = [o for o in objs if o.kind == 'line']
        self.assertEqual(a.segments()[-1][-2:], b.segments()[0][-2:])        # they meet

    def test_short_stretch_goes_with_its_neighbour(self):
        from tools.sketch2therion.smooth import wall_subtypes
        body = ("# wall-subtype sand: 0 0 400 0\n\n"
                "line wall\n  0 0\n  200 0\n  400 0\n  420 0\nendline\n")
        objs = parse_scrap(body)
        wall_subtypes(objs, 100.0)
        self.assertEqual([o.head for o in objs if o.kind == 'line'], ['line wall -subtype sand'])


class Scraps(unittest.TestCase):
    def test_stroke_drawn_on_goes_with_the_bigger_scrap(self):
        from tools.sketch2therion.convert import drawn_on
        a = [(0, 0), (5, 0)]
        b = [(5.1, 0), (12, 1)]
        lines = [('BLACK', a), ('BLACK', b)]
        out = drawn_on([(0, 'BLACK', list(a)), (1, 'BLACK', list(b))], lines, [20, 2])
        self.assertEqual([k for k, _, _ in out], [0, 0])     # the longer stroke joins the main scrap

    def test_glitch_cut_out(self):
        from tools.sketch2therion.convert import cut_glitches
        pp = [(0, 0), (1, 0), (1.5, 3), (2, 0), (3, 0)]
        out = cut_glitches([('BLACK', pp)], [[1.2, 1, 1.8, 4]])
        self.assertEqual([len(p) for _, p in out], [2, 2])


class BoulderFloor(unittest.TestCase):
    """A row of curls is a debris floor only where no floor line is drawn
    under it, through it or just over it (Style.md, hard rule 2)."""

    @staticmethod
    def row(y):
        return [('BROWN', [(x + 0.2 * math.cos(t / 3), y + 0.12 * math.sin(t / 3)) for t in range(19)])
                for x in [0.5 * i for i in range(10)]]

    def test_row_alone_is_a_floor(self):
        self.assertEqual(len(el.boulder_floor(self.row(0.0))), 1)

    def test_floor_over_the_tops(self):
        # BoldStep, user: a line through the tops of the rocks, smoothed
        (pp, kind), = el.boulder_floor(self.row(0.0))
        self.assertTrue(all(0.05 < y < 0.15 for x, y in pp))

    def test_row_on_a_line_under_it_is_not(self):
        self.assertEqual(el.boulder_floor(self.row(0.3) + [('BROWN', [(-1, 0), (6, 0)])]), [])

    def test_row_hanging_under_a_floor_line_is_not(self):
        # FairyChimneys 25 to 28: the small rocks drawn just below the brown floor line
        self.assertEqual(el.boulder_floor(self.row(-0.3) + [('BROWN', [(-1, 0), (6, 0)])]), [])


class Dashes(unittest.TestCase):
    """Two dashed lines side by side are two lines, not one zigzag (FairyChimneys 12)."""

    def tearDown(self):
        settings.use({})

    def test_side_by_side(self):
        from tools.sketch2therion import notation
        settings.use({'dash_neighbours': True})
        left = [('BLACK', [(0.0, y), (0.0, y + 0.3)]) for y in (0.0, 0.6, 1.2, 1.8)]
        right = [('BLACK', [(0.5, y + 0.3), (0.5, y + 0.6)]) for y in (0.0, 0.6, 1.2, 1.8)]
        found, used = notation.presumed(left + right, 1.2)
        self.assertEqual(len(found), 2)
        self.assertTrue(all(len({round(p[0], 1) for p in pp}) == 1 for pp in found))


class ShortLinks(unittest.TestCase):
    """A short stroke in a wall colour joined to the wall at both ends is wall (FairyChimneys 9)."""

    def tearDown(self):
        settings.use({})

    def test_link_kept_loose_mark_not(self):
        from tools.sketch2therion import convert
        settings.use({'wall_colours': ['BLACK', 'BROWN', 'GREEN'], 'short_links': True})
        a, link, b = [(0.0, 0.0), (2.0, 0.0)], [(2.1, 0.0), (2.6, 0.0)], [(2.7, 0.0), (5.0, 0.0)]
        loose = [(3.0, 1.0), (3.5, 1.0)]
        walls, _, _ = convert.wall_strokes([('BROWN', a), ('GREEN', link), ('BROWN', b), ('GREEN', loose)])
        self.assertIn(link, walls)
        self.assertNotIn(loose, walls)


class PitchFill(unittest.TestCase):
    def test_a_shaft_fills_sideways_to_its_walls(self):
        from shapely.geometry import Point
        from tools.sketch2therion.convert import elevation_fill
        walls = [[(-5.0, -1.0), (-5.0, 11.0)], [(6.0, 11.0), (6.0, -1.0)]]     # a shaft 11 m across
        legs = [((0.0, 0.0), (0.2, 10.0))]                                      # hung down its middle
        filled = lambda side: any(p.contains(Point(-4, 5)) and p.contains(Point(5, 5))
                                  for p in elevation_fill(walls, legs, side=side))
        self.assertTrue(filled(7.0))
        self.assertFalse(filled(0.0))       # without the side reach only the walls' and legs' edges
