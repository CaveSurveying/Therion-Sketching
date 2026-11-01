"""Projected elevations from the extended drawing (tools/sketch2therion/projected.py, loch.py)."""
import math
import os
import struct
import tempfile
import unittest

from tools.sketch2therion import loch, projected as pj


class Mapping(unittest.TestCase):
    def test_point_keeps_place_along_leg_and_height(self):
        ext = {'1': (0, 0), '2': (10, 0)}
        proj = {'1': (0, 0), '2': (5, 0)}               # the leg seen at half its length
        pr = pj.Projection(ext, proj, [('1', '2')])
        x, y = pr((4, 1.5))
        self.assertAlmostEqual(x, 2.0)
        self.assertAlmostEqual(y, 1.5)

    def test_mirrored_leg_has_negative_scale(self):
        pr = pj.Projection({'1': (0, 0), '2': (10, 0)}, {'1': (0, 0), '2': (-8, 0)}, [('1', '2')])
        self.assertLess(pr.s[('1', '2')], 0)


class Model(unittest.TestCase):
    def model(self, stations, legs, tris):
        m = loch.Model()
        m.stations, m.legs, m.triangles = stations, legs, tris
        return m

    def tube(self, a, b, r=0.5):
        """Triangles of a square tube round the leg a-b (north-south or east-west)."""
        out = []
        horiz = (0, r, 0) if a[0] != b[0] else (r, 0, 0)
        for s in (1, -1):
            for up in (r, -r):
                p = [a[0] + s * horiz[0], a[1] + s * horiz[1], a[2] + up]
                q = [b[0] + s * horiz[0], b[1] + s * horiz[1], b[2] + up]
                out.append((tuple(p), tuple(q), (q[0], q[1], q[2] - up)))
        return out

    def test_passage_folding_back_in_front_of_itself_is_two_scraps(self):
        # 1-2-3 east, then 3-4 north, 4-5 back west, in front (seen facing north) of 1-2
        st = {'1': (0, 0, 0), '2': (5, 0, 0), '3': (10, 0, 0), '4': (10, -4, 0), '5': (0, -4, 0)}
        legs = [('1', '2'), ('2', '3'), ('3', '4'), ('4', '5')]
        tris = sum((self.tube(st[a], st[b]) for a, b in legs), [])
        groups = pj.model_groups(legs, self.model(st, legs, tris), 0)
        self.assertGreaterEqual(len(groups), 2)
        self.assertFalse(any({('1', '2'), ('4', '5')} <= set(g) for g in groups))

    def test_straight_passage_is_one_scrap(self):
        st = {'1': (0, 0, 0), '2': (5, 0, 0), '3': (10, 0, 0)}
        legs = [('1', '2'), ('2', '3')]
        tris = sum((self.tube(st[a], st[b]) for a, b in legs), [])
        self.assertEqual(len(pj.model_groups(legs, self.model(st, legs, tris), 0)), 1)


class Loch(unittest.TestCase):
    def test_reads_stations_legs_and_walls(self):
        data = b'S\0' + b'1\0' + b'2\0'
        survey = struct.pack('<6I', 0, 0, 2, 0, 0, 0)
        st = b''.join(struct.pack('<6I', i, 0, pos, 2, 0, 0) + struct.pack('<I', 0) + struct.pack('<3d', *xyz)
                      for i, pos, xyz in ((0, 2, (0, 0, 0)), (1, 4, (3, 4, 0))))
        shot = struct.pack('<2I', 0, 1) + b'\0' * 40
        pts = struct.pack('<9d', 0, 0, 0, 1, 0, 0, 0, 1, 0)
        tri = struct.pack('<3I', 0, 1, 2)
        scrap = struct.pack('<8I', 0, 0, 3, 0, len(pts), 1, len(pts), len(tri))
        raw = (struct.pack('<4I', 1, len(survey), 1, len(data)) + survey + data +
               struct.pack('<4I', 2, len(st), 2, len(data)) + st + data +
               struct.pack('<4I', 3, len(shot), 1, 0) + shot +
               struct.pack('<4I', 4, len(scrap), 1, len(pts + tri)) + scrap + pts + tri)
        with tempfile.NamedTemporaryFile(suffix='.lox', delete=False) as f:
            f.write(raw)
        try:
            m = loch.read(f.name)
        finally:
            os.unlink(f.name)
        self.assertEqual(m.stations['2'], (3.0, 4.0, 0.0))
        self.assertEqual(m.legs, [('1', '2')])
        self.assertEqual(len(m.triangles), 1)


if __name__ == '__main__':
    unittest.main()
