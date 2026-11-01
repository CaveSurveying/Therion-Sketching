"""Style.md rules the converter keeps: section arrows, no `-outline none`,
and the legs and splays check against the fill (log rows 121 to 123)."""
import math
import os
import tempfile
import unittest

from tools.sketch2therion import convert, fillcheck, settings, smooth
from tools.sketch2therion.tidy import parse_scrap


class Geo:
    """Two legs north from 1, splays 1 m either side."""
    def __init__(self):
        self.pos = {'1': (0.0, 0.0), '2': (0.0, 5.0), '3': (0.0, 10.0)}
        self.legs = [('1', '2'), ('2', '3')]
        self.splays = {n: [(1.0, 0.0), (-1.0, 0.0)] for n in self.pos}

    def half_width(self, n, perp):
        return 1.0


class SectionArrows(unittest.TestCase):
    def setUp(self):
        settings.load()

    def tearDown(self):
        settings.load()

    def lines(self, n):
        g = Geo()
        g.direction = lambda m: (0.0, -1.0)          # the passage's direction, either way round
        rows, _, _ = convert.section_line(g, n, lambda p: p)
        a = tuple(map(float, rows[1].split()))
        b = tuple(map(float, rows[2].split()))
        return rows[0], a, b

    def test_arrows_both_with_the_view_on_the_left(self):
        settings.SETTINGS['section_arrows'] = True
        for n in ('1', '2', '3'):                  # 3 has no next station: on from 2
            head, a, b = self.lines(n)
            self.assertEqual(head, "line section -direction both")
            d = (b[0] - a[0], b[1] - a[1])
            left = (-d[1], d[0])
            self.assertGreater(left[1], 0, n)      # the view (north, along the survey) on the line's left
            self.assertAlmostEqual(math.dist(a, b), 2 * (1.0 + convert.SECTION_MARGIN))

    def test_upstream_has_no_arrows(self):
        settings.SETTINGS['section_arrows'] = False
        head, a, b = self.lines('2')
        self.assertEqual(head, "line section")


SCRAP = """scrap s -projection plan -scale [0 0 100 0 0 0 1 0 m]
line wall
  0 0
  1000 0
endline
line wall
  1000 0
  1000 500
endline
line wall
  1000 500
  0 500
endline
line wall
  0 500
  0 0
endline
line wall -outline none
  200 250
  800 250
endline
endscrap
"""


class NoOutlineNone(unittest.TestCase):
    def test_none_left(self):
        objs = parse_scrap(SCRAP.split('\n', 1)[1].rsplit('endscrap', 1)[0])
        n = smooth.no_outline_none(objs, 100)
        self.assertEqual(n, 1)
        heads = [o.head for o in objs if o.kind == 'line']
        self.assertFalse(any('-outline none' in h for h in heads))
        self.assertEqual(sum(h.startswith('line wall') for h in heads), 4)
        self.assertEqual(heads.count('line border'), 1)      # inside the passage: the edge of something


class FillCheck(unittest.TestCase):
    def test_xvi_read_and_survey_names(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'x.xvi')
            open(p, 'w').write("set XVIgrids {1.0 m}\nset XVIstations {\n  {   0.00   0.00 1@A.Cave}\n"
                               "  {  19.69   0.00 2@A.Cave}\n}\nset XVIshots {\n"
                               "  {   0.00   0.00  19.69   0.00}\n  {   0.00   0.00   0.00  39.37}\n}\n"
                               "set XVIgrid  {-10 -10 19.685 0.0 0.0 19.685 2 2}\n")
            scale, st, shots = fillcheck.read_xvi(p)
        self.assertAlmostEqual(scale, 19.685)
        self.assertEqual(st['2@A.Cave'], (19.69, 0.0))
        self.assertEqual(len(shots), 2)
        self.assertEqual(fillcheck._survey('2@A.Cave'), 'A')


if __name__ == '__main__':
    unittest.main()


class AutoScraps(unittest.TestCase):
    """autoscraps.choose: cuts on simple passage, balanced, at least two stations."""

    def setUp(self):
        from collections import defaultdict
        from tools.sketch2therion import autoscraps
        self.a = autoscraps
        # a passage 1..9 with a side branch at 5 (5-10, 10-11)
        self.legs = [(str(i), str(i + 1)) for i in range(1, 9)] + [('5', '10'), ('10', '11')]
        self.length = {l: 1.0 for l in self.legs}
        self.degree = defaultdict(int)
        for x, y in self.legs:
            self.degree[x] += 1
            self.degree[y] += 1

    def test_cut_not_at_a_junction_and_balanced(self):
        clash = [(('1', '2'), ('8', '9'), 0.9)]
        cut, comps, left = self.a.choose(self.legs, clash, self.length, self.degree, 'plan')
        self.assertFalse(left)
        self.assertEqual(len(cut), 1)
        (x, y), = cut
        self.assertTrue(self.degree[x] <= 2 and self.degree[y] <= 2)      # plans: never at the junction at 5
        self.assertTrue(all(len({n for l in c for n in l}) >= 2 for c in comps))

    def test_elevation_cut_by_the_junction(self):
        clash = [(('1', '2'), ('8', '9'), 0.9)]
        cut, comps, left = self.a.choose(self.legs, clash, self.length, self.degree, 'extended')
        self.assertFalse(left)
        (x, y), = cut
        self.assertTrue(self.degree[x] > 2 or self.degree[y] > 2
                        or any(self.degree[n] > 2 for l in self.legs if set(l) & {x, y} for n in l))

    def test_no_clash_one_scrap(self):
        cut, comps, left = self.a.choose(self.legs, [], self.length, self.degree)
        self.assertEqual((len(cut), len(comps)), (0, 1))

    def test_elevation_branch_detached_at_the_junction(self):
        # Trident 10: the branch 5-10-11 rises over 5-6; the passage through 5 stays whole
        clash = [(('5', '10'), ('5', '6'), 0.9)]
        cut, comps, left = self.a.choose(self.legs, clash, self.length, self.degree, 'extended')
        self.assertFalse(left)
        self.assertEqual(cut, {('5', '10'): '5'})
        self.assertEqual(sorted(map(sorted, comps), key=len)[0], [('10', '11'), ('5', '10')])

    def test_elevation_long_branch_the_scrap_coming_in_ends(self):
        # FairyChimneys 16: a long branch 5-10-11 over 4-5 (the way in from 1); the scrap
        # from 1 ends at 5 and the next carries on from it with 5-6 and the branch
        length = dict(self.length)
        length[('5', '10')] = length[('10', '11')] = 4.0
        clash = [(('4', '5'), ('5', '10'), 0.5)]
        cut, comps, left = self.a.choose(self.legs, clash, length, self.degree, 'extended', '1')
        self.assertFalse(left)
        self.assertEqual(cut, {('4', '5'): '5'})
        other = [c for c in comps if ('5', '6') in c][0]
        self.assertIn(('5', '10'), other)

    def test_incoming(self):
        came = self.a.incoming(self.legs, '1')
        self.assertEqual(came['5'], ('4', '5'))
        self.assertEqual(came['10'], ('5', '10'))

    def test_plan_cut_by_a_junction_keeps_it_whole(self):
        # CJPitch, CJS, CrossRoads: a leg by the junction is cut, the junction in one scrap
        legs = [('1', '2'), ('2', '3'), ('3', '4'), ('2', '5'), ('5', '6')]
        degree = {'1': 1, '2': 3, '3': 2, '4': 1, '5': 2, '6': 1}
        cut, comps, left = self.a.choose(legs, [(('3', '4'), ('5', '6'), 0.9)], dict.fromkeys(legs, 1.0), degree, 'plan')
        self.assertFalse(left)
        (l, j), = cut.items()
        self.assertIn('2', l)
        self.assertIsNone(j)                       # in neither scrap
        at2 = [i for i, c in enumerate(comps) for x in c if '2' in x]
        self.assertEqual(len(set(at2)), 1)         # the junction whole in one scrap


class Passages(unittest.TestCase):
    """autoscraps: ways paired through junctions, passages, the score against a hand split."""

    def setUp(self):
        from collections import defaultdict
        from tools.sketch2therion import autoscraps
        self.a = autoscraps
        # Trident 10: 9 -> 10 -> 12 nearly straight; 11 -> 10 -> 13 the other way through
        self.pos = {'9': (0, -3, 0), '10': (0, 0, 0), '12': (0.5, 3, 0.5), '11': (-3, 0, 0), '13': (3, 0.5, 0), '14': (6, 0.5, 0)}
        self.legs = [('10', '9'), ('10', '12'), ('10', '11'), ('10', '13'), ('13', '14')]
        self.degree = defaultdict(int)
        for x, y in self.legs:
            self.degree[x] += 1
            self.degree[y] += 1

    def test_pairs_straightest(self):
        pairs = self.a.pair_ways(self.legs, self.pos, self.degree)['10']
        self.assertEqual({frozenset(p) for p in pairs},
                         {frozenset({('10', '9'), ('10', '12')}), frozenset({('10', '11'), ('10', '13')})})

    def test_passages_through_the_pairs(self):
        pairs = self.a.pair_ways(self.legs, self.pos, self.degree)
        ps = sorted(sorted(p) for p in self.a.passages(self.legs, pairs, self.degree))
        self.assertEqual(ps, [[('10', '11'), ('10', '13'), ('13', '14')], [('10', '12'), ('10', '9')]])

    def test_score(self):
        rows = self.a.score([['1', '2', '3'], ['4', '5']], [['1', '2'], ['3', '4', '5']])
        self.assertEqual(rows, [(0, 0, ['3'], []), (1, 1, [], ['3'])])
