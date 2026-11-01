"""[convert] colour_map: where passages overlap, purple is read as a wall
(black) and red and orange by shape as grey (Style.md, Sketching in SexyTopo)."""

import os
import unittest

from tools.sketch2therion import xvi
from tools.sketch2therion.settings import SETTINGS

from tools.sketch2therion.project import REPO     # the test cave
SKETCH = os.path.join(REPO, "TestCave", "TridentCentre", "Notes", "TridentCentreP.xvi")


@unittest.skipUnless(os.path.exists(SKETCH), "TridentCentre sketch not present")
class ColourMap(unittest.TestCase):
    def test_red_read_as_grey(self):
        keep = SETTINGS.get('colour_map')
        try:
            SETTINGS['colour_map'] = {}
            raw = [c for c, _ in xvi.read(SKETCH).lines]
            SETTINGS['colour_map'] = {'PURPLE': 'BLACK', 'RED': 'GRAY', 'ORANGE': 'GRAY'}
            mapped = [c for c, _ in xvi.read(SKETCH).lines]
        finally:
            SETTINGS['colour_map'] = keep
        self.assertIn('RED', raw)
        self.assertNotIn('RED', mapped)
        self.assertEqual(mapped.count('GRAY'), raw.count('GRAY') + raw.count('RED'))


if __name__ == "__main__":
    unittest.main()
