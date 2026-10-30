# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""Text from SexyTopo's own Therion export, carried into the drawing.

SexyTopo writes a sketch's labels into its exported th2 (`point x y label
-text "..." -scale m`, in the sketch's units) and also draws their letters
into the .xvi as strokes. The converter keeps the labels exactly as
SexyTopo wrote them and leaves the letter strokes out, so they are not
read as walls. Before writing over a th2 it checks that the file is
SexyTopo's export (stations and labels only) or the converter's own
output, so nothing drawn by hand is lost.
"""
import glob
import math
import os
import re

from .survey import backdrops

POINT = re.compile(r'(?m)^point\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\S+).*$')
OWN = '# Converted from '          # the note convert.py writes at the top of its drawings


def contents(path):
    """(lines and areas, [(type, x, y, raw)] points) of a th2 file."""
    text = open(path, encoding='utf-8', errors='replace').read().replace('\r\n', '\n')
    drawn = len(re.findall(r'(?m)^(line|area)\b', text))
    points = [(m.group(3), float(m.group(1)), float(m.group(2)), m.group(0)) for m in POINT.finditer(text)]
    return drawn, points


def is_export(path):
    """True if a th2 is SexyTopo's export: no lines, only stations and labels."""
    drawn, points = contents(path)
    return drawn == 0 and all(t in ('station', 'label') for t, *_ in points)


def is_own(path):
    return OWN in open(path, encoding='utf-8', errors='replace').read()


def export_for(sketch):
    """SexyTopo's th2 export with `sketch` as its backdrop, beside it or one
    folder up, or None."""
    target = os.path.abspath(sketch)
    folder = os.path.dirname(target)
    for f in (folder, os.path.dirname(folder)):
        for th2 in sorted(glob.glob(os.path.join(f, '*.th2'))):
            text = open(th2, encoding='utf-8', errors='replace').read()
            if any(os.path.abspath(os.path.join(f, rel)) == target for rel in backdrops(text)) and is_export(th2):
                return th2
    return None


def labels(th2):
    """[(x, y, text, raw line)] of the labels in a th2, in its units."""
    out = []
    for t, x, y, raw in contents(th2)[1]:
        m = re.search(r'-text\s+"([^"]*)"', raw)
        if t == 'label' and m:
            out.append((x, y, m.group(1), raw))
    return out


def _box(p):
    xs, ys = [q[0] for q in p], [q[1] for q in p]
    return min(xs), min(ys), max(xs), max(ys)


def letter_strokes(lines, found, K):
    """Indices of the sketch strokes ([(colour, points)] in metres) that are
    the letters of the labels `found` (x, y, text, raw in units of K a metre).
    SexyTopo draws a label's letters from its point to the right, hanging
    below it; their height is read from the first letters."""
    boxes = [_box(p) for _, p in lines]
    out = set()
    for x, y, text, _ in found:
        x, y = x / K, y / K
        small = [i for i, (x0, y0, x1, y1) in enumerate(boxes)
                 if max(x1 - x0, y1 - y0) < 1.2 and x0 >= x - 0.1 and y1 <= y + 0.1 and y0 >= y - 1.2]
        first = [i for i in small if boxes[i][0] <= x + 0.6]
        if not first:
            continue
        H = max(y - boxes[i][1] for i in first)
        tol = 0.25 * H
        width = 0.8 * H * max(1, len(text))         # a character is about 0.75 of the height, spaces included
        right = x
        for i in sorted((i for i in small if boxes[i][1] >= y - H - tol and boxes[i][3] <= y + tol),
                        key=lambda i: boxes[i][0]):
            if boxes[i][0] > right + 1.5 * H or boxes[i][2] > x + width:
                break
            out.add(i)
            right = max(right, boxes[i][2])
    return out


def add_points(text, raws):
    """Th2 text with the point lines `raws` added, each to the scrap holding
    the station nearest it."""
    raws = list(raws)
    if not raws:
        return text
    scraps = list(re.finditer(r'(?ms)^scrap \S+[^\n]*\n(.*?)^endscrap', text))
    if not scraps:
        return text
    st = [(k, float(m.group(1)), float(m.group(2))) for k, s in enumerate(scraps)
          for m in re.finditer(r'(?m)^point\s+(-?[\d.]+)\s+(-?[\d.]+)\s+station\b', s.group(1))]
    into = {}
    for raw in raws:
        m = POINT.match(raw.strip())
        x, y = float(m.group(1)), float(m.group(2))
        k = min(st, key=lambda s: math.dist((s[1], s[2]), (x, y)))[0] if st else 0
        into.setdefault(k, []).append(raw.strip())
    for k in sorted(into, reverse=True):
        end = scraps[k].end(1)
        text = text[:end] + ''.join(r + '\n\n' for r in into[k]) + text[end:]
    return text
