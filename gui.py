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


def row(*widgets):
    """Widgets side by side; a number is a stretch."""
    w = QtWidgets.QWidget()
    h = QtWidgets.QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    for x in widgets:
        h.addWidget(x) if isinstance(x, QtWidgets.QWidget) else h.addStretch(x)
    return w


class Window(QtWidgets.QMainWindow):
    def __init__(self, cave=None, settings=None):
        super().__init__()
        self.setWindowTitle('Therion Sketching')
        self.settings = settings or QtCore.QSettings('CaveSurveying', 'Therion-Sketching')
        self.project = self.trip = None
        self.th_copyright = None
        self.queue, self.current, self.output = [], None, ''
        self.proc = QtCore.QProcess(self)
        self.proc.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.MergedChannels)
        env = QtCore.QProcessEnvironment.systemEnvironment()
        env.insert('PYTHONUNBUFFERED', '1')            # output as it comes
        self.proc.setProcessEnvironment(env)
        self.proc.readyReadStandardOutput.connect(self._output)
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(self._error)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        top = QtWidgets.QVBoxLayout(central)
        top.addWidget(self._header())
        self.tabs = QtWidgets.QTabWidget()
        self.section_ticks, self.part_ticks = {}, {}
        for key, title, parts in trip.SECTIONS:
            self._section_tab(key, title, parts)
        environment = self._environment_tab()          # before Author: it holds the local defaults
        self.tabs.addTab(self._author_tab(), 'Author')
        self.tabs.addTab(environment, 'Environment')
        top.addWidget(self.tabs)
        self.run_button = QtWidgets.QPushButton('Run')
        self.run_button.setToolTip('Run the ticked parts of every ticked tab, in order')
        self.run_button.clicked.connect(self.run_ticked)
        self.stop = QtWidgets.QPushButton('Stop')
        self.stop.clicked.connect(self._stop)
        self.state = QtWidgets.QLabel()
        top.addWidget(row(self.run_button, self.stop, self.state, 1))
        self.log = QtWidgets.QPlainTextEdit(readOnly=True)
        self.log.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont))
        self.log.setMaximumBlockCount(20000)
        top.addWidget(self.log, 1)
        self.resize(900, 900)

        cave = cave or (os.getcwd() if is_cave(os.getcwd()) else self.settings.value('cave', ''))
        self.cave_edit.setText(cave)
        self._load_cave()

    # --- always shown: the cave, the survey and its drawings ------------------

    def _header(self):
        box = QtWidgets.QGroupBox()
        form = QtWidgets.QFormLayout(box)
        self.cave_edit = QtWidgets.QLineEdit()
        self.cave_edit.editingFinished.connect(self._load_cave)
        form.addRow('Cave', self._with_browse(self.cave_edit, self._browse_cave))
        self.trip_combo = QtWidgets.QComboBox()
        self.trip_combo.currentTextChanged.connect(self._load_trip)
        form.addRow('Survey', self.trip_combo)
        self.drawing_combo, self.sketch_label = {}, {}
        for view, title in (('plan', 'Plan'), ('extended', 'Elevation')):
            c = QtWidgets.QComboBox()
            c.setToolTip(f"The {title.lower()} drawings the survey's .th inputs")
            c.currentTextChanged.connect(lambda _, v=view: self._drawing_changed(v))
            b = QtWidgets.QPushButton('View')
            b.setToolTip('Open it in the viewer (Environment). Therion Studio opens its last session, not the file')
            b.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Fixed)
            b.clicked.connect(lambda _=False, v=view: self._view(v))
            self.drawing_combo[view] = c
            form.addRow(title, row(c, b))
            self.sketch_label[view] = QtWidgets.QLabel()
            self.sketch_label[view].setWordWrap(True)
            form.addRow('', self.sketch_label[view])
        return box

    def _with_browse(self, edit, browse):
        b = QtWidgets.QPushButton('Browse…')
        b.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Fixed)
        b.clicked.connect(browse)
        return row(edit, b)

    def _browse_cave(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "The cave's repository", self.cave_edit.text())
        if d:
            self.cave_edit.setText(d)
            self._load_cave()

    def drawing(self, view):
        return self.drawing_combo[view].currentText() or None

    def _drawing_changed(self, view):
        th2 = self.drawing(view)
        sketches = self.trip.sketches(th2) if self.trip and th2 else []
        self.sketch_label[view].setText(('Sketches: ' + ', '.join(os.path.basename(s) for s in sketches))
                                        if sketches else ('No .xvi linked as a backdrop' if th2 else ''))
        if th2:
            self._remember(f'drawing_{view}', th2)

    # --- the tabs that run ------------------------------------------------------

    def _section_tab(self, key, title, parts):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        for part, label in parts:
            t = QtWidgets.QCheckBox(label)
            t.toggled.connect(lambda on, k=f'tick/{key}/{part}': self._remember(k, on))
            self.part_ticks[(key, part)] = t
            lay.addWidget(t)
        if key == 'plan':
            self.floor_check = QtWidgets.QCheckBox('plan: floor steps from the elevation sketch (--floor)')
            lay.addWidget(self.floor_check)
        lay.addStretch(1)
        i = self.tabs.addTab(page, title)
        tick = QtWidgets.QCheckBox()
        tick.setToolTip(f'Run the ticked parts of {title}')
        tick.toggled.connect(lambda on, k=f'tick/{key}': self._remember(k, on))
        self.tabs.tabBar().setTabButton(i, QtWidgets.QTabBar.ButtonPosition.LeftSide, tick)
        self.section_ticks[key] = tick

    def chosen(self):
        """{section: [part]}: the parts ticked, on the tabs ticked."""
        return {key: [p for (k, p), t in self.part_ticks.items() if k == key and t.isChecked()]
                for key, tick in self.section_ticks.items() if tick.isChecked()}

    # --- author and copyright ---------------------------------------------------

    def _author_tab(self):
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)
        self.author_name = QtWidgets.QComboBox()
        self.author_name.setEditable(True)
        self.author_name.setToolTip("Someone in the .th's team, the local default (Environment), or type a name")
        self.author_date = QtWidgets.QLineEdit()
        self.author_date.setToolTip("YYYY.MM.DD: the .th's date, or type one")
        self.author_date.editingFinished.connect(self._copyright_labels)
        form.addRow('Author', self.author_name)
        form.addRow('Date', self.author_date)
        self.copy_choice = {}
        group = QtWidgets.QButtonGroup(page)
        for k in ('local', 'th', 'none'):
            b = QtWidgets.QRadioButton()
            group.addButton(b)
            b.clicked.connect(lambda _=False, k=k: self._remember('copyright_from', k))     # the user's choice only
            self.copy_choice[k] = b
            form.addRow('Copyright' if k == 'local' else '', b)
        self.copy_choice['none'].setText('None')
        return page

    def _fill_author(self):
        d = self.trip.details() if self.trip else {'date': None, 'team': [], 'copyright': None}
        self.author_name.clear()
        for name, roles in d['team']:
            self.author_name.addItem(f"{name} ({roles}, in the .th)" if roles else f"{name} (in the .th)", name)
        local = self.local_author.text().strip()
        if local and local not in [n for n, _ in d['team']]:
            self.author_name.addItem(f"{local} (local default)", local)
        notes = [i for i, (_, roles) in enumerate(d['team']) if 'notes' in roles.split()]
        self.author_name.setCurrentIndex(notes[0] if notes else (0 if self.author_name.count() else -1))
        self.author_date.setText(d['date'] or datetime.date.today().strftime('%Y.%m.%d'))
        self.th_copyright = d['copyright']
        self._copyright_labels()

    def _year(self):
        return (self.author_date.text().strip() or str(datetime.date.today().year))[:4]

    def _copyright_labels(self):
        holder = self.local_copyright.text().strip()
        local, th = self.copy_choice['local'], self.copy_choice['th']
        local.setText(f'Local default: {self._year()} "{holder}"' if holder else 'Local default: none set (Environment)')
        local.setEnabled(bool(holder))
        c = self.th_copyright
        th.setText(f'In the .th: {c[0]} "{c[1]}"' if c else 'In the .th: none there')
        th.setEnabled(bool(c))
        want = self.copy_choice.get(self.settings.value(self._key('copyright_from'), ''))
        (want if want and want.isEnabled() else th if c else local if holder else self.copy_choice['none']).setChecked(True)

    def author(self):
        """(date, name) for --author, or None."""
        i = self.author_name.currentIndex()
        typed = self.author_name.currentText().strip()
        name = self.author_name.itemData(i) if i >= 0 and typed == self.author_name.itemText(i) else typed
        date = self.author_date.text().strip()
        return (date, name) if date and name else None

    def copyright(self):
        """(year, holder) for --copyright, or None."""
        if self.copy_choice['th'].isChecked():
            return self.th_copyright
        holder = self.local_copyright.text().strip()
        if self.copy_choice['local'].isChecked() and holder:
            return (self._year(), holder)
        return None

    def options(self, view):
        floor = None
        if view == 'plan' and self.floor_check.isChecked() and self.drawing('extended'):
            sk = self.trip.sketches(self.drawing('extended'))
            floor = sk[0] if sk else None
        return trip.Options(self.author(), self.copyright(), floor)

    # --- the environment ----------------------------------------------------------

    def _environment_tab(self):
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)
        self.python_edit = self._setting_edit('python', 'The Python that runs the scripts (needs requirements.txt); '
                                              'kept for each cave', per_cave=True)
        form.addRow('Python (scripts)', self._with_browse(self.python_edit, lambda: self._browse(self.python_edit)))
        self.therion_edit = self._setting_edit('therion', 'therion, or a local build', 'therion')
        form.addRow('Therion (compiling)', self._with_browse(self.therion_edit, lambda: self._browse(self.therion_edit)))
        self.viewer_choice, self.viewer_edit = {}, {}
        group = QtWidgets.QButtonGroup(page)
        for name, program in trip.VIEWERS.items():
            b = QtWidgets.QRadioButton(name)
            group.addButton(b)
            b.toggled.connect(lambda on, n=name: on and self.settings.setValue('viewer', n))
            e = self._setting_edit(f'viewer/{name}', f'Blank for {program}, or a local build')
            e.setPlaceholderText(program)
            self.viewer_choice[name], self.viewer_edit[name] = b, e
            form.addRow('Viewer' if len(self.viewer_choice) == 1 else '',
                        row(b, self._with_browse(e, lambda e=e: self._browse(e))))
        self.viewer_choice.get(self.settings.value('viewer', ''), self.viewer_choice['xTherion']).setChecked(True)
        self.local_author = self._setting_edit('local/author', "Offered as the author besides the .th's team")
        self.local_author.editingFinished.connect(self._fill_author)
        form.addRow('Local default author', self.local_author)
        self.local_copyright = self._setting_edit('local/copyright', 'The holder, e.g. Andrew Atkinson (WCC)')
        self.local_copyright.editingFinished.connect(self._copyright_labels)
        form.addRow('Local default copyright', self.local_copyright)
        return page

    def _setting_edit(self, name, tip, default='', per_cave=False):
        """A line kept in the settings, for each cave or for this computer."""
        e = QtWidgets.QLineEdit()
        e.setToolTip(tip)
        if not per_cave:
            e.setText(self.settings.value(name, default))
        e.editingFinished.connect(lambda: self._remember(name, e.text()) if per_cave
                                  else self.settings.setValue(name, e.text()))
        return e

    def _browse(self, edit):
        f, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Program', edit.text())
        if f:
            edit.setText(f)
            edit.editingFinished.emit()

    def viewer(self):
        name = next(n for n, b in self.viewer_choice.items() if b.isChecked())
        return self.viewer_edit[name].text().strip() or trip.VIEWERS[name]

    def _view(self, view):
        th2 = self.drawing(view)
        if not th2:
            return
        program = self.viewer()
        if not shutil.which(program):
            self._say(f"[{program} not found: choose the viewer in Environment]")
            return
        QtCore.QProcess.startDetached(program, [self.project.path(th2)], self.project.root)

    # --- loading the cave and the survey --------------------------------------------

    def _key(self, name):
        """A setting kept for each cave."""
        return f"caves/{self.cave_edit.text().replace('/', '|')}/{name}"

    def _remember(self, name, value):
        if self.project:
            self.settings.setValue(self._key(name), value)

    def _flag(self, name, default):
        v = self.settings.value(self._key(name), default)
        return v if isinstance(v, bool) else str(v).lower() == 'true'

    def _load_cave(self):
        cave = os.path.abspath(self.cave_edit.text()) if self.cave_edit.text() else ''
        self.project = None
        self.trip_combo.clear()
        if not is_cave(cave):
            self._say(f"{cave or 'No cave'}: not a cave's repository (no tools/project.toml)")
            self._enable()
            return
        try:
            p = trip.load_project(cave)
        except Exception as e:          # a project.toml that can't be read
            self._say(f"{cave}/tools/project.toml: {e}")
            self._enable()
            return
        self.cave_edit.setText(cave)
        self.settings.setValue('cave', cave)
        self.python_edit.setText(self.settings.value(self._key('python'), '') or trip.python_for(cave))
        for (key, part), t in self.part_ticks.items():
            t.setChecked(self._flag(f'tick/{key}/{part}', True))
        for key, t in self.section_ticks.items():
            t.setChecked(self._flag(f'tick/{key}', False))
        last = self.settings.value(self._key('survey'), '')
        self.project = p
        self.trip_combo.addItems(p.surveys())
        if last in p.surveys():
            self.trip_combo.setCurrentText(last)
        self._say(f"{p.cave['title']}: {self.trip_combo.count()} surveys in {p.cave['folder']}")
        self._enable()

    def _load_trip(self, survey):
        self.trip = trip.Trip(self.project, survey) if self.project and survey else None
        if self.trip:
            self._remember('survey', survey)
        for view, c in self.drawing_combo.items():
            last = self.settings.value(self._key(f'drawing_{view}'), '')
            c.blockSignals(True)
            c.clear()
            if self.trip:
                found = self.trip.drawings(view)
                c.addItems(found)
                c.setCurrentText(last if last in found else (self.trip.default_drawing(view) or ''))
            c.blockSignals(False)
            self._drawing_changed(view)
        self._fill_author()
        self._enable()

    def _enable(self):
        if not hasattr(self, 'run_button'):
            return
        busy = self.proc.state() != QtCore.QProcess.ProcessState.NotRunning
        self.run_button.setEnabled(bool(self.trip) and not busy)
        self.stop.setEnabled(busy)

    # --- running ----------------------------------------------------------------------

    def run_ticked(self):
        chosen = self.chosen()
        if not any(chosen.values()):
            self._say('[nothing to run: tick a tab and its parts]')
            return
        if 'sections_write' in chosen.get('cave', ()):
            ask = QtWidgets.QMessageBox.question(
                self, 'Cross sections', 'sections --write changes every plan drawing the master file inputs. Go on?',
                Yes | No)
            if ask != Yes:
                return
        try:
            cmds = trip.commands(self.trip, chosen, self.drawing('plan'), self.drawing('extended'),
                                 self.options('plan'), self.options('extended'), self.therion_edit.text() or 'therion')
        except ValueError as e:
            self._say(f'[{e}]')
            return
        self.run(cmds)

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
