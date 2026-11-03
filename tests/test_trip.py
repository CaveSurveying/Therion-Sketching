"""trip.py: a cave's trips, their drawings and the commands the GUI runs on them."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools.sketch2therion import trip
from tools.sketch2therion.project import REPO     # the test cave

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # this repository
NOTES = os.path.join(REPO, "TestCave", "GoSouth", "Notes")


def drawing(path, projection, *backdrops):
    open(path, "w").write("encoding  utf-8\n"
                          + "".join(f"##XTHERION## xth_me_image_insert {{0 1 1.0}} {{0 22}} {{{b}}} 0 {{}}\n" for b in backdrops)
                          + f"\nscrap S1 -projection {projection}\nendscrap\n")


def make_cave(d):
    """A cave in `d` like the test cave, with GoSouth's drawings: the plan
    links its sketch and a cross section's, the elevation its sketch."""
    os.makedirs(os.path.join(d, "tools"))
    shutil.copy(os.path.join(REPO, "tools", "project.toml"), os.path.join(d, "tools"))
    open(os.path.join(d, "tools", "__init__.py"), "w").close()
    os.symlink(TOP, os.path.join(d, "tools", "sketch2therion"))
    trip_dir = os.path.join(d, "TestCave", "GoSouth")
    shutil.copytree(NOTES, os.path.join(trip_dir, "Notes"))
    shutil.copy(os.path.join(NOTES, "GoSouthP.xvi"), os.path.join(trip_dir, "Notes", "GoSouthPX1.xvi"))
    shutil.copy(os.path.join(REPO, "TestCave", "GoSouth", "GoSouth.th"), trip_dir)
    drawing(os.path.join(trip_dir, "GoSouthP.th2"), "plan", "Notes/GoSouthP.xvi", "Notes/GoSouthPX1.xvi")
    drawing(os.path.join(trip_dir, "GoSouthEe.th2"), "extended", "Notes/GoSouthE.xvi")
    drawing(os.path.join(trip_dir, "GoSouthE315.th2"), "[elevation 315]")
    drawing(os.path.join(trip_dir, "NotInput.th2"), "plan", "Notes/GoSouthP.xvi")
    return d


class Trips(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = trip.load_project(make_cave(self.tmp.name))
        self.t = trip.Trip(self.p, "GoSouth")

    def tearDown(self):
        self.tmp.cleanup()

    def test_surveys(self):
        self.assertEqual(trip.load_project(REPO).surveys(), ["GoSouth", "Trident"])     # TridentCentre has no .th

    def test_drawings_input_by_the_th(self):
        self.assertEqual(self.t.drawings("plan"), ["TestCave/GoSouth/GoSouthP.th2"])
        self.assertEqual(self.t.drawings("extended"), ["TestCave/GoSouth/GoSouthEe.th2"])
        self.assertEqual(self.t.default_drawing("plan"), "TestCave/GoSouth/GoSouthP.th2")

    def test_every_sketch_of_a_drawing(self):
        self.assertEqual(self.t.sketches("TestCave/GoSouth/GoSouthP.th2"),
                         ["TestCave/GoSouth/Notes/GoSouthP.xvi", "TestCave/GoSouth/Notes/GoSouthPX1.xvi"])

    def test_details_from_the_th(self):
        d = self.t.details()
        self.assertEqual(d["date"], "2026.04.25")
        self.assertEqual(d["team"][0], ("Andrew Atkinson", "notes"))

    def test_commands_in_order(self):
        opts = trip.Options(("2026.04.25", "A N Other"), ("2026", "Someone"), floor="TestCave/GoSouth/Notes/GoSouthE.xvi")
        cmds = trip.commands(self.t, {"plan": ["th2lint", "smooth", "plan", "roofs", "check"]},
                             "TestCave/GoSouth/GoSouthP.th2", "TestCave/GoSouth/GoSouthEe.th2", opts, trip.Options())
        self.assertEqual([c.label for c in cmds], ["check GoSouthP.xvi", "check GoSouthPX1.xvi",
                                                   "Plan: plan", "Plan: roofs", "Plan: smooth", "th2lint GoSouthP.th2"])
        self.assertEqual(cmds[2].line("py"), [
            "py", "-m", "tools.sketch2therion", "plan", "TestCave/GoSouth/Notes/GoSouthP.xvi",
            "--survey", "GoSouth", "-o", "TestCave/GoSouth/GoSouthP.th2",
            "--author", "2026.04.25", "A N Other", "--copyright", "2026", "Someone",
            "--floor", "TestCave/GoSouth/Notes/GoSouthE.xvi"])
        self.assertEqual(cmds[3].args, ["roofs", "TestCave/GoSouth/GoSouthP.th2"])
        self.assertEqual(cmds[5].line("py"), ["py", "-m", "tools.sketch2therion.th2lint", "TestCave/GoSouth/GoSouthP.th2"])

    def test_elevation_checks(self):
        cmds = trip.commands(self.t, {"extended": ["check", "th2lint"]}, None, "TestCave/GoSouth/GoSouthEe.th2",
                             trip.Options(), trip.Options())
        self.assertEqual([c.args for c in cmds], [
            ["check", "TestCave/GoSouth/Notes/GoSouthE.xvi", "--survey", "GoSouth", "--elevation"],
            ["TestCave/GoSouth/GoSouthEe.th2"]])

    def test_extended_takes_no_floor(self):
        c = trip.convert(self.t, "extended", "extended", "TestCave/GoSouth/GoSouthEe.th2",
                         trip.Options(floor="y.xvi", force=True))
        self.assertEqual(c.args[:2], ["extended", "TestCave/GoSouth/Notes/GoSouthE.xvi"])
        self.assertNotIn("--floor", c.args)
        self.assertEqual(c.args[-1], "--force")

    def test_drawing_with_no_sketch(self):
        with self.assertRaises(ValueError):
            trip.convert(self.t, "extended", "extended", "TestCave/GoSouth/GoSouthE315.th2", trip.Options())

    def test_cave_commands(self):
        cmds = trip.commands(self.t, {"cave": ["database", "sections_write", "fillcheck"]},
                             None, None, trip.Options(), trip.Options(), "/opt/therion")
        self.assertEqual(cmds[0].line("py"), ["/opt/therion", "-l", trip.LAYOUT_LOG, trip.LAYOUT_CONFIG])
        self.assertEqual(cmds[1].args, ["sections", "--write"])
        self.assertEqual(cmds[2].args, ["fillcheck", "--build", "--survey", "GoSouth"])

    def test_check_runs(self):
        c = trip.check(self.t, self.t.sketches("TestCave/GoSouth/GoSouthP.th2")[0])
        r = subprocess.run(c.line(sys.executable), cwd=self.p.root, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("28 stations", r.stdout)

    def test_needs_force_message(self):
        """The GUI asks before --force by what plan prints when a drawing is in the way."""
        th2 = os.path.join(self.p.root, "TestCave", "GoSouth", "GoSouthP.th2")
        open(th2, "a").write("line wall\n  0 0\n  10 0\nendline\n")
        c = trip.convert(self.t, "plan", "plan", "TestCave/GoSouth/GoSouthP.th2", trip.Options())
        r = subprocess.run(c.line(sys.executable), cwd=self.p.root, capture_output=True, text=True)
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
