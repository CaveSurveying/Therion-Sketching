"""gui.py on the test cave, without a screen (needs PySide6 or PyQt6)."""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from tools.sketch2therion import gui
except ImportError:
    gui = None

from tools.sketch2therion.project import REPO     # the test cave

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
        settings = gui.QtCore.QSettings(os.path.join(self.tmp.name, "gui.ini"), gui.QtCore.QSettings.Format.IniFormat)
        self.w = gui.Window(REPO, settings)
        self.w.python_edit.setText(sys.executable)

    def tearDown(self):
        self.w.close()
        self.tmp.cleanup()

    def test_trip_and_sketches(self):
        self.assertEqual([self.w.trip_combo.itemText(i) for i in range(self.w.trip_combo.count())], ["GoSouth", "Trident"])
        self.assertEqual(self.w.plan_combo.currentText(), "TestCave/GoSouth/Notes/GoSouthP.xvi")
        self.assertEqual(self.w.ext_combo.currentText(), "TestCave/GoSouth/Notes/GoSouthE.xvi")

    def test_no_extended_sketch_no_extended_steps(self):
        self.w.trip_combo.setCurrentText("Trident")
        on = {b.text() for b in self.w.buttons if b.isEnabled()}
        self.assertIn("plan", on)
        self.assertNotIn("extended", on)
        self.assertNotIn("Extended sketch", on)

    def test_options(self):
        self.w.author_name.setText("A N Other")
        self.w.copy_holder.setText("")
        self.w.floor_check.setChecked(True)
        o = self.w.options("plan")
        self.assertEqual(o.author[1], "A N Other")
        self.assertIsNone(o.copyright)                  # no holder: no --copyright
        self.assertEqual(o.floor, "TestCave/GoSouth/Notes/GoSouthE.xvi")
        self.assertIsNone(self.w.options("extended").floor)

    @unittest.skipUnless(HAVE_SHAPELY, "the scripts need shapely")
    def test_check_runs(self):
        self.w.run([gui.trip.check(self.w.trip, self.w.plan_combo.currentText())])
        while self.w.current:
            loop = gui.QtCore.QEventLoop()
            self.w.proc.finished.connect(loop.quit)
            loop.exec()
        self.assertIn("28 stations", self.w.log.toPlainText())
        self.assertEqual(self.w.state.text(), "check GoSouthP.xvi: done")


if __name__ == "__main__":
    unittest.main()
