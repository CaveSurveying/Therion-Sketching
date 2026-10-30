# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""A zip of a survey's plan drawing for review on another computer.

    python3 -m tools.sketch2therion zip X OUT.zip [--extra DIR]

Holds, at their paths in the repository so the drawing's backdrop path
still works when unzipped: the plan drawing, the survey's .th, its
plan sketches (.xvi; not the elevations), and the cave's master .th; plus every file in DIR
(PDFs, pictures, NOTES.md) under review/. Files are stored byte for
byte (line endings unchanged). Fails if the drawing's backdrop sketch
is missing.
"""
import argparse
import glob
import os
import sys
import zipfile

from . import project as _project
from .survey import backdrops


def contents(survey, p=None):
    """[(path in the zip, file on disk)] for a survey's review zip."""
    p = p or _project.load()
    plan = p.plan_file(survey)
    folder = os.path.dirname(plan)
    files = [plan, p.survey_file(survey)]
    # plan sketches only: plans are drawn for now, not elevations
    files += sorted(os.path.relpath(f, p.root) for f in glob.glob(p.path(os.path.join(folder, '**', '*.xvi')),
                                                                  recursive=True) if p.is_plan_sketch(f))
    text = open(p.path(plan), 'rb').read().decode('utf-8', errors='replace')
    for b in backdrops(text):
        target = os.path.normpath(os.path.join(folder, b))
        if not os.path.exists(p.path(target)):
            raise FileNotFoundError(f'{plan}: backdrop {b} not found ({target})')
        if target not in files:
            files.append(target)
    files.append(p.cave['plan_map_file'])
    seen, out = set(), []
    for f in files:
        f = f.replace(os.sep, '/')
        if f not in seen:
            seen.add(f)
            out.append((f, p.path(f)))
    return out


def write(survey, out, extra=None, p=None):
    items = contents(survey, p)
    if extra:
        for f in sorted(os.listdir(extra)):
            if os.path.isfile(os.path.join(extra, f)):
                items.append((f'review/{f}', os.path.join(extra, f)))
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, src in items:
            z.write(src, name)
    return [name for name, _ in items]


def main(argv):
    ap = argparse.ArgumentParser(prog='python3 -m tools.sketch2therion zip', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('survey')
    ap.add_argument('out')
    ap.add_argument('--extra', help='a folder of review files (PDFs, pictures, NOTES.md)')
    a = ap.parse_args(argv)
    for name in write(a.survey, a.out, a.extra):
        print(f'  {name}')
    print(f'wrote {a.out}')
