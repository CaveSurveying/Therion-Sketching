# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""A trip's files and the commands of "A new trip" (README.md) on them,
for the GUI (gui.py) to run in the cave's folder. No Qt here.

    p = trip.load_project(cave)
    t = trip.Trip(p, "GoSouth")
    trip.commands(t, {"plan": ["plan", "roofs"]}, t.default_drawing("plan"), None,
                  trip.Options(), trip.Options())
"""
import collections
import dataclasses
import os
import sys

from . import project as _project
from . import survey as _survey

# The order a drawing's steps always run in (README.md, "Converting a drawing")
STEPS = {'plan': ('plan', 'roofs', 'details', 'smooth'),
         'extended': ('extended', 'roofs', 'smooth')}
# The window's tabs, in the order they run: (key, title, [Part]). Each part
# has a short note (what it does) and a longer one (what it changes or
# prints, and what to do about it), shown by the window's (i).
Part = collections.namedtuple('Part', 'key label short detail')
_CHECK = """Reads each sketch the {what} drawing links (its .xvi files) and the trip's .th, and prints a short report in the log. It changes no files.

For example
    GoSouthP.xvi: plan, 78.74 units/m
      28 stations, 27 legs, 205 splays, 0 cross sections
      lines: brown 96, black 80, gray 47, green 34, blue 1
      NOT IN THE SURVEY (1): 29
      stations to nearest wall line: 0.16 m (median)

The first lines give the sketch's scale, what SexyTopo recorded, and how many strokes of each colour were drawn. The colour decides what a stroke becomes (black rock wall, brown mud, green flowstone and so on, as in sketching-guide.md), so an odd count is worth a look before converting.

NOT IN THE SURVEY lists stations in the sketch with no leg in the .th. They are left out of the drawing. Check the survey name is right, or put the leg back in the .th.

The last line is how far the stations are from the nearest drawn wall. Over 2.5 m it warns that the stations may not line up with the drawing."""
_CONVERT = """Turns the {what} sketch into Therion lines and writes them into the drawing, in {what} scraps and cross sections. Each stroke becomes a wall, mud, flowstone, a step, a boulder and so on by its colour. SexyTopo's labels already in the drawing are kept, and the author, date and copyright come from Credits.

For example
    wrote GoSouth{suffix}.th2: 2 {scraps}, 0 cross sections
    Add to {map} in GoSouth.th
      GoSouthS{suffix}1
      GoSouthS{suffix}2

The drawing is written over freely while it holds only scraps with station and label points, as SexyTopo exports it. If it has any lines, or other points, it has been drawn in, maybe by hand. You are asked before it is replaced, and that drawing is lost.

What it writes is not finished, and breaks the rules in Style.md until smooth has run. Run the steps after it too."""
_SMOOTH = """Refits each wall with fewer, smooth points (about one a metre, as a wall drawn by hand), joins wall pieces that meet, removes doubled or stray pieces and puts line ends on the walls. Sharp corners stay corners. Always the last step.

For example
    GoSouthSP1: 1 walls joined, 4 doubled or stray pieces gone, 0 made borders, 67 wall steps joined or line ends put on wall nodes; wall points 40 -> 29

A line saying an outline still crosses itself gives the place in the drawing. Look there in xTherion. It is often two passages over one another, which need separate scraps.

Run again on a smoothed drawing it still changes it a little (to be fixed)."""
_LINT = """Checks the {what} drawing against the rules in Style.md that can be read from the file. It changes no files.

For example
    GoSouthP.th2:11: [scrap-author-copyright] scrap has no -author or -copyright (scrap GoSouthSP1)
    1 files, 1 findings, 1 new, 0 in baseline, 0 baseline entries fixed

Each finding gives the line in the file, the rule (its [lint: ...] tag in Style.md) and the scrap. Findings already in the cave's baseline (older drawings) are only listed. A new one fails the run, so the later tabs do not run until it is fixed."""
SECTIONS = [
    ('plan', 'Plan', [
        Part('check', 'check sketches', 'Reports what the sketches hold. Changes nothing.', _CHECK.format(what='plan')),
        Part('plan', 'plan', 'Draws the plan from its sketch, over the drawing.',
             _CONVERT.format(what='plan', suffix='P', scraps='plan scraps', map='`map GoSouthMP`')
             + " The scrap list it prints is what Place the plan (Cave tab) adds to the trip's .th."),
        Part('roofs', 'roofs', 'Redraws passage edges no wall was sketched for, from the splays.',
             """Where the sketch has no wall, plan has to guess the edge of the passage, and draws it as an invisible outline. roofs redraws that outline round each leg from the splay ends of the drawing's own sketch, which measured the walls at each station. Sketched walls are left as they are.

For example
    GoSouthP.th2: GoSouthSP2
    GoSouthP.th2: nothing to redo

It names the scraps it redrew. Nothing to redo means every edge was sketched, and the drawing is not written."""),
        Part('details', 'details', 'Turns lines inside the passage into floor steps, and tidies boulders.',
             """Lines inside the passage (brown and grey strokes, or walls left inside) are mostly the edge of a step down. Each over a metre long becomes a floor step, with its ticks on the lower side (the side the water is on, else the side the survey is on). Steps doubling a longer one and short scribbles go. Boulders are straightened into clean shapes, and the bigger ones get edges drawn on them.

For example
    GoSouthSP1: 0 floor steps, 14 boulders"""),
        Part('smooth', 'smooth', 'Refits the walls as smooth curves and tidies line ends.', _SMOOTH),
        Part('review', 'review check', "Checks each outline as Therion will see it. Changes nothing.",
             """Reads each plan scrap's outline as Therion and MetaPost will, and checks it against the hard rules in Style.md. It changes no files.

For example
    GoSouthSP1: 9 lines, valid True, turning 1
    GoSouthSP1: a second wall on one side of the passage for 2.6 m at -11 -489   <- hard rule 2

An outline should be valid with a turning number of 1 or -1. Turning 0 means it crosses itself, which Therion reports as "scrap outline intersects itself". A hard rule line gives the rule's number in Style.md and the place in the drawing's coordinates, to put right in xTherion."""),
        Part('th2lint', 'th2lint', "Checks the drawing against Style.md. Changes nothing.", _LINT.format(what='plan'))]),
    ('extended', 'Elevation', [
        Part('check', 'check sketches', 'Reports what the sketches hold. Changes nothing.',
             _CHECK.format(what='elevation').replace('GoSouthP.xvi: plan', 'GoSouthE.xvi: extended elevation')),
        Part('extended', 'extended', 'Draws the extended elevation from its sketch, over the drawing.',
             _CONVERT.format(what='extended elevation', suffix='Ee', scraps='elevation scraps',
                             map='an extended-elevation map')),
        Part('roofs', 'roofs', 'Redraws roof and floor where none was sketched, from the splays.',
             """Where the sketch has no roof or floor, extended has to guess how far the passage goes up and down, and can reach a line of another passage (rectangles of fill) or close up round the legs (round bites). roofs redraws the fill along each leg from the splays up and down at its two stations. A sketched roof or floor near the splays still wins.

For example
    GoSouthEe.th2: GoSouthSEe1
    GoSouthEe.th2: nothing to redo

It names the scraps it redrew. Nothing to redo means every roof and floor was sketched, and the drawing is not written."""),
        Part('smooth', 'smooth', 'Refits the walls as smooth curves and tidies line ends.',
             _SMOOTH.replace('GoSouthSP1', 'GoSouthSEe1')),
        Part('th2lint', 'th2lint', "Checks the drawing against Style.md. Changes nothing.",
             _LINT.format(what='elevation'))]),
    ('cave', 'Cave', [
        Part('database', "Therion's database", "Has Therion place every station in the cave. Writes output/layout.sql.",
             """Runs Therion on tools/layout.thcfg, which writes the cave's database (output/layout.sql) with every station where it is once the loops are closed. Place, Cross sections and the checks of the whole cave read it. It changes no drawings.

The trip must be tied into the cave's master file first (input and equate), or its stations are not in it. Run it again whenever the survey data change. Therion's log is in output/therion-layout.log."""),
        Part('place', 'Place the plan', "Adds the plan drawing to the trip's .th and the cave's plan map.",
             """Changes the trip's .th so it inputs the plan drawing and has a map of its scraps (map GoSouthMP), and adds that map to the cave's plan map. SexyTopo's own empty plan file is removed, unless the drawing was written over it. A file it would remove that has walls drawn in it is left, and the run fails.

The trip must be tied into the cave. Running it again changes nothing."""),
        Part('sections', 'Cross sections (report)', 'Reports how the cross section lines would move. Changes nothing.',
             """For every plan drawing the master file inputs, works out each cross section line turned to look along the survey and carried across its passage (0.5 m past the wall each side), and each section drawing moved clear of the passages, and lists the changes. It changes no files.

Needs Therion's database, up to date."""),
        Part('sections_write', 'Cross sections (write)', 'Moves the cross section lines in every plan drawing. Asks first.',
             """As the report, but writes the changes into every plan drawing the master file inputs, not only this trip's. You are asked first. A section drawing is moved by its point section, never redrawn."""),
        Part('fillcheck', 'fillcheck', "Builds the cave and checks the legs and splays are inside the passage.",
             """Runs the cave's check build with Therion (check_build in project.toml), lists its errors and any scrap that crosses itself, then checks this trip's legs and splays against the passage as drawn. It changes no drawings. The report is also written to output/check/fillcheck.txt.

For example
    == plan (stations agree within 0.02 m)
      legs outside the fill, both stations inside: 0
      legs out of the fill at a station outside it (passage not drawn yet?): 1
      splay ends more than 0.5 m outside the fill, to check: 2

Every leg should be inside the drawn passage, except at a passage end not drawn yet. A splay end well outside a wall usually means the wall is drawn too far in.""")]),
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
    force: bool = False         # replace a drawing with lines or other points in it


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
    return Command(f"review check {os.path.basename(th2)}", ['review', 'check', th2])


def th2lint(files):
    return Command(f"th2lint {' '.join(os.path.basename(f) for f in files)}", list(files),
                   module='tools.sketch2therion.th2lint')


def fillcheck(trip):
    return Command("fillcheck", ['fillcheck', '--build', '--survey', trip.survey])


def commands(trip, chosen, plan, extended, plan_opts, ext_opts, therion='therion'):
    """The commands for the parts ticked in `chosen` ({section: [part]}),
    in the order of SECTIONS, on the plan and extended drawings (th2)."""
    drawing = {'plan': plan, 'extended': extended}
    out = []
    for key, _, parts in SECTIONS:
        for part in (p.key for p in parts):
            if part not in chosen.get(key, ()):
                continue
            th2 = drawing.get(key)
            if key in STEPS and not th2:
                continue
            if part == 'check':
                out += [check(trip, sk, key == 'extended') for sk in trip.sketches(th2)]
            elif part == 'review':
                out.append(review_check(th2))
            elif part == 'th2lint':
                out += [th2lint([th2])] if trip.exists(th2) else []
            elif key in STEPS:
                out.append(convert(trip, key, part, th2, plan_opts if key == 'plan' else ext_opts))
            elif part == 'database':
                out.append(database(therion))
            elif part == 'place':
                out.append(place(trip))
            elif part in ('sections', 'sections_write'):
                out.append(sections(part == 'sections_write'))
            elif part == 'fillcheck':
                out.append(fillcheck(trip))
    return out
