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
        self.assertEqual(titles, ["Check", "Plan", "Elevation", "Cave", "Checks", "Author", "Environment"])
        self.assertEqual(self.w.chosen(), {})                   # no tab ticked to start with
        self.w.section_ticks["plan"].setChecked(True)
        self.w.part_ticks[("plan", "details")].setChecked(False)
        self.assertEqual(self.w.chosen(), {"plan": ["plan", "roofs", "smooth"]})

    def test_author_from_the_th(self):
        w = self.w
        self.assertEqual(w.author(), ("2026.04.25", "Andrew Atkinson"))     # the notes person, the .th's date
        w.author_name.setEditText("Someone Else")
        self.assertEqual(w.author(), ("2026.04.25", "Someone Else"))

    def test_local_defaults(self):
        w = self.w
        w.local_author.setText("A Local")
        w.local_author.editingFinished.emit()
        self.assertIn("A Local (local default)", [w.author_name.itemText(i) for i in range(w.author_name.count())])
        self.assertIsNone(w.copyright())                        # GoSouth.th has no copyright, none set locally
        w.local_copyright.setText("A Club")
        w.local_copyright.editingFinished.emit()
        self.assertTrue(w.copy_choice["local"].isChecked())
        self.assertEqual(w.copyright(), ("2026", "A Club"))

    def test_floor_from_the_elevation_drawing(self):
        self.w.floor_check.setChecked(True)
        self.assertEqual(self.w.options("plan").floor, "TestCave/GoSouth/Notes/GoSouthE.xvi")
        self.assertIsNone(self.w.options("extended").floor)

    @unittest.skipUnless(HAVE_SHAPELY, "the scripts need shapely")
    def test_run_check(self):
        w = self.w
        w.section_ticks["check"].setChecked(True)
        w.part_ticks[("check", "extended")].setChecked(False)
        w.run_ticked()
        while w.current:
            loop = gui.QtCore.QEventLoop()
            w.proc.finished.connect(loop.quit)
            loop.exec()
        self.assertEqual(w.log.toPlainText().count("28 stations"), 2)       # both sketches of the plan
        self.assertEqual(w.state.text(), "check GoSouthPX1.xvi: done")


if __name__ == "__main__":
    unittest.main()
