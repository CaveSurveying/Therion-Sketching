"""trip.py: a cave's trips and the commands the GUI runs on them."""
import os
import subprocess
import sys
import tempfile
import unittest

from tools.sketch2therion import trip
from tools.sketch2therion.project import REPO     # the test cave


class Trips(unittest.TestCase):
    def setUp(self):
        self.p = trip.load_project(REPO)
        self.t = trip.Trip(self.p, "GoSouth")

    def test_surveys(self):
        self.assertEqual(self.p.surveys(), ["GoSouth", "Trident"])     # TridentCentre has no .th

    def test_files(self):
        self.assertEqual(self.t.th, "TestCave/GoSouth/GoSouth.th")
        self.assertEqual(self.t.plan_sketches(), ["TestCave/GoSouth/Notes/GoSouthP.xvi"])
        self.assertEqual(self.t.elevation_sketches(), ["TestCave/GoSouth/Notes/GoSouthE.xvi"])
        self.assertEqual(self.t.output("plan"), "TestCave/GoSouth/GoSouthP.th2")
        self.assertEqual(self.t.output("extended"), "TestCave/GoSouth/GoSouthEe.th2")

    def test_usual_extended_sketch_first(self):
        self.assertEqual(sorted(["a/XE315.xvi", "a/XEe.xvi"], key=lambda f: trip.EXTENDED_SKETCH.search(f) is None),
                         ["a/XEe.xvi", "a/XE315.xvi"])

    def test_plan_steps(self):
        opts = trip.Options(("2026.04.25", "A N Other"), ("2026", "Someone"), floor="TestCave/GoSouth/Notes/GoSouthE.xvi")
        cmds = trip.convert_all(self.t, "plan", "TestCave/GoSouth/Notes/GoSouthP.xvi", opts)
        self.assertEqual([c.args[0] for c in cmds], list(trip.STEPS["plan"]))
        self.assertEqual(cmds[0].line("py"), [
            "py", "-m", "tools.sketch2therion", "plan", "TestCave/GoSouth/Notes/GoSouthP.xvi",
            "--survey", "GoSouth", "-o", "TestCave/GoSouth/GoSouthP.th2",
            "--author", "2026.04.25", "A N Other", "--copyright", "2026", "Someone",
            "--floor", "TestCave/GoSouth/Notes/GoSouthE.xvi"])
        self.assertEqual(cmds[1].args, ["roofs", "TestCave/GoSouth/GoSouthP.th2"])

    def test_extended_takes_no_floor_and_force(self):
        c = trip.convert(self.t, "extended", "extended", "x.xvi", trip.Options(floor="y.xvi", force=True))
        self.assertNotIn("--floor", c.args)
        self.assertEqual(c.args[-1], "--force")
        self.assertEqual(trip.convert(self.t, "extended", "smooth", "x.xvi", trip.Options()).args,
                         ["smooth", "TestCave/GoSouth/GoSouthEe.th2"])

    def test_other_commands(self):
        self.assertEqual(trip.database().line("py"), ["therion", "-l", trip.LAYOUT_LOG, trip.LAYOUT_CONFIG])
        self.assertEqual(trip.sections(True).args, ["sections", "--write"])
        self.assertEqual(trip.th2lint(self.t).line("py")[:3], ["py", "-m", "tools.sketch2therion.th2lint"])
        self.assertEqual(trip.fillcheck(self.t).args, ["fillcheck", "--build", "--survey", "GoSouth"])

    def test_check_runs(self):
        c = trip.check(self.t, self.t.plan_sketches()[0])
        r = subprocess.run(c.line(sys.executable), cwd=REPO, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("28 stations", r.stdout)

    def test_needs_force_message(self):
        """The GUI asks before --force by what plan prints when a drawing is in the way."""
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "GoSouthP.th2")
            open(out, "w").write("encoding  utf-8\nscrap S1 -projection plan\nline wall\n  0 0\n  10 0\nendline\nendscrap\n")
            r = subprocess.run([sys.executable, "-m", "tools.sketch2therion", "plan", self.t.plan_sketches()[0],
                                "--survey", "GoSouth", "-o", out], cwd=REPO, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(trip.NEEDS_FORCE, r.stdout + r.stderr)

    def test_python_for(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(trip.python_for(d), sys.executable)
            os.makedirs(os.path.join(d, ".venv", "bin"))
            open(os.path.join(d, ".venv", "bin", "python"), "w").close()
            self.assertEqual(trip.python_for(d), os.path.join(d, ".venv", "bin", "python"))


if __name__ == "__main__":
    unittest.main()
