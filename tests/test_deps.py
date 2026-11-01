import os
import tempfile
import unittest

from tools.sketch2therion import deps


def write(root, rel, text=""):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class ParseRefsTest(unittest.TestCase):
    def test_kinds_quotes_and_comments(self):
        refs = deps.parse_refs(
            'source "Cave.th"\n'
            "input ../common_layout.th\n"
            "#input Old/Old.th\n"
            "  # input Older.th\n"
            "  \\legendbox{0}{0}{SW}{\\loadpicture{Outputs/E.pdf}}\n"
            " %\\legendbox{0}{0}{SW}{\\loadpicture{Outputs/Gone.pdf}}\n")
        self.assertEqual([(r.kind, r.target, r.line) for r in refs],
                         [("source", "Cave.th", 1), ("input", "../common_layout.th", 2),
                          ("loadpicture", "Outputs/E.pdf", 5)])


class WalkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_relative_to_containing_file(self):
        # ../common_layout.th then Symbols/Symbols.th resolves to the root Symbols/
        write(self.root, "Cave/Plan_only.thcfg", "source Cave.th\ninput ../common_layout.th\n")
        write(self.root, "Cave/Cave.th", 'input "A/A.th"\n')
        write(self.root, "Cave/A/A.th", "input AP.th2\n")
        write(self.root, "Cave/A/AP.th2", "scrap AP1\nendscrap\n")
        write(self.root, "common_layout.th", "input Symbols/Symbols.th\n")
        write(self.root, "Symbols/Symbols.th", "")
        res = deps.walk(self.root, "Cave/Plan_only.thcfg")
        self.assertEqual(res.problems, [])
        self.assertEqual(sorted(deps.outside(res.files, "Cave")), ["Symbols/Symbols.th", "common_layout.th"])
        self.assertIn(os.path.join("Cave", "A", "AP.th2"), res.files)

    def test_loadpicture_relative_to_thconfig(self):
        write(self.root, "Cave/thconfig", "input layouts/l.th\n")
        write(self.root, "Cave/layouts/l.th", "\\loadpicture{Outputs/E.pdf}\n")
        write(self.root, "Cave/Outputs/E.pdf", "%PDF")
        res = deps.walk(self.root, "Cave/thconfig")
        self.assertEqual(res.problems, [])
        self.assertIn(os.path.join("Cave", "Outputs", "E.pdf"), res.files)

    def test_missing_target_names_file_and_line(self):
        write(self.root, "Cave/thconfig", "source Cave.th\n\ninput Gone.th\n")
        write(self.root, "Cave/Cave.th", "")
        res = deps.walk(self.root, "Cave/thconfig")
        self.assertEqual([(p.file, p.line, p.target, p.reason) for p in res.problems],
                         [(os.path.join("Cave", "thconfig"), 3, "Gone.th", "missing")])
        self.assertEqual(deps.main([self.root, "Cave/thconfig"]), 1)

    def test_case_differs(self):
        write(self.root, "Cave/thconfig", "input tickle/TickleWest.th\n")
        write(self.root, "Cave/Tickle/TickleWest.th", "")
        res = deps.walk(self.root, "Cave/thconfig")
        self.assertEqual(len(res.problems), 1)
        self.assertTrue(res.problems[0].reason.startswith("case differs"))
        self.assertIn(os.path.join("Cave", "Tickle", "TickleWest.th"), res.files)

    def test_input_without_extension(self):
        write(self.root, "Cave/thconfig", "input Cave\n")
        write(self.root, "Cave/Cave.th", "")
        self.assertEqual(deps.walk(self.root, "Cave/thconfig").problems, [])

    def test_loop_terminates(self):
        write(self.root, "Cave/thconfig", "input a.th\n")
        write(self.root, "Cave/a.th", "input b.th\n")
        write(self.root, "Cave/b.th", "input a.th\n")
        res = deps.walk(self.root, "Cave/thconfig")
        self.assertEqual(len(res.files), 3)


if __name__ == "__main__":
    unittest.main()
