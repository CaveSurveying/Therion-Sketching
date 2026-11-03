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
DEFAULTS = 'defaults/'          # settings saved by "Save defaults" (and the default author and copyright)

# The other options' short and full descriptions (the steps' are in trip.SECTIONS)
HELP = {
    'floor': ('floor steps and gradients from the elevation sketch',
              "Gives plan the elevation drawing's first sketch (--floor), for floor steps and gradients. "
              "Ignored where the cave's project.toml draws only what the plan sketch shows."),
    'author': ("who drew it, in each scrap's -author",
               "Offers the trip's team from its .th (the notes person first) and your default author. "
               "Type a name to use another. Written into every scrap the conversion makes."),
    'date': ("the drawing's date, in each scrap's -author",
             "The date line of the trip's .th, or today if it has none. Type YYYY.MM.DD to change it."),
    'copyright': ("each scrap's -copyright",
                  "Your default holder, the copyright line of the trip's .th, a holder typed here, or "
                  "none. The year is the date's."),
    'licence': ("the cave's, from its project.toml",
                "The licence written at the top of every drawing. The converter writes the cave's licence "
                "(drawing.licence in tools/project.toml) for now, so the other choices are not yet open."),
    'defaults': ('kept on this computer for every cave',
                 "The author and copyright holder offered for every trip. Change them with the button, "
                 "so it is clear the default is changing and not just this run."),
    'python': ('runs the scripts, kept for each cave',
               "The Python the scripts run with. It needs the libraries in requirements.txt. The cave's "
               ".venv if it has one, else the Python running this window."),
    'therion': ('compiles the database and the check build',
                "The therion program, or the path to a local build."),
    'viewer': ('opens a drawing with View',
               "xTherion or Therion Studio, each with the path to a local build if wanted (blank uses "
               "the installed one). Therion Studio opens its last session for now, not the drawing."),
}


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


def narrow(widget):
    widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Fixed)
    return widget


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
        self.tabs.addTab(self._credits_tab(), 'Credits')
        self.tabs.addTab(self._environment_tab(), 'Environment')
        top.addWidget(self.tabs)
        self.run_button = narrow(QtWidgets.QPushButton('Run'))
        self.run_button.setToolTip('Run the ticked parts of every ticked tab, in order')
        self.run_button.clicked.connect(self.run_ticked)
        self.stop = narrow(QtWidgets.QPushButton('Stop'))
        self.stop.clicked.connect(self._stop)
        self.state = QtWidgets.QLabel()
        top.addWidget(row(self.run_button, self.stop, self.state, 1))
        self.log = QtWidgets.QPlainTextEdit(readOnly=True)
        self.log.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont))
        self.log.setMaximumBlockCount(20000)
        top.addWidget(self.log, 1)
        save = narrow(QtWidgets.QPushButton('Save defaults'))
        save.setToolTip('Keep the tick boxes, copyright choice and Environment as they are now, for next time')
        save.clicked.connect(self.save_defaults)
        top.addWidget(row(save, 1))
        self.resize(950, 950)
        self._apply_defaults()

        cave = cave or (os.getcwd() if is_cave(os.getcwd()) else self.settings.value('cave', ''))
        self.cave_edit.setText(cave)
        self._load_cave()

    # --- an option: its widget, a short line on what it does and an (i) for more -------

    def _info(self, title, detail):
        b = QtWidgets.QToolButton()
        b.setText('\u24d8')                         # a circled i
        f = b.font()
        f.setPointSizeF(f.pointSizeF() * 1.3)
        b.setFont(f)
        b.setAutoRaise(True)
        b.setToolTip('More about this')
        b.clicked.connect(lambda: QtWidgets.QMessageBox.information(self, title, detail))
        return b

    def _option(self, widget, title, short, detail, wide=False):
        """`wide`: the widget takes the room, else the note and (i) sit just after it."""
        note = QtWidgets.QLabel(short)
        note.setEnabled(False)                       # greyed: a note, not a control
        if wide:
            widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
            return row(widget, note, self._info(title, detail))
        return row(widget, note, self._info(title, detail), 1)

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
            b = narrow(QtWidgets.QPushButton('View'))
            b.setToolTip('Open it in the viewer (Environment)')
            b.clicked.connect(lambda _=False, v=view: self._view(v))
            self.drawing_combo[view] = c
            form.addRow(title, row(c, b))
            self.sketch_label[view] = QtWidgets.QLabel()
            self.sketch_label[view].setWordWrap(True)
            form.addRow('', self.sketch_label[view])
        return box

    def _with_browse(self, edit, browse):
        b = narrow(QtWidgets.QPushButton('Browse…'))
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
        for p in parts:
            t = QtWidgets.QCheckBox(p.label)
            self.part_ticks[(key, p.key)] = t
            lay.addWidget(self._option(t, p.label, p.short, p.detail))
        if key == 'plan':
            self.floor_check = QtWidgets.QCheckBox('--floor')
            lay.addWidget(self._option(self.floor_check, '--floor', *HELP['floor']))
        lay.addStretch(1)
        i = self.tabs.addTab(page, title)
        tick = QtWidgets.QCheckBox()
        tick.setToolTip(f'Run the ticked parts of {title}')
        self.tabs.tabBar().setTabButton(i, QtWidgets.QTabBar.ButtonPosition.LeftSide, tick)
        self.section_ticks[key] = tick

    def chosen(self):
        """{section: [part]}: the parts ticked, on the tabs ticked."""
        return {key: [p for (k, p), t in self.part_ticks.items() if k == key and t.isChecked()]
                for key, tick in self.section_ticks.items() if tick.isChecked()}

    # --- credits: author, copyright and licence ----------------------------------

    def _credits_tab(self):
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)
        self.author_name = QtWidgets.QComboBox()
        self.author_name.setEditable(True)
        self.author_name.setMinimumContentsLength(25)
        self.author_from = QtWidgets.QLabel()          # where the name came from: not part of it
        self.author_name.currentIndexChanged.connect(self._author_from)
        self.author_name.editTextChanged.connect(self._author_from)
        form.addRow('Author', self._option(row(self.author_name, self.author_from), 'Author', *HELP['author']))
        self.author_date = QtWidgets.QLineEdit()
        self.author_date.setMaximumWidth(120)
        self.author_date.editingFinished.connect(self._copyright_labels)
        form.addRow('Date', self._option(self.author_date, 'Date', *HELP['date']))
        self.copy_choice = {}
        group = QtWidgets.QButtonGroup(page)
        for k in ('default', 'th', 'typed', 'none'):
            b = QtWidgets.QRadioButton()
            group.addButton(b)
            self.copy_choice[k] = b
        self.copy_choice['none'].setText('None')
        self.copy_typed = QtWidgets.QLineEdit()
        self.copy_typed.setPlaceholderText('the holder, e.g. A Club')
        self.copy_typed.textEdited.connect(lambda _: self.copy_choice['typed'].setChecked(True))
        self.copy_choice['typed'].setText('Other')
        form.addRow('Copyright', self._option(self.copy_choice['default'], 'Copyright', *HELP['copyright']))
        form.addRow('', self.copy_choice['th'])
        form.addRow('', row(self.copy_choice['typed'], self.copy_typed))
        form.addRow('', self.copy_choice['none'])
        # the licence: the cave's (project.toml) for now, as the converter writes no other
        self.licence_choice = {k: QtWidgets.QRadioButton(t) for k, t in
                               (('default', 'Default'), ('th', 'In the .th'), ('typed', 'Other'))}
        group = QtWidgets.QButtonGroup(page)
        for b in self.licence_choice.values():
            group.addButton(b)
            b.setEnabled(False)
        self.licence_choice['default'].setChecked(True)
        licence_typed = QtWidgets.QLineEdit()
        licence_typed.setEnabled(False)
        form.addRow('Licence', self._option(self.licence_choice['default'], 'Licence', *HELP['licence']))
        form.addRow('', self.licence_choice['th'])
        form.addRow('', row(self.licence_choice['typed'], licence_typed))
        self.defaults_label = QtWidgets.QLabel()
        change = narrow(QtWidgets.QPushButton('Change defaults…'))
        change.clicked.connect(self._change_defaults)
        form.addRow('Defaults', row(self.defaults_label, change, self._info('Defaults', HELP['defaults'][1]), 1))
        self._show_defaults()
        return page

    def default_author(self):
        return self.settings.value(DEFAULTS + 'author', '')

    def default_copyright(self):
        return self.settings.value(DEFAULTS + 'copyright', '')

    def _show_defaults(self):
        self.defaults_label.setText(f'author "{self.default_author() or "none"}", '
                                    f'copyright "{self.default_copyright() or "none"}"')

    def _change_defaults(self):
        d = QtWidgets.QDialog(self)
        d.setWindowTitle('Default author and copyright')
        form = QtWidgets.QFormLayout(d)
        form.addRow(QtWidgets.QLabel('Offered for every trip on this computer.'))
        name, holder = QtWidgets.QLineEdit(self.default_author()), QtWidgets.QLineEdit(self.default_copyright())
        form.addRow('Author', name)
        form.addRow('Copyright holder', holder)
        ok = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok
                                        | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        ok.accepted.connect(d.accept)
        ok.rejected.connect(d.reject)
        form.addRow(ok)
        if d.exec():
            self.set_defaults(name.text().strip(), holder.text().strip())

    def set_defaults(self, author, copyright):
        self.settings.setValue(DEFAULTS + 'author', author)
        self.settings.setValue(DEFAULTS + 'copyright', copyright)
        self._show_defaults()
        self._fill_author()

    def _fill_author(self):
        d = self.trip.details() if self.trip else {'date': None, 'team': [], 'copyright': None}
        self.author_name.clear()
        for name, roles in d['team']:
            self.author_name.addItem(name, f"{roles}, in the .th" if roles else "in the .th")
        mine = self.default_author()
        if mine and mine not in [n for n, _ in d['team']]:
            self.author_name.addItem(mine, 'default')
        notes = [i for i, (_, roles) in enumerate(d['team']) if 'notes' in roles.split()]
        self.author_name.setCurrentIndex(notes[0] if notes else (0 if self.author_name.count() else -1))
        self.author_date.setText(d['date'] or datetime.date.today().strftime('%Y.%m.%d'))
        self.th_copyright = d['copyright']
        self._copyright_labels()
        licence = self.project.drawing['licence'] if self.project else ''
        self.licence_choice['default'].setText(f'Default: {licence}' if licence else 'Default')

    def _year(self):
        return (self.author_date.text().strip() or str(datetime.date.today().year))[:4]

    def _copyright_labels(self):
        holder, c = self.default_copyright(), self.th_copyright
        default, th = self.copy_choice['default'], self.copy_choice['th']
        default.setText(f'Default: {self._year()} "{holder}"' if holder else 'Default: none set')
        default.setEnabled(bool(holder))
        th.setText(f'In the .th: {c[0]} "{c[1]}"' if c else 'In the .th: none there')
        th.setEnabled(bool(c))
        want = self.copy_choice.get(self.settings.value(DEFAULTS + 'copyright_from', ''))
        if not (want and want.isEnabled()):
            want = th if c else default if holder else self.copy_choice['none']
        want.setChecked(True)

    def _author_from(self, *_):
        i = self.author_name.findText(self.author_name.currentText())
        self.author_from.setText(f'({self.author_name.itemData(i)})' if i >= 0 else '(typed)')

    def author(self):
        """(date, name) for --author, or None."""
        name = self.author_name.currentText().strip()
        date = self.author_date.text().strip()
        return (date, name) if date and name else None

    def copyright(self):
        """(year, holder) for --copyright, or None."""
        holder = {'default': self.default_copyright(), 'typed': self.copy_typed.text().strip()}
        if self.copy_choice['th'].isChecked():
            return self.th_copyright
        for k, h in holder.items():
            if self.copy_choice[k].isChecked() and h:
                return (self._year(), h)
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
        self.python_edit = QtWidgets.QLineEdit()
        form.addRow('Python', self._option(self._with_browse(self.python_edit, lambda: self._browse(self.python_edit)),
                                           'Python', *HELP['python'], wide=True))
        self.therion_edit = QtWidgets.QLineEdit()
        self.therion_edit.setPlaceholderText('therion')
        form.addRow('Therion', self._option(self._with_browse(self.therion_edit, lambda: self._browse(self.therion_edit)),
                                            'Therion', *HELP['therion'], wide=True))
        self.viewer_choice, self.viewer_edit = {}, {}
        group = QtWidgets.QButtonGroup(page)
        for name, program in trip.VIEWERS.items():
            b = QtWidgets.QRadioButton(name)
            group.addButton(b)
            e = QtWidgets.QLineEdit()
            e.setPlaceholderText(program)
            self.viewer_choice[name], self.viewer_edit[name] = b, e
            line = row(b, self._with_browse(e, lambda e=e: self._browse(e)))
            first = len(self.viewer_choice) == 1
            form.addRow('Viewer' if first else '', self._option(line, 'Viewer', *HELP['viewer'], wide=True) if first else line)
        return page

    def _browse(self, edit):
        f, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Program', edit.text())
        if f:
            edit.setText(f)

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

    # --- defaults -------------------------------------------------------------------

    def _flag(self, name, default):
        v = self.settings.value(name, default)
        return v if isinstance(v, bool) else str(v).lower() == 'true'

    def _apply_defaults(self):
        """The tick boxes, copyright choice and environment as last saved."""
        for (key, part), t in self.part_ticks.items():
            t.setChecked(self._flag(f'{DEFAULTS}tick/{key}/{part}', True))
        for key, t in self.section_ticks.items():
            t.setChecked(self._flag(f'{DEFAULTS}tick/{key}', True))
        self.floor_check.setChecked(self._flag(DEFAULTS + 'floor', False))
        self.therion_edit.setText(self.settings.value(DEFAULTS + 'therion', ''))
        for name, e in self.viewer_edit.items():
            e.setText(self.settings.value(f'{DEFAULTS}viewer/{name}', ''))
        self.viewer_choice.get(self.settings.value(DEFAULTS + 'viewer', ''), self.viewer_choice['xTherion']).setChecked(True)

    def save_defaults(self):
        s, d = self.settings, DEFAULTS
        for (key, part), t in self.part_ticks.items():
            s.setValue(f'{d}tick/{key}/{part}', t.isChecked())
        for key, t in self.section_ticks.items():
            s.setValue(f'{d}tick/{key}', t.isChecked())
        s.setValue(d + 'floor', self.floor_check.isChecked())
        s.setValue(d + 'copyright_from', next(k for k, b in self.copy_choice.items() if b.isChecked()))
        s.setValue(d + 'therion', self.therion_edit.text().strip())
        s.setValue(d + 'viewer', next(n for n, b in self.viewer_choice.items() if b.isChecked()))
        for name, e in self.viewer_edit.items():
            s.setValue(f'{d}viewer/{name}', e.text().strip())
        self._remember('python', self.python_edit.text().strip())
        self._say('[defaults saved]')

    # --- loading the cave and the survey --------------------------------------------

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
            p = trip.load_project(cave)
        except Exception as e:          # a project.toml that can't be read
            self._say(f"{cave}/tools/project.toml: {e}")
            self._enable()
            return
        self.cave_edit.setText(cave)
        self.settings.setValue('cave', cave)
        self.python_edit.setText(self.settings.value(self._key('python'), '') or trip.python_for(cave))
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
