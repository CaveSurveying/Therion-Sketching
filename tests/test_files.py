"""files.write: a step that changes nothing leaves the file and its date alone."""
import os
import subprocess
import sys
import tempfile
import unittest

from tools.sketch2therion import files
from tools.sketch2therion.project import REPO     # the test cave


def stamp(path):
    os.utime(path, ns=(1_000_000_000, 1_000_000_000))      # an old date, to see whether it moves


class Write(unittest.TestCase):
    def test_same_bytes_not_written(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.th2")
            self.assertTrue(files.write(p, b"x\n"))
            stamp(p)
            self.assertFalse(files.write(p, b"x\n"))
            self.assertEqual(os.stat(p).st_mtime_ns, 1_000_000_000)
            self.assertTrue(files.write(p, b"x\r\n"))
            self.assertEqual(open(p, "rb").read(), b"x\r\n")

    def test_roofs_rerun_leaves_the_drawing(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "GoSouthP.th2")
            run = lambda *a: subprocess.run([sys.executable, "-m", "tools.sketch2therion", *a],
                                            cwd=REPO, check=True, capture_output=True)
            run("plan", os.path.join(REPO, "TestCave", "GoSouth", "Notes", "GoSouthP.xvi"), "--survey", "GoSouth", "-o", out)
            for step in ("roofs", "details", "smooth"):
                run(step, out)
            for step in ("roofs", "details"):      # smooth changes it again each time (not yet fixed)
                stamp(out)
                run(step, out)
                self.assertEqual(os.stat(out).st_mtime_ns, 1_000_000_000, step)


if __name__ == "__main__":
    unittest.main()
