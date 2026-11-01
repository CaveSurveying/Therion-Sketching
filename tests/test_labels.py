"""SexyTopo's labels carried into the drawing, their letters left out of the
walls, and no drawing overwritten that the converter did not write."""

import os
import tempfile
import unittest

from tools.sketch2therion import labels

EXPORT = """encoding utf-8
##XTHERION## xth_me_image_insert {0.0 1 1.0} {0.0 1} "Notes/XEe.xvi" 0 {}
scrap XE1 -projection extended
point 0.0 0.0 station -name 1
point 100.0 0.0 station -name 2
point 300.0 -50.0 label -text " 2nd pitch " -scale l
endscrap
"""


def letter(x, y, h=0.6):
    """A letter as SexyTopo draws it: an upright stroke hanging below y."""
    return ('BLACK', [(x, y), (x, y - h)])


class Labels(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.tmp.name, 'Notes'))
        self.sketch = os.path.join(self.tmp.name, 'Notes', 'XEe.xvi')
        open(self.sketch, 'w').close()
        self.export = os.path.join(self.tmp.name, 'XEe.th2')
        with open(self.export, 'w', encoding='utf-8') as f:
            f.write(EXPORT)

    def tearDown(self):
        self.tmp.cleanup()

    def test_export_found_by_its_backdrop(self):
        self.assertTrue(labels.is_export(self.export))
        self.assertEqual(labels.export_for(self.sketch), self.export)
        self.assertEqual(labels.labels(self.export),
                         [(300.0, -50.0, ' 2nd pitch ', 'point 300.0 -50.0 label -text " 2nd pitch " -scale l')])

    def test_a_drawing_is_not_an_export(self):
        with open(self.export, 'a', encoding='utf-8') as f:
            f.write("scrap XE2\nline wall\n  0 0\n  1 1\nendline\nendscrap\n")
        self.assertFalse(labels.is_export(self.export))
        self.assertIsNone(labels.export_for(self.sketch))

    def test_letters_left_out_and_walls_kept(self):
        K = 50.0                                   # the label at (6, -1) m
        lines = [letter(6.0 + 0.45 * i, -1.0) for i in range(9)] + \
            [('BLACK', [(6.0, -1.0), (6.0, -9.0)]),           # a wall from the label down: too big for a letter
             letter(14.0, -1.0)]                               # a mark well past the text
        drop = labels.letter_strokes(lines, labels.labels(self.export), K)
        self.assertEqual(drop, set(range(9)))

    def test_points_go_in_the_scrap_with_the_nearest_station(self):
        text = ("scrap A\npoint 0 0 station -name 1\nendscrap\n"
                "scrap B\npoint 1000 0 station -name 9\nendscrap\n")
        out = labels.add_points(text, ['point 990 5 label -text "x" -scale m'])
        self.assertIn('point 1000 0 station -name 9\npoint 990 5 label -text "x" -scale m', out)


if __name__ == "__main__":
    unittest.main()
