"""Legs and splays come from the drawing's own sketch (the backdrop .xvi),
so the tools run on any survey, not only those in this cave's build."""

import os
import tempfile
import unittest

try:
    from tools.sketch2therion import roofs, xvi
    from tools.sketch2therion.survey import survey_file
except ImportError:          # shapely missing
    roofs = None


def sketch():
    """Two stations 4 m apart, a splay 3 m sideways at 1 and one 2 m straight up at 2."""
    return xvi.Sketch({'1': [(0.0, 0.0)], '2': [(4.0, 0.0)]},
                      [((0.0, 0.0), (4.0, 0.0)), ((0.0, 0.0), (0.0, 3.0)), ((4.0, 0.0), (4.2, 2.0))], [])


def write(folder, name, text):
    path = os.path.join(folder, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    return path


@unittest.skipUnless(roofs, "needs shapely")
class SketchSplays(unittest.TestCase):
    def test_plan_gives_splay_ends(self):
        sp = roofs.Splays.from_sketch(sketch(), 'X', False)
        self.assertEqual(sp.legs['1@X'], {'2@X'})
        self.assertEqual(sp.ends['1@X'], [(0.0, 3.0)])
        self.assertEqual(sp.up, {})

    def test_elevation_gives_up_and_down(self):
        sp = roofs.Splays.from_sketch(sketch(), 'X', True)
        self.assertAlmostEqual(sp.up['2@X'], 2.0)
        self.assertAlmostEqual(sp.up['1@X'], 3.0)
        self.assertEqual(sp.down, {})
        self.assertEqual(dict(sp.ends), {})

    def test_drawing_reads_its_backdrop(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'Notes'))
            xvi.write(sketch(), os.path.join(tmp, 'Notes', 'XEe.xvi'))
            write(tmp, 'X.th', 'survey X\ninput "XEe.th2"\nendsurvey\n')
            th2 = write(tmp, 'XEe.th2', '##XTHERION## xth_me_image_insert {0.0 1 1.0} {0.0 1} "Notes/XEe.xvi" 0 {}\n'
                                        'scrap XE1 -projection extended\nendscrap\n')
            sp = roofs.Splays.from_drawing(th2)
            self.assertAlmostEqual(sp.up['2@X'], 2.0, places=3)      # xvi keeps hundredths of its units
            self.assertEqual(sp.legs['2@X'], {'1@X'})

    def test_drawing_without_backdrop_has_no_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            th2 = write(tmp, 'Y.th2', 'scrap YP1 -projection plan\nendscrap\n')
            self.assertEqual(dict(roofs.Splays.from_drawing(th2).legs), {})


@unittest.skipUnless(roofs, "needs shapely")
class SurveyFile(unittest.TestCase):
    def test_found_beside_or_above_the_sketch(self):
        with tempfile.TemporaryDirectory() as tmp:
            th = write(tmp, 'X.th', 'encoding utf-8\nsurvey X\nendsurvey\n')
            write(tmp, 'Other.th', 'survey XY\nendsurvey\n')
            self.assertEqual(survey_file('X', os.path.join(tmp, 'Notes', 'XP.xvi')), th)
            self.assertEqual(survey_file('X', os.path.join(tmp, 'X.plan.th2')), th)
            self.assertIsNone(survey_file('Z', os.path.join(tmp, 'X.plan.th2')))


if __name__ == "__main__":
    unittest.main()
