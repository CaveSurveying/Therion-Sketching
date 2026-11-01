"""Profile runs joined end to end (sketch2therion unfold --ee)."""

import unittest

try:
    from tools.sketch2therion import unfold, projected
except ImportError:          # shapely missing
    unfold = None


@unittest.skipUnless(unfold, "needs shapely")
class Joined(unittest.TestCase):
    def test_runs_meeting_become_one_line(self):
        runs = [[(0, 0), (1, 0)], [(1.2, 0), (2, 0)], [(5, 5), (6, 5)]]
        out = unfold._joined(runs, ['a', 'b', 'c'])
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0], ('a', [(0, 0), (1, 0), (2, 0)]))

    def test_a_run_reversed_to_join(self):
        out = unfold._joined([[(0, 0), (1, 0)], [(2, 0), (1.1, 0)]], ['a', 'b'])
        self.assertEqual(out, [('a', [(0, 0), (1, 0), (2, 0)])])


@unittest.skipUnless(unfold, "needs shapely")
class ProjectedNodes(unittest.TestCase):
    def test_dense_points_refitted_to_few_nodes(self):
        q = [(0.05 * i, 0.002 * (i % 2)) for i in range(101)]     # 5 m, a point every 5 cm
        rows = projected._fitted(q, lambda p: (100 * p[0], 100 * p[1]), 100)
        self.assertLessEqual(len(rows), 3)
        self.assertEqual(rows[0].split(), ['0.00', '0.00'])


if __name__ == "__main__":
    unittest.main()
