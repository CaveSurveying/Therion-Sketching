"""gui.py on a small cave, without a screen (needs PySide6 or PyQt6)."""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from tools.sketch2therion import gui
except ImportError:
    gui = None

from test_trip import make_cave

try:
    import shapely  # noqa: F401  (the scripts run with this Python here)
    HAVE_SHAPELY = True
except ImportError:
    HAVE_SHAPELY = False


@unittest.skipIf(gui is None, "needs PySide6 or PyQt6")
class Window(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = gui.QtWidgets.QApplication.instance() or gui.QtWidgets.QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        cave = make_cave(os.path.join(self.tmp.name, "cave"))
        settings = gui.QtCore.QSettings(os.path.join(self.tmp.name, "gui.ini"), gui.QtCore.QSettings.Format.IniFormat)
        self.w = gui.Window(cave, settings)
        self.w.python_edit.setText(sys.executable)

    def tearDown(self):
        self.w.close()
        self.tmp.cleanup()

    def test_header(self):
        w = self.w
        self.assertEqual([w.trip_combo.itemText(i) for i in range(w.trip_combo.count())], ["GoSouth"])
        self.assertEqual(w.drawing("plan"), "TestCave/GoSouth/GoSouthP.th2")
        self.assertEqual(w.drawing("extended"), "TestCave/GoSouth/GoSouthEe.th2")
        self.assertEqual(w.sketch_label["plan"].text(), "Sketches: GoSouthP.xvi, GoSouthPX1.xvi")

    def test_tabs(self):
        titles = [self.w.tabs.tabText(i) for i in range(self.w.tabs.count())]
        self.assertEqual(titles, ["Plan", "Elevation", "Cave", "Credits", "Environment"])
        self.assertEqual(self.w.chosen()["plan"],                                        # all ticked to start with
                         ["check", "plan", "roofs", "details", "smooth", "review", "th2lint"])
        self.w.section_ticks["cave"].setChecked(False)
        self.w.part_ticks[("plan", "details")].setChecked(False)
        self.assertNotIn("cave", self.w.chosen())
        self.assertEqual(self.w.chosen()["plan"], ["check", "plan", "roofs", "smooth", "review", "th2lint"])

    def test_save_defaults(self):
        self.w.section_ticks["cave"].setChecked(False)
        self.w.part_ticks[("plan", "details")].setChecked(False)
        self.w.save_defaults()
        again = gui.Window(self.w.project.root, self.w.settings)
        self.assertNotIn("cave", again.chosen())
        self.assertEqual(again.chosen()["plan"], ["check", "plan", "roofs", "smooth", "review", "th2lint"])
        again.close()

    def test_every_option_explained(self):
        for key, _, parts in gui.trip.SECTIONS:
            for p in parts:
                self.assertTrue(p.short[0].isupper() and p.short.endswith('.') and p.detail, (key, p.key))

    def test_author_from_the_th(self):
        w = self.w
        self.assertEqual(w.author(), ("2026.04.25", "Andrew Atkinson"))     # the notes person, the .th's date
        self.assertEqual(w.author_from.text(), "(notes, in the .th)")             # beside it, not in it
        w.author_name.setEditText("Someone Else")
        self.assertEqual(w.author(), ("2026.04.25", "Someone Else"))
        self.assertEqual(w.author_from.text(), "(typed)")

    def test_licence_the_caves(self):
        self.assertEqual(self.w.licence_choice["default"].text(), "Default: GPLv3.0+")
        self.assertTrue(self.w.licence_choice["default"].isChecked())
        self.assertFalse(any(b.isEnabled() for b in self.w.licence_choice.values()))

    def test_defaults_and_copyright(self):
        w = self.w
        self.assertIsNone(w.copyright())                        # GoSouth.th has no copyright, no default set
        w.set_defaults("A Local", "A Club")
        self.assertIn("A Local", [w.author_name.itemText(i) for i in range(w.author_name.count())])
        self.assertTrue(w.copy_choice["default"].isChecked())
        self.assertEqual(w.copyright(), ("2026", "A Club"))
        w.copy_typed.setText("Someone")
        w.copy_choice["typed"].setChecked(True)
        self.assertEqual(w.copyright(), ("2026", "Someone"))
        w.copy_choice["none"].setChecked(True)
        self.assertIsNone(w.copyright())

    def test_floor_from_the_elevation_drawing(self):
        self.w.floor_check.setChecked(True)
        self.assertEqual(self.w.options("plan").floor, "TestCave/GoSouth/Notes/GoSouthE.xvi")
        self.assertIsNone(self.w.options("extended").floor)

    @unittest.skipUnless(HAVE_SHAPELY, "the scripts need shapely")
    def test_run_check(self):
        w = self.w
        for key, t in w.section_ticks.items():
            t.setChecked(key == "plan")
        for (key, part), t in w.part_ticks.items():
            t.setChecked(part == "check")
        w.run_ticked()
        while w.current:
            loop = gui.QtCore.QEventLoop()
            w.proc.finished.connect(loop.quit)
            loop.exec()
        self.assertEqual(w.log.toPlainText().count("28 stations"), 2)       # both sketches of the plan
        self.assertEqual(w.state.text(), "check GoSouthPX1.xvi: done")


if __name__ == "__main__":
    unittest.main()
