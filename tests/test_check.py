"""check: the sketch's stations against the trip's own .th, so a trip can be
checked before it is tied into the cave (the test cave has no Therion layout)."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools.sketch2therion.project import REPO     # the test cave

TRIP = os.path.join(REPO, "TestCave", "GoSouth")


def check(folder):
    r = subprocess.run([sys.executable, "-m", "tools.sketch2therion", "check",
                        os.path.join(folder, "Notes", "GoSouthP.xvi"), "--survey", "GoSouth"],
                       cwd=REPO, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


class Check(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.trip = os.path.join(self.tmp.name, "GoSouth")      # not input by the test cave's master
        os.makedirs(os.path.join(self.trip, "Notes"))
        shutil.copy(os.path.join(TRIP, "GoSouth.th"), self.trip)
        shutil.copy(os.path.join(TRIP, "Notes", "GoSouthP.xvi"), os.path.join(self.trip, "Notes"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_trip_on_its_own(self):
        code, out = check(self.trip)
        self.assertEqual(code, 0, out)
        self.assertIn("28 stations", out)
        self.assertNotIn("NOT IN THE SURVEY", out)

    def test_station_off_the_legs(self):
        th = os.path.join(self.trip, "GoSouth.th")
        text = open(th, encoding="utf-8").read()
        open(th, "w", encoding="utf-8").write(re.sub(r"(?m)^28  29 ", "# 28  29 ", text))
        code, out = check(self.trip)
        self.assertEqual(code, 0, out)
        self.assertIn("NOT IN THE SURVEY (1): 29", out)

    def test_survey_needed(self):
        r = subprocess.run([sys.executable, "-m", "tools.sketch2therion", "check",
                            os.path.join(self.trip, "Notes", "GoSouthP.xvi")],
                           cwd=REPO, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--survey", r.stderr)


if __name__ == "__main__":
    unittest.main()
