# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""A trip's files and the commands of "A new trip" (README.md) on them,
for the GUI (gui.py) to run in the cave's folder. No Qt here.

    p = trip.load_project(cave)
    t = trip.Trip(p, "GoSouth")
    trip.commands(t, {"plan": ["plan", "roofs"]}, t.default_drawing("plan"), None,
                  trip.Options(), trip.Options())
"""
import dataclasses
import os
import sys

from . import project as _project
from . import survey as _survey

# The order a drawing's steps always run in (README.md, "Converting a drawing")
STEPS = {'plan': ('plan', 'roofs', 'details', 'smooth'),
         'extended': ('extended', 'roofs', 'smooth')}
# The window's tabs, in the order they run: (key, title, [(part, label)])
SECTIONS = [
    ('check', 'Check', [('plan', 'Plan sketches'), ('extended', 'Elevation sketches')]),
    ('plan', 'Plan', [(s, s) for s in STEPS['plan']]),
    ('extended', 'Elevation', [(s, s) for s in STEPS['extended']]),
    ('cave', 'Cave', [('database', "Therion's database"), ('place', 'Place the plan'),
                      ('sections', 'Cross sections (report)'), ('sections_write', 'Cross sections (--write)')]),
    ('checks', 'Checks', [('review', 'review check'), ('th2lint', 'th2lint'), ('fillcheck', 'fillcheck --build')]),
]
TITLES = {key: title for key, title, _ in SECTIONS}
VIEWERS = {'xTherion': 'xtherion', 'Therion Studio': 'TherionStudio'}     # programs to view a th2 with
LAYOUT_CONFIG = 'tools/layout.thcfg'
LAYOUT_LOG = 'output/therion-layout.log'
NEEDS_FORCE = '--force to replace it'      # in what plan and extended print when a drawing is in the way


def load_project(cave):
    """The cave's tools/project.toml, its paths relative to `cave`."""
    return _project.load(os.path.join(cave, 'tools', 'project.toml'), cave)


def python_for(cave):
    """The Python to run the scripts with: the cave's .venv, else this one."""
    for rel in (('.venv', 'bin', 'python'), ('.venv', 'Scripts', 'python.exe')):
        p = os.path.join(cave, *rel)
        if os.path.exists(p):
            return p
    return sys.executable


@dataclasses.dataclass
class Options:
    """What plan and extended are told besides the sketch."""
    author: tuple = None        # (date, name), e.g. ("2026.04.25", "Andrew Atkinson")
    copyright: tuple = None     # (year, holder)
    floor: str = None           # plan only: the extended sketch, for floor steps (--floor)
    force: bool = False         # replace a drawing that is not SexyTopo's export


@dataclasses.dataclass
class Command:
    """A command line run in the cave's folder: `module` run by the
    scripts' Python with `args`, or `program` (e.g. therion) with them."""
    label: str
    args: list
    program: str = None
    module: str = 'tools.sketch2therion'

    def line(self, python):
        return [self.program, *self.args] if self.program else [python, '-m', self.module, *self.args]


class Trip:
    """A survey in the cave's folder; paths relative to the cave."""

    def __init__(self, project, survey):
        self.project = project
        self.survey = survey
        self.th = project.survey_file(survey)
        th = project.path(self.th)
        self.inputs = [self._rel(f) for f in _survey.inputs(th)] if os.path.exists(th) else []

    def _rel(self, path):
        return os.path.relpath(path, self.project.root)

    def drawings(self, view):
        """The .th2 files the .th inputs for `view` ('plan', 'extended'),
        and any with no scraps yet."""
        return [f for f in self.inputs
                if view in _survey.projections(self.project.path(f)) or not _survey.projections(self.project.path(f))]

    def default_drawing(self, view):
        usual = self.project.plan_file(self.survey) if view == 'plan' else self.project.extended_file(self.survey)
        found = self.drawings(view)
        return usual if usual in found else (found[0] if found else None)

    def sketches(self, th2):
        """The .xvi files a drawing links as its backdrops, that exist."""
        folder = os.path.dirname(self.project.path(th2))
        text = open(self.project.path(th2), encoding='utf-8', errors='replace').read()
        found = [os.path.normpath(os.path.join(folder, b)) for b in _survey.backdrops(text)]
        return [self._rel(f) for f in found if f.lower().endswith('.xvi') and os.path.exists(f)]

    def details(self):
        th = self.project.path(self.th)
        return _survey.details(th) if os.path.exists(th) else {'date': None, 'team': [], 'copyright': None}

    def exists(self, rel):
        return bool(rel) and os.path.exists(self.project.path(rel))


def check(trip, sketch, elevation=False):
    return Command(f"check {os.path.basename(sketch)}",
                   ['check', sketch, '--survey', trip.survey] + (['--elevation'] if elevation else []))


def convert(trip, view, step, th2, opts):
    """One step of converting a drawing. The first converts its sketch, the
    first .xvi it links (as every later step reads it); the others redo th2."""
    label = f"{TITLES[view]}: {step}"
    if step != STEPS[view][0]:
        return Command(label, [step, th2])
    sketches = trip.sketches(th2)
    if not sketches:
        raise ValueError(f"{th2} links no .xvi sketch as its backdrop")
    args = [step, sketches[0], '--survey', trip.survey, '-o', th2]
    if opts.author:
        args += ['--author', *opts.author]
    if opts.copyright:
        args += ['--copyright', *opts.copyright]
    if view == 'plan' and opts.floor:
        args += ['--floor', opts.floor]
    if opts.force:
        args.append('--force')
    return Command(label, args)


def database(therion='therion'):
    """Therion's database of the cave (README step 5)."""
    return Command("Therion's database", ['-l', LAYOUT_LOG, LAYOUT_CONFIG], therion)


def place(trip):
    return Command(f"place {trip.survey}", ['place', trip.survey])


def sections(write=False):
    return Command("sections --write" if write else "sections", ['sections'] + (['--write'] if write else []))


def review_check(th2):
    return Command("review check", ['review', 'check', th2])


def th2lint(files):
    return Command("th2lint", list(files), module='tools.sketch2therion.th2lint')


def fillcheck(trip):
    return Command("fillcheck", ['fillcheck', '--build', '--survey', trip.survey])


def commands(trip, chosen, plan, extended, plan_opts, ext_opts, therion='therion'):
    """The commands for the parts ticked in `chosen` ({section: [part]}),
    in the order of SECTIONS, on the plan and extended drawings (th2)."""
    drawing = {'plan': plan, 'extended': extended}
    out = []
    for key, _, parts in SECTIONS:
        for part, _ in parts:
            if part not in chosen.get(key, ()):
                continue
            if key == 'check':
                out += [check(trip, s, part == 'extended') for s in trip.sketches(drawing[part])] if drawing[part] else []
            elif key in STEPS:
                if drawing[key]:
                    out.append(convert(trip, key, part, drawing[key], plan_opts if key == 'plan' else ext_opts))
            elif part == 'database':
                out.append(database(therion))
            elif part == 'place':
                out.append(place(trip))
            elif part in ('sections', 'sections_write'):
                out.append(sections(part == 'sections_write'))
            elif part == 'review':
                out += [review_check(plan)] if plan else []
            elif part == 'th2lint':
                files = [f for f in (plan, extended) if trip.exists(f)]
                out += [th2lint(files)] if files else []
            elif part == 'fillcheck':
                out.append(fillcheck(trip))
    return out
