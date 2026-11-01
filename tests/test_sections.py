"""Cross sections keep the shape they were sketched (TridentLeft PX1, PX6,
PX10): an open stroke closed by a floor across its ends, small sections
not despiked to a sliver, and no section joined to another scrap."""

import math
import os
import unittest

try:
    from shapely.geometry import Polygon
    from tools.sketch2therion import settings, convert, smooth, scraps
    from tools.sketch2therion.tidy import bezier_points
except ImportError:          # shapely missing
    settings = None

K = 78.74016


def u_stroke(w=0.5, h=0.9, n=30):
    """Walls and roof of a small section, open at the bottom."""
    left = [(0.0, h * i / n) for i in range(n)]
    roof = [(w * i / n, h + 0.05 * math.sin(math.pi * i / n)) for i in range(n + 1)]
    right = [(w, h * (n - i) / n) for i in range(1, n + 1)]
    return left + roof + right


def pebble(x, y, r=0.03):
    pts = [(x + r * math.cos(2 * math.pi * i / 10), y + r * math.sin(2 * math.pi * i / 10)) for i in range(10)]
    return pts + [pts[0]]


@unittest.skipUnless(settings, "needs shapely")
class SectionShape(unittest.TestCase):
    def setUp(self):
        settings.load()

    def tearDown(self):
        settings.load()

    def test_open_stroke_closed_by_a_floor(self):
        u = u_stroke()
        out = convert.drawn_outline([('BLACK', u)] + [('BROWN', pebble(0.1 * k, 0.0)) for k in range(1, 5)],
                                    (0.25, 0.45))
        self.assertIsNotNone(out)
        poly, lines, taken = out
        self.assertEqual(lines[1], ([u[-1], u[0]], 'debris'))   # the floor straight across, pebbles on it
        self.assertGreater(poly.area, 0.4)                      # the whole section, about 0.5 x 0.9 m

    def test_floor_without_marks_is_plain_wall(self):
        self.assertIsNone(convert.drawn_outline([('BLACK', u_stroke())], (0.25, 0.45))[1][1][1])

    def test_closed_or_wide_open_strokes_not_floored(self):
        u = u_stroke()
        self.assertIsNone(convert.drawn_outline([('BLACK', u + [u[0]])], (0.25, 0.45)))   # closed already
        self.assertIsNone(convert.drawn_outline([('BLACK', u[20:-20])], (0.25, 0.45)))    # an arch, not a section

    def test_roof_and_brown_floor_with_sand_dashes(self):
        """FairyChimneys PX5: a black roof, a brown floor meeting its ends,
        and sand dashes under the floor: the dashes are not the outline."""
        roof = [(3.0 * i / 20, 0.6 * math.sin(math.pi * i / 20)) for i in range(21)]
        floor = [(3.0 - 3.0 * i / 20, -0.02) for i in range(21)]
        dashes = [[(0.2 * k, -0.1), (0.2 * k + 0.1, -0.25)] for k in range(1, 14)]
        strokes = [('BLACK', roof), ('BROWN', floor)] + [('BROWN', d) for d in dashes]
        poly, lines, taken = convert.drawn_outline(strokes, (1.5, 0.3))
        self.assertEqual([sub for _, sub in lines], [None, 'sand'])
        self.assertGreater(poly.bounds[1], -0.05)               # nothing below the floor
        self.assertEqual(lines[1][0][0], roof[-1])              # meeting the roof's ends
        self.assertEqual(lines[1][0][-1], roof[0])

    def test_section_written_with_its_floor(self):
        lines = [('BLACK', u_stroke())] + [('BROWN', pebble(0.1 * k, 0.0)) for k in range(1, 5)]
        o = convert.section_th2('XPX1', '', lines, (0.25, 0.45), K, '# test')[0]
        heads = [l for l in o if l.startswith('line ')]
        self.assertEqual(heads, ['line wall', 'line wall -subtype debris'])

    def test_section_on_the_walls_left(self):
        """Hard rule 6: sketched either way round (u_stroke is clockwise), the
        walls go round the section with it on their left."""
        from tools.sketch2therion import th2lint
        head = 'scrap XPX1 -projection none -author 2026 "A" -copyright 2026 "C"'
        for u in (u_stroke(), u_stroke()[::-1]):
            o = convert.section_th2('XPX1', '', [('BLACK', u)], (0.25, 0.45), K, '# test')[0]
            text = '\n'.join([head] + o[1:])
            self.assertEqual([f.rule for f in th2lint.lint_text(text) if f.rule == 'wall-side'], [])

    def test_small_section_not_despiked_to_a_sliver(self):
        lines = [('BLACK', u_stroke())] + [('BROWN', pebble(0.1 * k, 0.0)) for k in range(1, 5)]
        o = convert.section_th2('XPX1', '', lines, (0.25, 0.45), K, '# test')[0]
        header = 'scrap XPX1 -projection none -scale [0 0 787.40 787.40 0.0 0.0 10 10 m]'
        objs = smooth._redo_scrap(header, '\n'.join(o[1:o.index('endscrap')]) + '\n', 'x.th2')[0]
        before, _ = smooth._shape(smooth.parse_scrap('\n'.join(o[1:o.index('endscrap')]) + '\n'), True)
        after, _ = smooth._shape(objs, True)
        self.assertGreater(after['outline'], 0.9 * before['outline'])

    def test_section_joins_no_other_scrap(self):
        text = "\n".join([
            "scrap XSP1 -projection plan", "line wall", "  0 0", "  100 0", "endline", "endscrap",
            "scrap XPX1 -projection none", "line wall", "  50 3", "  50 60", "  80 60", "endline", "endscrap", ""])
        self.assertEqual(scraps.meet_on_walls(text, 10), text)
        self.assertEqual(scraps.meet_ends(text, 10), text)

    def test_drawing_moved_by_its_point_only(self):
        import tempfile
        from types import SimpleNamespace
        from tools.sketch2therion import sections as sec
        from tools.sketch2therion.tidy import parse_scrap
        plan = "point 0 0 station -name 1\npoint 50 100 section -scrap S\n"
        drawing = "line wall -close on\n  300 300\n  300 340\n  320 340\nendline\n"
        text = (f"scrap P -projection plan\n{plan}endscrap\n\n"
                f"scrap S -projection none\n{drawing}endscrap\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "X.plan.th2")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            d = SimpleNamespace(path=path, scraps=[("P", parse_scrap(plan), None)])
            sec.write(d, {}, {"S": (0, 1, (10.0, -5.0))})
            with open(path, encoding="utf-8") as f:
                out = f.read()
        self.assertIn("point 60.00 95.00 section -scrap S", out)
        self.assertIn(drawing, out)


if __name__ == "__main__":
    unittest.main()


class SectionLineEvenly(unittest.TestCase):
    def test_even_margins_and_arrow_left_off_near_another_passage(self):
        from shapely.geometry import box
        from tools.sketch2therion import sections as sec
        own = box(0, 0, 10, 2)                      # a passage 2 m wide, running east
        r = sec.redo_line((5.0, -0.3), (5.0, 4.0), own, None)
        (A, B), arrows, u = r
        self.assertAlmostEqual(A[1], -sec.MARGIN)
        self.assertAlmostEqual(B[1], 2 + sec.MARGIN)
        self.assertEqual(arrows, [True, True])
        # another passage 0.15 m north: the north end comes in to 0.1 m, its arrow kept
        (A, B), arrows, u = sec.redo_line((5.0, -0.3), (5.0, 4.0), own, box(0, 2.15, 10, 5))
        self.assertAlmostEqual(B[1], 2.1)
        self.assertEqual(arrows, [True, True])
        # only 0.05 m away: that arrow is left off
        (A, B), arrows, u = sec.redo_line((5.0, -0.3), (5.0, 4.0), own, box(0, 2.05, 10, 5))
        self.assertEqual(arrows, [True, False])

