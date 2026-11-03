# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""A trip's files and the commands of "A new trip" (README.md) on them,
for the GUI (gui.py) to run in the cave's folder. No Qt here.

    p = trip.load_project(cave)
    t = trip.Trip(p, "GoSouth")
    trip.convert(t, "plan", "plan", t.plan_sketches()[0], trip.Options())
"""
import dataclasses
import glob
import os
import re
import sys

from . import project as _project
from .survey import sketch_of

# The order a drawing's steps always run in (README.md, "Converting a drawing")
STEPS = {'plan': ('plan', 'roofs', 'details', 'smooth'),
         'extended': ('extended', 'roofs', 'smooth')}
LAYOUT_CONFIG = 'tools/layout.thcfg'
LAYOUT_LOG = 'output/therion-layout.log'
NEEDS_FORCE = '--force to replace it'      # in what plan and extended print when a drawing is in the way
EXTENDED_SKETCH = re.compile(r'(Ee|\.ee)\.xvi$')     # the usual names (Style.md, naming)


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
        self.folder = os.path.dirname(self.th)
        self.plan_file = project.plan_file(survey)
        self.extended_file = project.extended_file(survey)

    def sketches(self):
        """The trip's .xvi sketches, anywhere in its folder."""
        found = glob.glob(self.project.path(os.path.join(self.folder, '**', '*.xvi')), recursive=True)
        return sorted(os.path.relpath(f, self.project.root) for f in found)

    def plan_sketches(self):
        """The plan sketches, the plan drawing's own (its backdrop) first."""
        return self._own_first('plan', [f for f in self.sketches() if self.project.is_plan_sketch(f)])

    def elevation_sketches(self):
        """The other sketches: the extended drawing's own first, then the
        usual extended sketch's name."""
        rest = sorted((f for f in self.sketches() if not self.project.is_plan_sketch(f)),
                      key=lambda f: EXTENDED_SKETCH.search(f) is None)
        return self._own_first('extended', rest)

    def _own_first(self, view, sketches):
        own = sketch_of(self.project.path(self.output(view)))
        own = own and os.path.relpath(own, self.project.root)
        return sorted(sketches, key=lambda f: f != own)

    def output(self, view):
        return self.plan_file if view == 'plan' else self.extended_file

    def exists(self, rel):
        return os.path.exists(self.project.path(rel))


def check(trip, sketch, elevation=False):
    return Command(f"check {os.path.basename(sketch)}",
                   ['check', sketch, '--survey', trip.survey] + (['--elevation'] if elevation else []))


def convert(trip, view, step, sketch, opts):
    """One step of converting the trip's plan or extended sketch."""
    out = trip.output(view)
    if step != STEPS[view][0]:
        return Command(f"{view}: {step}", [step, out])
    args = [step, sketch, '--survey', trip.survey, '-o', out]
    if opts.author:
        args += ['--author', *opts.author]
    if opts.copyright:
        args += ['--copyright', *opts.copyright]
    if view == 'plan' and opts.floor:
        args += ['--floor', opts.floor]
    if opts.force:
        args.append('--force')
    return Command(f"{view}: {step}", args)


def convert_all(trip, view, sketch, opts):
    return [convert(trip, view, s, sketch, opts) for s in STEPS[view]]


def database():
    """Therion's database of the cave (README step 5)."""
    return Command("Therion's database", ['-l', LAYOUT_LOG, LAYOUT_CONFIG], 'therion')


def place(trip):
    return Command(f"place {trip.survey}", ['place', trip.survey])


def sections(write=False):
    return Command("sections --write" if write else "sections", ['sections'] + (['--write'] if write else []))


def review_check(trip):
    return Command("review check", ['review', 'check', trip.plan_file])


def th2lint(trip):
    files = [f for f in (trip.plan_file, trip.extended_file) if trip.exists(f)]
    return Command("th2lint", files, module='tools.sketch2therion.th2lint')


def fillcheck(trip):
    return Command("fillcheck", ['fillcheck', '--build', '--survey', trip.survey])
