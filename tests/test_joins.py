"""Earlier plans cut back where a new survey joins (sketch2therion joins):
lines are cut by splitting a segment, no node moves, rows not cut stay as
written and option rows stay with their points."""

import unittest

try:
    from tools.sketch2therion import joins
    from tools.sketch2therion.tidy import Obj
except ImportError:          # shapely missing
    joins = None


@unittest.skipUnless(joins, "needs shapely")
class CutLine(unittest.TestCase):
    def line(self):
        return Obj('line', 'line wall -id w1', ['  0.0 0.0', '  10.0 0.0 20.0 0.0 30.0 0.0', '  smooth off',
                                                 '  40.0 0.0 50.0 0.0 60.0 0.0', '  90.5 0.0'])

    def test_middle_cut_leaves_two_lines(self):
        parts = joins.cut_line(self.line(), [(2, 0.5, 3, 0.5, 0, None)])
        self.assertEqual(len(parts), 2)
        first, second = parts
        self.assertEqual(first[:3], ['  0.0 0.0', '  10.0 0.0 20.0 0.0 30.0 0.0', '  smooth off'])
        self.assertTrue(first[-1].endswith('45.00 0.00'))          # half way along 30 to 60
        self.assertTrue(second[0].endswith('75.25 0.00'))         # half way along 60 to 90.5
        self.assertEqual(second[-1], '  90.5 0.0')                 # the end node as written

    def test_end_cut(self):
        parts = joins.cut_line(self.line(), [(3, 0.0, 3, 1.0, 0, None)])
        self.assertEqual(parts, [['  0.0 0.0', '  10.0 0.0 20.0 0.0 30.0 0.0', '  smooth off',
                                  '  40.0 0.0 50.0 0.0 60.0 0.0']])

    def test_split_point_on_the_curve(self):
        c = joins._cubic((0.0, 0.0), [0.0, 10.0, 10.0, 10.0, 10.0, 0.0])
        a, b = joins._split(c, 0.5)
        self.assertEqual(a[0], (0.0, 0.0))
        self.assertEqual(b[3], (10.0, 0.0))
        self.assertAlmostEqual(a[3][0], 5.0)
        self.assertAlmostEqual(a[3][1], 7.5)


if __name__ == "__main__":
    unittest.main()
