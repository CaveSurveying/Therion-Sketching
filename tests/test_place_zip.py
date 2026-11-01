"""sketch2therion place and zip, on a small copy of a cave."""

import os
import shutil
import tempfile
import unittest
import zipfile

from tools.sketch2therion import project
from tools.sketch2therion import place, reviewzip

TOML = project.TOML                 # the test cave's

SURVEY_TH = """encoding  utf-8
survey GoSouth
# Created with SexyTopo

input "GoSouthP.th2"
input "GoSouthE.th2"
# input "Old.th2"

centreline
  1 2 3.0 10 0
endcentreline
endsurvey
"""

MASTER = """encoding  utf-8
survey TestCave
input GoSouth/GoSouth.th
map TestCaveMP
  CyclopsMP
  NorthRiftMP
endmap
map TestCaveM315
  CyclopsME315
endmap
endsurvey
"""

EMPTY = "encoding utf-8\nscrap GoSouthSP1 -projection plan\npoint 0 0 station -name 1\nendscrap\n"
DRAWN = ('encoding  utf-8\n##XTHERION## xth_me_image_insert {667.33 1 1.0} {-1568.15 22} {Notes/GoSouthP.xvi} 0 {}\n'
         'scrap GoSouthSP1 -projection plan\nline wall\n  0 0\n  1 1\nendline\nendscrap\n'
         'scrap GoSouthSP2 -projection plan\nline wall\n  2 2\n  3 3\nendline\nendscrap\n'
         'scrap GoSouthSEe1 -projection extended\nendscrap\n')


class Fixture(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.p = project.load(TOML, root=self.root)
        # a cave whose drawing is not SexyTopo's file: place removes the empty export
        self.p.names = dict(self.p.names, plan_file="{survey}/{survey}.plan.th2")
        self.dir = os.path.join(self.root, "TestCave", "GoSouth")
        os.makedirs(os.path.join(self.dir, "Notes"))
        self.put("TestCave/GoSouth/GoSouth.th", SURVEY_TH)
        self.put("TestCave/TestCave.th", MASTER)
        self.put("TestCave/GoSouth/GoSouthP.th2", EMPTY)
        self.put("TestCave/GoSouth/GoSouth.plan.th2", DRAWN)
        self.put("TestCave/GoSouth/Notes/GoSouthP.xvi", "set XVIgrids {1 m}\n")
        self.put("TestCave/GoSouth/Notes/GoSouthE.xvi", "set XVIgrids {1 m}\n")

    def put(self, rel, text, newline="\n"):
        with open(os.path.join(self.root, rel), "wb") as f:
            f.write(text.replace("\n", newline).encode())

    def get(self, rel):
        with open(os.path.join(self.root, rel), "rb") as f:
            return f.read().decode()


class PlaceTest(Fixture):
    def test_place(self):
        done = place.place("GoSouth", self.p)
        self.assertEqual(len(done), 3)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "GoSouthP.th2")))
        th = self.get("TestCave/GoSouth/GoSouth.th")
        self.assertIn('input "GoSouth.plan.th2"\n\nmap GoSouthMP\n  GoSouthSP1\n  GoSouthSP2\nendmap\n'
                      'input "GoSouthE.th2"', th)
        self.assertIn('# input "Old.th2"', th)                       # comments left alone
        self.assertNotIn("GoSouthSEe1", th)                           # plan scraps only
        master = self.get("TestCave/TestCave.th")
        self.assertIn("  NorthRiftMP\n  GoSouthMP@GoSouth\nendmap\nmap TestCaveM315", master)

    def test_drawing_is_the_sexytopo_file(self):
        self.p.names = dict(self.p.names, plan_file="{survey}/{survey}P.th2")
        self.put("TestCave/GoSouth/GoSouthP.th2", DRAWN)
        place.place("GoSouth", self.p)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "GoSouthP.th2")))
        self.assertIn('input "GoSouthP.th2"\n\nmap GoSouthMP\n  GoSouthSP1\n  GoSouthSP2\nendmap\n',
                      self.get("TestCave/GoSouth/GoSouth.th"))

    def test_twice_changes_nothing(self):
        place.place("GoSouth", self.p)
        before = (self.get("TestCave/GoSouth/GoSouth.th"), self.get("TestCave/TestCave.th"))
        self.assertEqual(place.place("GoSouth", self.p), [])
        after = (self.get("TestCave/GoSouth/GoSouth.th"), self.get("TestCave/TestCave.th"))
        self.assertEqual(before, after)

    def test_map_updated_when_scraps_change(self):
        place.place("GoSouth", self.p)
        self.put("TestCave/GoSouth/GoSouth.plan.th2", DRAWN.replace("GoSouthSP2", "GoSouthSP3"))
        place.place("GoSouth", self.p)
        th = self.get("TestCave/GoSouth/GoSouth.th")
        self.assertEqual(th.count("map GoSouthMP"), 1)
        self.assertIn("  GoSouthSP3\n", th)
        self.assertNotIn("GoSouthSP2", th)

    def test_keeps_crlf(self):
        self.put("TestCave/GoSouth/GoSouth.th", SURVEY_TH, "\r\n")
        self.put("TestCave/TestCave.th", MASTER, "\r\n")
        place.place("GoSouth", self.p)
        for rel in ["TestCave/GoSouth/GoSouth.th", "TestCave/TestCave.th"]:
            raw = open(os.path.join(self.root, rel), "rb").read()
            self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"), rel)

    def test_refuses_drawn_sexytopo_file(self):
        self.put("TestCave/GoSouth/GoSouthP.th2", DRAWN)
        with self.assertRaisesRegex(place.PlaceError, "has walls drawn"):
            place.place("GoSouth", self.p)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "GoSouthP.th2")))

    def test_needs_the_drawing(self):
        os.remove(os.path.join(self.dir, "GoSouth.plan.th2"))
        with self.assertRaisesRegex(place.PlaceError, "convert the sketch first"):
            place.place("GoSouth", self.p)

    def test_input_added_when_missing(self):
        self.assertEqual(place.fix_input("survey X\ncentreline\n", "XP.th2", "X.plan.th2"),
                         'survey X\n\ninput "X.plan.th2"\ncentreline\n')

    def test_add_to_map_once(self):
        text = place.add_to_map(MASTER, "TestCaveMP", "GoSouthMP@GoSouth")
        self.assertEqual(place.add_to_map(text, "TestCaveMP", "GoSouthMP@GoSouth"), text)
        with self.assertRaisesRegex(place.PlaceError, "no map Nope"):
            place.add_to_map(MASTER, "Nope", "x")


class ZipTest(Fixture):
    def test_backdrops(self):
        self.assertEqual(reviewzip.backdrops(DRAWN), ["Notes/GoSouthP.xvi"])
        self.assertEqual(reviewzip.backdrops('##XTHERION## xth_me_image_insert {0.0 1 1.0} {0.0 1} "Notes/a.xvi" 0 {}\n'),
                         ["Notes/a.xvi"])

    def test_zip(self):
        extra = os.path.join(self.root, "review")
        os.makedirs(extra)
        self.put("review/NOTES.md", "notes\n")
        out = os.path.join(self.root, "r.zip")
        names = reviewzip.write("GoSouth", out, extra, self.p)
        self.assertEqual(names, ["TestCave/GoSouth/GoSouth.plan.th2", "TestCave/GoSouth/GoSouth.th",
                                 "TestCave/GoSouth/Notes/GoSouthP.xvi",
                                 "TestCave/TestCave.th", "review/NOTES.md"])
        with zipfile.ZipFile(out) as z:
            plan = z.read("TestCave/GoSouth/GoSouth.plan.th2").decode()
            backdrop = os.path.normpath(os.path.join("TestCave/GoSouth", reviewzip.backdrops(plan)[0]))
            self.assertIn(backdrop, z.namelist())                 # the backdrop resolves inside the zip

    def test_bytes_unchanged(self):
        self.put("TestCave/GoSouth/GoSouth.plan.th2", DRAWN, "\r\n")
        out = os.path.join(self.root, "r.zip")
        reviewzip.write("GoSouth", out, None, self.p)
        with zipfile.ZipFile(out) as z:
            self.assertEqual(z.read("TestCave/GoSouth/GoSouth.plan.th2"),
                             open(os.path.join(self.dir, "GoSouth.plan.th2"), "rb").read())

    def test_missing_backdrop_fails(self):
        os.remove(os.path.join(self.dir, "Notes", "GoSouthP.xvi"))
        with self.assertRaisesRegex(FileNotFoundError, "backdrop Notes/GoSouthP.xvi"):
            reviewzip.contents("GoSouth", self.p)


if __name__ == "__main__":
    unittest.main()
