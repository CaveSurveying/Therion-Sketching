# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""A window that runs the converter on a new trip, step by step (GUI.md).

    python3 -m tools.sketch2therion.gui [CAVE]

CAVE is the cave's repository (default: here, else the last one used).
Every step is a command line from trip.py, run in the cave's folder.
"""
import datetime
import os
import shlex
import shutil
import sys

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PyQt6 import QtCore, QtGui, QtWidgets

from . import trip

Yes = QtWidgets.QMessageBox.StandardButton.Yes
No = QtWidgets.QMessageBox.StandardButton.No


def is_cave(folder):
    return bool(folder) and os.path.exists(os.path.join(folder, 'tools', 'project.toml'))


class Window(QtWidgets.QMainWindow):
    def __init__(self, cave=None, settings=None):
        super().__init__()
        self.setWindowTitle('Therion Sketching')
        self.settings = settings or QtCore.QSettings('CaveSurveying', 'Therion-Sketching')
        self.project = self.trip = None
        self.queue = []                 # commands still to run
        self.current = None
        self.status = {}                # step key -> its status label
        self.buttons = []
        self.proc = QtCore.QProcess(self)
        self.proc.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.MergedChannels)
        env = QtCore.QProcessEnvironment.systemEnvironment()
        env.insert('PYTHONUNBUFFERED', '1')            # output as it comes
        self.proc.setProcessEnvironment(env)
        self.proc.readyReadStandardOutput.connect(self._output)
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(self._error)
        self.output = ''

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        top = QtWidgets.QVBoxLayout(central)
        top.addWidget(self._settings_box())
        top.addWidget(self._steps_box())
        self.log = QtWidgets.QPlainTextEdit(readOnly=True)
        self.log.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont))
        self.log.setMaximumBlockCount(20000)
        top.addWidget(self.log, 1)
        self.resize(900, 900)

        cave = cave or (os.getcwd() if is_cave(os.getcwd()) else self.settings.value('cave', ''))
        self.cave_edit.setText(cave)
        self._load_cave()

    # --- the cave, the trip and the drawing options -------------------------

    def _settings_box(self):
        box = QtWidgets.QGroupBox('Trip')
        form = QtWidgets.QFormLayout(box)
        self.cave_edit = QtWidgets.QLineEdit()
        self.cave_edit.editingFinished.connect(self._load_cave)
        form.addRow('Cave', self._with_browse(self.cave_edit, self._browse_cave))
        self.python_edit = QtWidgets.QLineEdit()
        self.python_edit.setToolTip("The Python that runs the scripts (needs requirements.txt)")
        self.python_edit.editingFinished.connect(lambda: self._remember('python', self.python_edit.text()))
        form.addRow('Python', self._with_browse(self.python_edit, self._browse_python))
        self.trip_combo = QtWidgets.QComboBox()
        self.trip_combo.currentTextChanged.connect(self._load_trip)
        form.addRow('Survey', self.trip_combo)
        self.plan_combo = QtWidgets.QComboBox()
        form.addRow('Plan sketch', self.plan_combo)
        self.ext_combo = QtWidgets.QComboBox()
        form.addRow('Extended sketch', self.ext_combo)
        for c in (self.plan_combo, self.ext_combo):
            c.currentTextChanged.connect(lambda _: self._enable())
        self.files_label = QtWidgets.QLabel()
        form.addRow('Drawings', self.files_label)

        today = datetime.date.today()
        self.author_date = QtWidgets.QLineEdit(today.strftime('%Y.%m.%d'))
        self.author_date.setToolTip('The survey date, YYYY.MM.DD')
        self.author_name = QtWidgets.QLineEdit()
        self.author_name.editingFinished.connect(lambda: self._remember('author', self.author_name.text()))
        form.addRow('Author', self._row(self.author_date, self.author_name))
        self.copy_year = QtWidgets.QLineEdit(str(today.year))
        self.copy_holder = QtWidgets.QLineEdit()
        self.copy_holder.editingFinished.connect(lambda: self._remember('copyright', self.copy_holder.text()))
        form.addRow('Copyright', self._row(self.copy_year, self.copy_holder))
        self.floor_check = QtWidgets.QCheckBox('Plan: floor steps from the extended sketch (--floor)')
        form.addRow('', self.floor_check)
        return box

    def _row(self, *widgets):
        w = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        for x in widgets:
            h.addWidget(x)
        return w

    def _with_browse(self, edit, browse):
        b = QtWidgets.QPushButton('Browse…')
        b.clicked.connect(browse)
        return self._row(edit, b)

    def _browse_cave(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "The cave's repository", self.cave_edit.text())
        if d:
            self.cave_edit.setText(d)
            self._load_cave()

    def _browse_python(self):
        f, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Python', self.python_edit.text())
        if f:
            self.python_edit.setText(f)
            self._remember('python', f)

    def _key(self, name):
        """A setting kept for each cave."""
        return f"caves/{self.cave_edit.text().replace('/', '|')}/{name}"

    def _remember(self, name, value):
        if self.project:
            self.settings.setValue(self._key(name), value)

    def _load_cave(self):
        cave = os.path.abspath(self.cave_edit.text()) if self.cave_edit.text() else ''
        self.project = None
        self.trip_combo.clear()
        if not is_cave(cave):
            self._say(f"{cave or 'No cave'}: not a cave's repository (no tools/project.toml)")
            self._enable()
            return
        try:
            self.project = trip.load_project(cave)
        except Exception as e:          # a project.toml that can't be read
            self._say(f"{cave}/tools/project.toml: {e}")
            self._enable()
            return
        self.cave_edit.setText(cave)
        self.settings.setValue('cave', cave)
        self.python_edit.setText(self.settings.value(self._key('python'), '') or trip.python_for(cave))
        self.author_name.setText(self.settings.value(self._key('author'), ''))
        self.copy_holder.setText(self.settings.value(self._key('copyright'), ''))
        last = self.settings.value(self._key('survey'), '')
        self.trip_combo.addItems(self.project.surveys())
        if last in self.project.surveys():
            self.trip_combo.setCurrentText(last)
        self._say(f"{self.project.cave['title']}: {self.trip_combo.count()} surveys in {self.project.cave['folder']}")
        self._enable()

    def _load_trip(self, survey):
        self.trip = trip.Trip(self.project, survey) if self.project and survey else None
        self.plan_combo.clear()
        self.ext_combo.clear()
        if self.trip:
            self._remember('survey', survey)
            self.plan_combo.addItems(self.trip.plan_sketches())
            self.ext_combo.addItems(self.trip.elevation_sketches())
            for s in self.status.values():
                s.setText('')
        self._show_files()
        self._enable()

    def _show_files(self):
        if not self.trip:
            self.files_label.setText('')
            return
        self.files_label.setText('   '.join(f"{f} {'✓' if self.trip.exists(f) else '(not yet)'}"
                                           for f in (self.trip.plan_file, self.trip.extended_file)))

    def options(self, view):
        author = (self.author_date.text().strip(), self.author_name.text().strip())
        copyright = (self.copy_year.text().strip(), self.copy_holder.text().strip())
        floor = self.ext_combo.currentText() if view == 'plan' and self.floor_check.isChecked() else None
        return trip.Options(author if all(author) else None, copyright if all(copyright) else None, floor or None)

    # --- the steps ----------------------------------------------------------

    def _steps_box(self):
        box = QtWidgets.QGroupBox('Steps')
        grid = QtWidgets.QGridLayout(box)
        rows = [
            ('Check', [('Plan sketch', lambda: [trip.check(self.trip, self._sketch('plan'))], 'plan'),
                       ('Extended sketch', lambda: [trip.check(self.trip, self._sketch('extended'), True)], 'extended')]),
            ('Plan', [(s, self._convert('plan', s), 'plan') for s in trip.STEPS['plan']]
                     + [('All in order', self._convert('plan'), 'plan')]),
            ('Extended', [(s, self._convert('extended', s), 'extended') for s in trip.STEPS['extended']]
                         + [('All in order', self._convert('extended'), 'extended')]),
            ('Cave', [("Therion's database", lambda: [trip.database()], None),
                      ('Place plan', lambda: [trip.place(self.trip)], None),
                      ('Sections (report)', lambda: [trip.sections()], None),
                      ('Sections --write', self._sections_write, None)]),
            ('Checks', [('review check', lambda: [trip.review_check(self.trip)], None),
                        ('th2lint', lambda: [trip.th2lint(self.trip)], None),
                        ('fillcheck', lambda: [trip.fillcheck(self.trip)], None)]),
        ]
        for r, (group, steps) in enumerate(rows):
            grid.addWidget(QtWidgets.QLabel(f'<b>{group}</b>'), r, 0)
            for c, (label, make, needs) in enumerate(steps):
                b = QtWidgets.QPushButton(label)
                b.clicked.connect(lambda _=False, m=make: self.run(m()))
                b.needs = needs
                self.buttons.append(b)
                grid.addWidget(b, r, c + 1)
        r = len(rows)
        self.xtherion = QtWidgets.QPushButton('Open plan in xTherion')
        self.xtherion.clicked.connect(lambda: self._open(self.trip.plan_file))
        self.xtherion.setEnabled(bool(shutil.which('xtherion')))
        grid.addWidget(self.xtherion, r, 1, 1, 2)
        self.stop = QtWidgets.QPushButton('Stop')
        self.stop.clicked.connect(self._stop)
        grid.addWidget(self.stop, r, 5)
        self.state = QtWidgets.QLabel()
        grid.addWidget(self.state, r + 1, 0, 1, 6)
        return box

    def _sketch(self, view):
        return (self.plan_combo if view == 'plan' else self.ext_combo).currentText()

    def _convert(self, view, step=None):
        """The commands for one of the drawing's steps, or all of them."""
        def make():
            sketch, opts = self._sketch(view), self.options(view)
            return [trip.convert(self.trip, view, step, sketch, opts)] if step else \
                trip.convert_all(self.trip, view, sketch, opts)
        return make

    def _sections_write(self):
        ask = QtWidgets.QMessageBox.question(
            self, 'Sections', 'sections --write changes every plan drawing the master file inputs. Go on?', Yes | No)
        return [trip.sections(True)] if ask == Yes else []

    def _open(self, rel):
        QtCore.QProcess.startDetached('xtherion', [self.project.path(rel)], self.project.root)

    def _enable(self):
        busy = self.proc.state() != QtCore.QProcess.ProcessState.NotRunning
        for b in self.buttons:
            ok = bool(self.trip) and not busy
            if b.needs:
                ok = ok and bool(self._sketch(b.needs))
            b.setEnabled(ok)
        self.stop.setEnabled(busy)
        self.xtherion.setEnabled(bool(self.trip and shutil.which('xtherion') and self.trip.exists(self.trip.plan_file)))

    # --- running ------------------------------------------------------------

    def run(self, commands):
        if not commands or self.current:
            return
        self.queue = list(commands)
        self._next()

    def _next(self):
        self.current = self.queue.pop(0)
        line = self.current.line(self.python_edit.text() or sys.executable)
        self._say(f"\n$ {shlex.join(line)}")
        self.log.appendPlainText('')                   # the output starts on a line of its own
        self.state.setText(f"Running: {self.current.label}")
        self.output = ''
        self.proc.setWorkingDirectory(self.project.root)
        self.proc.start(line[0], line[1:])
        self._enable()

    def _output(self):
        text = bytes(self.proc.readAllStandardOutput()).decode('utf-8', errors='replace')
        self.output += text
        self.log.moveCursor(QtGui.QTextCursor.MoveOperation.End)
        self.log.insertPlainText(text)
        self.log.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    def _finished(self, code, _status=None):
        done, rest = self.current, self.queue
        self.current, self.queue = None, []
        ok = code == 0
        self.state.setText(f"{done.label}: {'done' if ok else f'failed ({code})'}")
        self._say(f"[{done.label}: {'done' if ok else f'failed, exit {code}'}]")
        self._show_files()
        self._enable()
        if ok and rest:
            self.queue = rest
            self._next()
        elif not ok and trip.NEEDS_FORCE in self.output and '--force' not in done.args:
            ask = QtWidgets.QMessageBox.question(
                self, 'Replace the drawing?',
                f"{done.args[done.args.index('-o') + 1]} is not SexyTopo's export: it has drawing in it, "
                "maybe edited by hand. Replace it (--force)? Its hand edits are lost.", Yes | No, No)
            if ask == Yes:
                self.run([trip.Command(done.label, done.args + ['--force'])] + rest)
        elif not ok and rest:
            self._say(f"[not run: {', '.join(c.label for c in rest)}]")

    def _error(self, error):
        if error == QtCore.QProcess.ProcessError.FailedToStart:
            self._say(f"[could not start {self.proc.program()}]")
            self.current, self.queue = None, []
            self.state.setText('')
            self._enable()

    def _stop(self):
        self.queue = []
        self.proc.kill()

    def _say(self, text):
        self.log.appendPlainText(text)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    app = QtWidgets.QApplication(sys.argv[:1])
    w = Window(os.path.abspath(args[0]) if args else None)
    w.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
