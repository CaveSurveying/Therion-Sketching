import os
import unittest

from tools.sketch2therion import project

MINIMAL = """
[cave]
name = "C"
title = "C"
folder = "C"
master = "C/C.th"
survey = "C"
thconfig = "C/Plan_only.thcfg"
plan_map = "CMP"
plan_map_file = "C/C.th"
[names]
survey_file = "{survey}/{survey}.th"
plan_file = "{survey}/{survey}.plan.th2"
scrap_prefix = "{survey}S"
survey_plan_map = "{survey}MP"
plan_sketch = '(\\\\.plan|P)\\\\.xvi$'
[drawing]
line_endings = "crlf"
map_scale = 200
licence = "CC BY-NC-SA 4.0"
[build]
outputs = "C/Outputs"
log = "output/therion.log"
layout_plan = "output/layout-plan.xvi"
layout_extended = "output/layout-extended.xvi"
sql = "output/layout.sql"
review_plan = "output/review-plan.pdf"
"""


class ProjectTest(unittest.TestCase):
    def setUp(self):
        self.p = project.load()

    def test_plan_sketches(self):
        for f in ["X/Notes/X.plan.xvi", "Triassic/PocketTopo/Triasic_p.xvi", "GoSouth/Notes/GoSouthP.xvi"]:
            self.assertTrue(self.p.is_plan_sketch(f), f)
        for f in ["X/Notes/X.ee.xvi", "GoSouth/Notes/GoSouthE.xvi", "TridentEe.xvi", "CyclopsE315.xvi",
                  "Triasic_e.xvi", "BoldStepEE.xvi", "NorthRiftE090.xvi"]:
            self.assertFalse(self.p.is_plan_sketch(f), f)

    def test_parse_minimal(self):
        p = project.parse(MINIMAL)
        self.assertEqual(p.newline, "\r\n")
        self.assertEqual(p.sheets, [])

    def test_missing_key_named(self):
        with self.assertRaisesRegex(project.ConfigError, "missing build.sql"):
            project.parse(MINIMAL.replace('sql = "output/layout.sql"\n', ""))
        with self.assertRaisesRegex(project.ConfigError, "missing cave.master"):
            project.parse(MINIMAL.replace('master = "C/C.th"\n', ""))

    def test_bad_values(self):
        with self.assertRaisesRegex(project.ConfigError, "line_endings"):
            project.parse(MINIMAL.replace('"crlf"', '"cr"'))
        with self.assertRaisesRegex(project.ConfigError, r"sheets\[0\].blurb"):
            project.parse(MINIMAL + '[[sheets]]\nfile = "a.pdf"\ntitle = "A"\n')


if __name__ == "__main__":
    unittest.main()
