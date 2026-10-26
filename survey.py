# Part of tools/sketch2therion; `fit` is copied from caves-mendip-swildons
# tools/routes/survey.py (commit 198bf46). GPLv3: see LICENSE.
"""Which survey a .th2 file belongs to, where a survey's .th is, and fitting
a scrap to the survey.

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


def survey_of(th2):
    """The survey a th2 file is input in, from the .th files in its folder."""
    folder = os.path.dirname(os.path.abspath(th2))
    target = os.path.abspath(th2)
    for th in sorted(glob.glob(os.path.join(folder, '*.th'))):
        t = open(th, encoding='utf-8', errors='replace').read()
        for m in INPUT.finditer(t):
            if os.path.abspath(os.path.join(folder, m.group(1))) != target:
                continue
            found = re.findall(r'^\s*survey (\S+)', t[:m.start()], re.M)
            if found:
                return found[-1]
    return None


def survey_file(survey, near):
    """The .th declaring `survey`, beside the file `near` (a sketch or
    drawing) or one folder up (sketches are often in Notes/), or None."""
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
