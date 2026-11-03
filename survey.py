# Part of tools/sketch2therion; `fit` is copied from caves-mendip-swildons
# tools/routes/survey.py (commit 198bf46). GPLv3: see LICENSE.
"""Which survey a .th2 file belongs to, where a survey's .th is, the sketch a
drawing links as its backdrop, and fitting a scrap to the survey.

Replaces two helpers the Swildons version took from `sections.py` and
`tools/routes/survey.py`, neither of which is ported. `survey_of` looks
for the `.th` files beside the drawing, as each survey here lives in
its own folder (`<Cave>/X/X.th` inputs its plan, `XP.th2`); `fit` is copied
unchanged.
"""
import glob
import os
import re

INPUT = re.compile(r'^\s*input\s+"?([^"\s]+)"?', re.M)
BACKDROP = re.compile(r'(?m)^##XTHERION## xth_me_image_insert \{[^}]*\} \{[^}]*\} (?:\{([^}]*)\}|"([^"]*)"|(\S+))')
PROJECTION = re.compile(r'(?m)^scrap \S+.*?-projection \[?([a-z]+)(?:\s+(\d+))?')


def backdrops(th2_text):
    """The sketch paths a .th2 links as xTherion backdrops, as written."""
    return [a or b or c for a, b, c in BACKDROP.findall(th2_text)]


def sketch_of(th2):
    """The sketch (.xvi) a drawing links as its backdrop, the first that
    exists, or None: where the drawing's sketch is, wherever it is kept."""
    if not os.path.exists(th2):
        return None
    folder = os.path.dirname(os.path.abspath(th2))
    for rel in backdrops(open(th2, encoding='utf-8', errors='replace').read()):
        f = os.path.join(folder, rel)
        if rel.lower().endswith('.xvi') and os.path.exists(f):
            return f
    return None


def inputs(th):
    """The .th2 files the survey's .th inputs that exist, in order."""
    folder = os.path.dirname(os.path.abspath(th))
    out = []
    for m in INPUT.finditer(open(th, encoding='utf-8', errors='replace').read()):
        f = os.path.join(folder, m.group(1))
        if f.lower().endswith('.th2') and os.path.exists(f) and f not in out:
            out.append(f)
    return out


def projections(th2):
    """The projections of a .th2's scraps: 'plan', 'extended', an angle
    faced as a string (e.g. '315'), 'none'."""
    found = PROJECTION.findall(open(th2, encoding='utf-8', errors='replace').read())
    return {angle if kind == 'elevation' and angle else kind for kind, angle in found}


def drawings(th, projection):
    """The .th2 files the survey's .th inputs with a scrap in `projection`
    ('plan', 'extended', or an angle faced, e.g. 315)."""
    return [f for f in inputs(th) if str(projection) in projections(f)]


TEAM = re.compile(r'(?m)^\s*team\s+"([^"]+)"\s*([^#\n]*)')
DATE = re.compile(r'(?m)^\s*date\s+(\d{4}\.\d{2}\.\d{2})')
COPYRIGHT = re.compile(r'(?m)^\s*copyright\s+(\d{4})\s+"([^"]+)"')


def details(th):
    """What the survey's .th says of who and when: {'date': '2026.04.25' or
    None, 'team': [(name, roles)], 'copyright': (year, holder) or None}."""
    t = open(th, encoding='utf-8', errors='replace').read()
    d, c = DATE.search(t), COPYRIGHT.search(t)
    team = []
    for name, roles in TEAM.findall(t):
        if name.strip() not in [n for n, _ in team]:
            team.append((name.strip(), roles.strip()))
    return {'date': d and d.group(1), 'team': team, 'copyright': c and (c.group(1), c.group(2))}


def survey_sketch(th, projection):
    """The sketch of the survey's drawing in `projection`, read from the
    drawing's backdrop, or None."""
    for f in drawings(th, projection):
        sk = sketch_of(f)
        if sk:
            return sk
    return None


def survey_of(th2, ths=None):
    """The survey a th2 file is input in, from the .th files in its folder
    (or `ths`, as a whole cave's are). An input is relative to its .th."""
    folder = os.path.dirname(os.path.abspath(th2))
    target = os.path.abspath(th2)
    for th in sorted(glob.glob(os.path.join(folder, '*.th'))) if ths is None else ths:
        t = open(th, encoding='utf-8', errors='replace').read()
        for m in INPUT.finditer(t):
            if os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(th)), m.group(1))) != target:
                continue
            found = re.findall(r'^\s*survey (\S+)', t[:m.start()], re.M)
            if found:
                return found[-1]
    return None


def survey_file(survey, near):
    """The .th declaring `survey`, beside the file `near` (a sketch or
    drawing) or one folder up (sketches are often kept in a folder of their own), or None."""
    folder = os.path.dirname(os.path.abspath(near))
    for f in (folder, os.path.dirname(folder)):
        for th in sorted(glob.glob(os.path.join(f, '*.th'))):
            if re.search(rf'(?m)^\s*survey {re.escape(survey)}\b', open(th, encoding='utf-8', errors='replace').read()):
                return th
    return None


def joined_ids(near):
    """The ids that `join` statements name, in the .th files beside the file
    `near` and up to two folders above it (the cave's master)."""
    folder = os.path.dirname(os.path.abspath(near))
    out = set()
    for f in (folder, os.path.dirname(folder), os.path.dirname(os.path.dirname(folder))):
        for th in glob.glob(os.path.join(f, '*.th')):
            for line in re.findall(r'(?m)^\s*join\s+([^#\n]*)', open(th, encoding='utf-8', errors='replace').read()):
                out |= {t.split('@')[0].split(':')[0] for t in line.split() if not t.startswith('-')}
    return out


def fit(pairs):
    """Similarity transform (scale, rotation, shift) from scrap to survey coordinates."""
    n = len(pairs)
    sx = sum(p[0][0] for p in pairs) / n
    sy = sum(p[0][1] for p in pairs) / n
    tx = sum(p[1][0] for p in pairs) / n
    ty = sum(p[1][1] for p in pairs) / n
    a = b = d = 0.0
    for (x, y), (u, v) in pairs:
        x -= sx; y -= sy; u -= tx; v -= ty
        a += x * u + y * v
        b += x * v - y * u
        d += x * x + y * y
    if d == 0:
        return None
    a /= d
    b /= d
    return lambda p: (tx + a * (p[0] - sx) - b * (p[1] - sy), ty + b * (p[0] - sx) + a * (p[1] - sy))
