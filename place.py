# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""File a converted plan drawing into its survey and the cave's plan map.

Run after `plan` has written the drawing to its house-style name
(`<Cave>/X/X.plan.th2`, from tools/project.toml):

    python3 -m tools.sketch2therion place X

It
- removes SexyTopo's empty plan file (`XP.th2`, a scrap with no walls),
  refusing if that file has walls drawn;
- points the survey's `input` at `X.plan.th2`;
- writes `map XMP` listing the drawing's plan scraps, after that input;
- adds `XMP@X` to the cave's plan map (`LongwoodValleySinkMP`).

Each file keeps its line endings. Running it again changes nothing.
"""
import os
import re
import subprocess
import sys

from . import project as _project


class PlaceError(Exception):
    pass


def _read(path):
    raw = open(path, 'rb').read().decode('utf-8')
    nl = '\r\n' if '\r\n' in raw else '\n'
    return raw.replace('\r\n', '\n'), nl


def _write(path, text, nl):
    open(path, 'wb').write(text.replace('\n', nl).encode('utf-8'))


def plan_scraps(th2_text):
    """Names of the plan scraps in a .th2, in file order."""
    return re.findall(r'(?m)^scrap (\S+)[^\n]*-projection plan', th2_text)


def has_walls(th2_text):
    return re.search(r'(?m)^\s*line wall\b', th2_text) is not None


INPUT = re.compile(r'(?m)^(\s*)input\s+"?([^"\s]+)"?[ \t]*$')


def fix_input(th_text, old, new):
    """The survey's input of `old` (or `new`) made `input "new"`; added if missing."""
    for m in INPUT.finditer(th_text):
        if m.group(2) in (old, new):
            return th_text[:m.start()] + f'{m.group(1)}input "{new}"' + th_text[m.end():]
    m = re.search(r'(?m)^\s*survey \S+[^\n]*\n', th_text)
    if not m:
        raise PlaceError('no survey line to add the input after')
    return th_text[:m.end()] + f'\ninput "{new}"\n' + th_text[m.end():]


def set_map(th_text, name, scraps, after):
    """`map name` listing `scraps`: replaced if present, else written after the input of `after`."""
    block = f'map {name}\n' + ''.join(f'  {s}\n' for s in scraps) + 'endmap\n'
    m = re.search(rf'(?ms)^map {re.escape(name)}\b.*?^endmap[ \t]*\n?', th_text)
    if m:
        return th_text[:m.start()] + block + th_text[m.end():]
    for m in INPUT.finditer(th_text):
        if m.group(2) == after:
            end = th_text.index('\n', m.end()) + 1 if '\n' in th_text[m.end():] else len(th_text)
            return th_text[:end] + '\n' + block + th_text[end:]
    raise PlaceError(f'no input of {after} to put map {name} after')


def add_to_map(text, map_name, entry):
    """`entry` added as the last line of `map map_name`, if not already there."""
    m = re.search(rf'(?ms)^[ \t]*map {re.escape(map_name)}\b[^\n]*\n(.*?)^[ \t]*endmap', text)   # maps may be indented in a survey
    if not m:
        raise PlaceError(f'no map {map_name}')
    if re.search(rf'(?m)^\s*{re.escape(entry)}\s*$', m.group(1)):
        return text
    body = m.group(1)
    indent = re.match(r'[ \t]*', body).group(0) if body.strip() else '  '
    return text[:m.end(1)] + f'{indent}{entry}\n' + text[m.end(1):]


def _remove(path, repo):
    if subprocess.run(['git', '-C', repo, 'rm', '-q', '--', os.path.relpath(path, repo)],
                      capture_output=True).returncode != 0:
        os.remove(path)


def place(survey, p=None):
    """File survey's plan drawing; returns a list of what changed."""
    p = p or _project.load()
    th = p.path(p.survey_file(survey))
    plan = p.path(p.plan_file(survey))
    folder = os.path.dirname(th)
    if not os.path.exists(plan):
        raise PlaceError(f'{p.plan_file(survey)} not found: convert the sketch first')
    plan_text, _ = _read(plan)
    scraps = plan_scraps(plan_text)
    if not scraps:
        raise PlaceError(f'{p.plan_file(survey)} has no plan scraps')
    done = []

    old = os.path.join(folder, f'{survey}P.th2')          # SexyTopo's export name
    if os.path.exists(old) and os.path.abspath(old) != os.path.abspath(plan):
        if has_walls(_read(old)[0]):
            raise PlaceError(f'{os.path.relpath(old, p.root)} has walls drawn: not removing it')
        _remove(old, p.root)
        done.append(f'removed {os.path.relpath(old, p.root)} (SexyTopo\'s empty plan)')

    text, nl = _read(th)
    new_name = os.path.basename(plan)
    new = fix_input(text, os.path.basename(old), new_name)
    new = set_map(new, p.survey_plan_map(survey), scraps, new_name)
    if new != text:
        _write(th, new, nl)
        done.append(f'{p.survey_file(survey)}: input "{new_name}", map {p.survey_plan_map(survey)} '
                    f'({", ".join(scraps)})')

    master = p.path(p.cave['plan_map_file'])
    text, nl = _read(master)
    entry = p.qualified(p.survey_plan_map(survey), survey)
    new = add_to_map(text, p.cave['plan_map'], entry)
    if new != text:
        _write(master, new, nl)
        done.append(f'{p.cave["plan_map_file"]}: {entry} in {p.cave["plan_map"]}')
    return done


def main(argv):
    if len(argv) != 1:
        sys.exit('usage: python3 -m tools.sketch2therion place SURVEY')
    try:
        done = place(argv[0])
    except PlaceError as e:
        sys.exit(f'place: {e}')
    print('\n'.join(done) if done else 'nothing to change')
