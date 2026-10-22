# Ported from caves-mendip-swildons, tools/sketch2therion (commit 198bf46,
# https://github.com/paperclipmonkey/caves-mendip-swildons). GPLv3: see tools/LICENSE.
"""Reviewing a drawing against the surveyor's sketch, with someone who
knows the cave.

    python3 -m tools.sketch2therion review build
        build the plan with station names (output/review-plan.pdf); copy it
        aside before editing to have a "before"
    python3 -m tools.sketch2therion review show OUT.png 90 91 ... --survey NorthRift
        [--title T] [--before OLD.pdf] [--ring 92 93]
        a split screen: the original sketch (PocketTopo or XVI, with its
        colours, legs and station names) beside the drawing at those
        stations; with --before, sketch | before | after
    python3 -m tools.sketch2therion review gaps FILE.th2 SCRAP [...]
        where Therion closes the outline with a straight line, and how much
        of each the sketch draws a wall along: walls lost in conversion
    python3 -m tools.sketch2therion review check FILE.th2 [SCRAP ...]
        the outlines as Therion joins them: valid (no 3D failure) and
        MetaPost's turning number (0 means "scrap outline intersects
        itself")

See the review section of .claude/skills/therion-drawing/SKILL.md.
"""
import glob
import io
import math
import os
import re
import subprocess
import sys

from shapely.geometry import LineString, Point

from .. import project as _project
from . import pockettopo, register, xvi
from .survey import survey_of
from .tidy import bezier_points, parse_scrap, reverse_segments, therion_rings

K = 39.37
PROJECT = _project.load()
PLAN = PROJECT.build['review_plan']
LAYOUT = PROJECT.build['layout_plan']
COLOURS = {'BLACK': '#111111', 'GRAY': '#888888', 'BROWN': '#8b4513', 'BLUE': '#1f5fff',
           'RED': '#dd0000', 'GREEN': '#1a9a1a', 'ORANGE': '#ff9900'}


# -- sketches --------------------------------------------------------------------------

_SKETCHES = {}


def _sketch(path, view='plan'):
    if (path, view) not in _SKETCHES:
        if path.lower().endswith('.xvi'):
            _SKETCHES[(path, view)] = xvi.read(path)
        else:
            _SKETCHES[(path, view)] = pockettopo.sketch(path, view)
    return _SKETCHES[(path, view)]


def sketches_for(stations, view='plan', survey=None):
    """The sketch files that have these stations, most of them first.

    Station names restart in each survey here, so with `survey` only that
    survey's folder is searched."""
    where = PROJECT.cave['folder'] + (f'/{survey}' if survey else '')
    xvis = [f for f in glob.glob(f'{where}/**/*.xvi', recursive=True)
            if PROJECT.is_plan_sketch(f) == (view == 'plan')]
    files = sorted(glob.glob(f'{where}/**/*.top', recursive=True) + xvis)
    hits = []
    for f in files:
        try:
            pos = _sketch(f, view).positions()
        except Exception:
            continue
        n = sum(s in pos for s in stations)
        if n:
            hits.append((n, f))
    return [f for n, f in sorted(hits, reverse=True)]


def _similarity(src, dst):
    import numpy as np
    A = np.array(src, float); B = np.array(dst, float)
    ma, mb = A.mean(0), B.mean(0); a, b = A - ma, B - mb
    U, S, Vt = np.linalg.svd(a.T @ b); R = (U @ Vt).T
    if np.linalg.det(R) < 0:
        Vt[-1] *= -1; R = (U @ Vt).T
    s = S.sum() / (a ** 2).sum()
    return lambda p: tuple(s * R @ (np.array(p, float) - ma) + mb)


def scrap_objects(th2, scrap):
    t = open(th2, encoding='utf-8').read().replace('\r\n', '\n')
    m = re.search(r'^scrap %s\b[^\n]*\n(.*?)^endscrap' % re.escape(scrap), t, re.S | re.M)
    return parse_scrap(m.group(1))


def stations_of(objs):
    st = {}
    for o in objs:
        m = re.match(r'point (\S+) (\S+) station .*-name (\S+)', o.head) if o.kind == 'point' else None
        if m:
            st[m.group(3).split('@')[0]] = (float(m.group(1)), float(m.group(2)))
    return st


def sketch_to_th2(sketch, objs, view='plan'):
    """A transform from the sketch's metres to the scrap's th2 units, fitted
    on the stations they share."""
    pos = _sketch(sketch, view).positions(); st = stations_of(objs)
    common = [n for n in st if n in pos]
    return _similarity([pos[n] for n in common], [st[n] for n in common])


# -- pictures --------------------------------------------------------------------------

def _turn(p, angle):
    """Rotate a point anticlockwise by `angle` radians about the origin."""
    c, s_ = math.cos(angle), math.sin(angle)
    return (c * p[0] - s_ * p[1], s_ * p[0] + c * p[1])


def page_angle(to_page):
    """The anticlockwise turn from survey to page (as seen, y up)."""
    (x0, y0), (x1, y1) = to_page((0.0, 0.0)), to_page((1.0, 0.0))
    return math.atan2(-(y1 - y0), x1 - x0)


def sketch_panel(stations, view='plan', pad=4, survey=None, angle=0.0):
    import matplotlib; matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from PIL import Image
    files = sketches_for(stations, view, survey)
    main, layers = None, []
    for f in files:
        sk = _sketch(f, view); off = (0.0, 0.0)
        pos = {n: _turn(p, angle) for n, p in sk.positions().items()}
        if main is not None:
            common = [n for n in pos if n in main]
            if not common:
                continue
            off = (main[common[0]][0] - pos[common[0]][0], main[common[0]][1] - pos[common[0]][1])
        P = {n: (p[0] + off[0], p[1] + off[1]) for n, p in pos.items()}
        main = dict(P) if main is None else {**P, **main}
        layers.append((f, sk, P, off))
    xs = [main[s][0] for s in stations if s in main]; ys = [main[s][1] for s in stations if s in main]
    x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
    fig, ax = plt.subplots(figsize=(7, 7 * (y1 - y0) / max(x1 - x0, 1e-6)), dpi=110)
    for f, sk, P, off in layers:
        for col, pts in sk.lines:
            q = [(t[0] + off[0], t[1] + off[1]) for t in (_turn(p, angle) for p in pts)]
            if any(x0 <= x <= x1 and y0 <= y <= y1 for x, y in q):
                ax.plot([p[0] for p in q], [p[1] for p in q], color=COLOURS.get(col, 'm'), lw=1.4)
        for leg in sk.legs():
            a, b = leg[0], leg[1]
            if a in P and b in P:
                ax.plot([P[a][0], P[b][0]], [P[a][1], P[b][1]], color='#dd0000', lw=0.6, ls='--')
    for n, p in main.items():
        if x0 <= p[0] <= x1 and y0 <= p[1] <= y1:
            ax.plot(*p, '+', color='#c00060', ms=7)
            ax.text(p[0] + 0.15, p[1] + 0.15, n, fontsize=8, color='#c00060')
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([])
    ax.set_title('Original sketch (%s): %s' % (view, ', '.join(os.path.basename(f) for f, *_ in layers)), fontsize=8)
    ax.legend([Line2D([], [], color=COLOURS[c]) for c in ('BLACK', 'BROWN', 'GRAY', 'BLUE', 'GREEN', 'ORANGE')]
              + [Line2D([], [], color='#dd0000', ls='--')],
              ['black', 'brown', 'grey', 'blue', 'green', 'orange', 'survey leg'], fontsize=6, loc='lower right', ncol=4)
    buf = io.BytesIO(); fig.savefig(buf, format='png', bbox_inches='tight'); plt.close(fig)
    return Image.open(buf).convert('RGB')


_PDFMAP = {}


def fit_page(pairs):
    """Survey (x east, y north) to PDF page (y down): scale, rotation and
    shift, least squares. Returns a function. The plan may be rotated."""
    import numpy as np
    src = np.array([p for p, _ in pairs], dtype=float); dst = np.array([q for _, q in pairs], dtype=float)
    if len(src) < 2:
        raise ValueError('too few labels found on the PDF to place the drawing')
    A = np.zeros((2 * len(src), 4)); y = np.zeros(2 * len(src))
    A[0::2, 0] = 1; A[0::2, 2] = src[:, 0]; A[0::2, 3] = -src[:, 1]; y[0::2] = dst[:, 0]
    A[1::2, 1] = 1; A[1::2, 2] = -src[:, 1]; A[1::2, 3] = -src[:, 0]; y[1::2] = dst[:, 1]
    tx, ty, p, q = np.linalg.lstsq(A, y, rcond=None)[0]
    return lambda v: (tx + p * v[0] - q * v[1], ty - q * v[0] - p * v[1])


def config_with_inputs(path):
    """A config's text followed by the files it inputs (where its layouts are)."""
    from ..svn2git.deps import parse_refs
    text = open(path, encoding='utf-8').read()
    folder = os.path.dirname(path)
    for ref in parse_refs(text):
        f = os.path.join(folder, ref.target)
        if ref.kind == 'input' and os.path.isfile(f):
            text += '\n' + open(f, encoding='utf-8').read()
    return text


def sheet_scale_rotation(config_text):
    """(scale denominator, rotation in degrees) from a thconfig's layout."""
    sc = re.search(r'^\s*scale\s+1\s+(\d+(?:\.\d+)?)', config_text, re.M)
    rot = re.search(r'^\s*rotate\s+(-?\d+(?:\.\d+)?)', config_text, re.M)
    return (float(sc.group(1)) if sc else 500.0), (float(rot.group(1)) if rot else 0.0)


def calibrate(words, names, scale=500.0, rotate=0.0, tol=6.0):
    """Survey -> page transform from the station names printed on a review plan.

    `words` are (x, y, text) on the page; `names` maps a station name to its
    survey positions (names restart in each survey, so one name can have
    several). With the sheet's scale and rotation, each match of a printed
    name to a station gives a shift; the commonest shift wins, and the
    matches that agree with it are fitted by least squares."""
    from collections import Counter
    k = 72 / 25.4 * 1000 / scale            # PDF points per metre
    best = None
    for sign in (1, -1):
        th = math.radians(sign * rotate)
        c, s_ = math.cos(th), math.sin(th)
        cands = []
        for x, y, t in words:
            for sx, sy in names.get(t, ()):
                X, Y = k * (c * sx - s_ * sy), -k * (s_ * sx + c * sy)
                cands.append(((x - X, y - Y), (sx, sy), (x, y)))
        votes = Counter((round(o[0] / tol), round(o[1] / tol)) for o, _, _ in cands)
        if votes:
            key, n = votes.most_common(1)[0]
            if best is None or n > best[0]:
                best = (n, key, cands)
    if best is None:
        raise ValueError('no station names found on the PDF: was it made with `review build`?')
    _, key, cands = best
    centre = (key[0] * tol, key[1] * tol)
    pairs = [(sv, pg) for o, sv, pg in cands if math.dist(o, centre) <= 1.5 * tol]
    if len(pairs) < 3:
        raise ValueError('too few station names on the PDF agree; was it made with `review build`?')
    return fit_page(pairs)


def pdf_rect(stations, pdf=PLAN, pad=15, survey=None):
    """Where the stations (of `survey`) are on a review plan PDF."""
    import pymupdf
    if pdf not in _PDFMAP:
        lay = register.Layout(LAYOUT)
        names = {}
        for (n, sv), ps in lay.by_name.items():
            names.setdefault(n, []).extend(ps[:1])
        page = pymupdf.open(pdf)[0]
        words = [((w[0] + w[2]) / 2, (w[1] + w[3]) / 2, w[4]) for w in page.get_text('words')]
        scale, rotate = sheet_scale_rotation(config_with_inputs(PROJECT.path(PROJECT.cave['thconfig'])))
        _PDFMAP[pdf] = (calibrate(words, names, scale, rotate), lay)
    to_page, lay = _PDFMAP[pdf]
    ps = [to_page(lay.find(n, survey)[0]) for n in stations if lay.find(n, survey)]
    if not ps:
        raise ValueError(f'none of {stations} found in the layout' + (f' in survey {survey}' if survey else ''))
    xs = [p[0] for p in ps]; ys = [p[1] for p in ps]
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


def drawing_panel(pdf, clip, rings=(), dpi=220):
    import pymupdf
    from PIL import Image, ImageDraw
    page = pymupdf.open(pdf)[0]; c = pymupdf.Rect(*clip)
    pix = page.get_pixmap(dpi=dpi, clip=c)
    im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    d = ImageDraw.Draw(im); k = dpi / 72
    for x0, y0, x1, y1 in rings:
        d.ellipse([(x0 - c.x0) * k, (y0 - c.y0) * k, (x1 - c.x0) * k, (y1 - c.y0) * k], outline=(220, 0, 0), width=5)
    return im


def show(out, stations, title='', before=None, after=PLAN, ring=(), pad=15, view='plan', survey=None):
    """sketch | drawing, or sketch | before | after, one PNG."""
    from PIL import Image, ImageDraw, ImageFont
    clip = pdf_rect(stations, after, pad, survey)
    rings = [pdf_rect(ring, after, 6, survey)] if ring else []
    angle = page_angle(_PDFMAP[after][0]) if view == 'plan' else 0.0
    panels = [(sketch_panel(stations, view, survey=survey, angle=angle), '')]
    if before:
        panels.append((drawing_panel(before, clip, rings), 'Before'))
    panels.append((drawing_panel(after, clip, rings), 'After' if before else 'Drawing (station names shown)'))
    h = 680
    panels = [(p.resize((int(p.width * h / p.height), h)), lab) for p, lab in panels]
    W = sum(p.width for p, _ in panels) + 30 * (len(panels) - 1)
    im = Image.new('RGB', (W, h + 50), 'white'); d = ImageDraw.Draw(im)
    try:
        big = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 22)
        bold = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 18)
    except OSError:
        big = bold = None
    d.text((10, 10), title, fill=(0, 0, 0), font=big)
    x = 0
    for p, lab in panels:
        im.paste(p, (x, 50))
        if lab:
            d.text((x + 10, 52), lab, fill=(200, 0, 0), font=bold)
        x += p.width + 30
        if x < W:
            d.line([(x - 15, 50), (x - 15, h + 50)], fill=(150, 150, 150), width=2)
    im.save(out)
    return out


# -- building --------------------------------------------------------------------------

def review_config(s, out, select=None, names=True):
    """The sheet's config with station names on and one plan export to `out`.

    The plan layout is the one the config's plan export uses. `select`
    (a map, e.g. GoSouthMP@GoSouth.LongwoodValleySink) replaces the
    config's selection, to show one survey alone; with `names=False`
    the sheet's own station and centreline settings are kept."""
    m = re.search(r'^\s*export map\b[^\n]*-proj\w* plan\b[^\n]*-layout (\S+)', s, re.M) or \
        re.search(r'^\s*export map\b[^\n]*-layout (\S+)[^\n]*-proj\w* plan\b', s, re.M)
    if not m:
        raise ValueError('the config has no plan export with a -layout')
    lay = m.group(1)
    s = re.sub(r'^\s*export .*$', '', s, flags=re.M)
    if select:
        s = re.sub(r'^\s*select .*$', '', s, flags=re.M)
        s = re.sub(r'^(\s*source [^\n]*\n)', lambda mm: mm.group(1) + f'\nselect {select}\n', s, count=1, flags=re.M)
        # one survey alone: the sheet's legend, north arrow and scale bar are
        # placed for the whole cave and would land on the drawing
        s = s.rstrip('\n') + (f'\n\nlayout review-one\n  copy {lay}\n  legend off\n'
                              '  code tex-map\n    \\def\\maplayout{}\n  endcode\nendlayout\n')
        lay = 'review-one'
    if names:
        # a layout of its own, as the sheet's may be in an input file
        s = s.rstrip('\n') + (f'\n\nlayout review-names\n  copy {lay}\n  debug station-names\n'
                              '  symbol-show point station\n  symbol-show group cave-centreline\nendlayout\n')
        lay = 'review-names'
    return s.rstrip('\n') + f'\n\nexport map -projection plan -layout {lay} -o {out}\n'


def survey_map(survey):
    """The selection for one survey's plan map, from the master survey."""
    return f"{PROJECT.survey_plan_map(survey)}@{survey}.{PROJECT.cave['survey']}"


def build(config=PROJECT.cave['thconfig'], out=PLAN, therion=('therion',), survey=None, names=True):
    """The plan with station names, from the sheet's own config (only
    `survey`'s plan map, if given). Run in the config's folder, as its
    paths are relative to it."""
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    folder = os.path.dirname(os.path.abspath(config))
    s = review_config(open(config, encoding='utf-8').read(), out,
                      survey_map(survey) if survey else None, names)
    tmp = os.path.join(folder, 'review-plan.thcfg')
    open(tmp, 'w', encoding='utf-8').write(s)
    try:
        subprocess.run(list(therion) + ['-l', out[:-4] + '.log', os.path.basename(tmp)], cwd=folder,
                       check=True, stdout=subprocess.DEVNULL)
    finally:
        os.remove(tmp)
    _PDFMAP.pop(out, None)
    return out


# -- checks ----------------------------------------------------------------------------

def outline_lines(objs):
    return [o for o in objs if o.kind == 'line' and len(o.segments()) > 1 and '-close on' not in o.head
            and ('-outline out' in o.head or (o.head.startswith('line wall') and '-outline' not in o.head))]


def check(th2, scraps=None):
    """[(scrap, lines in the outline, valid, MetaPost turning number)]."""
    from .smooth import mp_turning, ring_ok
    t = open(th2, encoding='utf-8').read().replace('\r\n', '\n')
    res = []
    for m in re.finditer(r'^scrap (\S+)[^\n]*\n(.*?)^endscrap', t, re.S | re.M):
        if scraps and m.group(1) not in scraps:
            continue
        out = outline_lines(parse_scrap(m.group(2)))
        ol = [bezier_points(o.segments(), 20) for o in out]
        for ring in therion_rings(ol):
            pts = [p for i, r in ring for p in (ol[i][::-1] if r else ol[i])]
            segs = [reverse_segments(out[i].segments()) if r else out[i].segments() for i, r in ring]
            res.append((m.group(1), len(ring), ring_ok(pts)[0], mp_turning(segs)))
    return res


DOUBLED_NEAR = 1.0   # m: a wall this close behind another, seen from the nearest station,
DOUBLED_RUN = 1.0    # m: for this long in all, is a second wall on one side of the passage (a hard rule)


def doubled_walls(th2, scraps=None):
    """[(scrap, metres, (x, y))]: an outer wall lying behind another of the
    same scrap's walls, seen from the nearest station (Style.md, hard rule 2:
    one outer wall each side of the passage)."""
    t = open(th2, encoding='utf-8').read().replace('\r\n', '\n')
    res = []
    for m in re.finditer(r'^scrap (\S+)([^\n]*)\n(.*?)^endscrap', t, re.S | re.M):
        if scraps and m.group(1) not in scraps:
            continue
        sc = re.search(r'-scale \[([^]]*)\]', m.group(2))
        v = sc.group(1).split() if sc else []
        k = (float(v[2]) - float(v[0])) / (float(v[6]) - float(v[4])) if len(v) >= 8 else K
        objs = parse_scrap(m.group(3))
        st = list(stations_of(objs).values())
        walls = [LineString(bezier_points(o.segments(), 20)) for o in outline_lines(objs)]
        if not st:
            continue
        # walls joined end to end carry on from one another: not one behind the other
        ends = [(Point(w.coords[0]), Point(w.coords[-1])) for w in walls]
        joined = [{j for j in range(len(walls)) if j != i and
                   min(e.distance(f) for e in ends[i] for f in ends[j]) < 0.1 * k} for i in range(len(walls))]
        for i, a in enumerate(walls):
            run, at = 0.0, None
            n = max(2, int(a.length / (0.1 * k)) + 1)
            for q_ in range(n):
                p = a.interpolate(q_ / (n - 1), normalized=True)
                s = min(st, key=lambda q: math.dist(q, (p.x, p.y)))
                sight = LineString([(p.x, p.y), s])
                behind = any(j != i and j not in joined[i] and b.distance(p) < DOUBLED_NEAR * k
                             and b.intersects(sight) and b.intersection(sight).distance(p) > 0.05 * k
                             for j, b in enumerate(walls))
                if behind:                       # in all, along the wall (a sight line may slip past)
                    run += a.length / (n - 1) / k
                    at = at or (round(p.x), round(p.y))
            if run >= DOUBLED_RUN:
                res.append((m.group(1), run, at))
    return res


def gaps(th2, scrap, minlen=0.3, sketch=None):
    """[(metres, nearest station, a, b, share of the gap the sketch walls run along)]."""
    objs = scrap_objects(th2, scrap); st = stations_of(objs)
    out = outline_lines(objs)
    ol = [bezier_points(o.segments(), 8) for o in out]
    walls = []
    if sketch is None:
        found = sketches_for(list(st))
        sketch = found[0] if found else None
    if sketch:
        T = sketch_to_th2(sketch, objs)
        walls = [LineString([T(p) for p in pts]) for c, pts in _sketch(sketch).lines if c == 'BLACK' and len(pts) > 1]
    res = []
    for ring in therion_rings(ol):
        seq = [ol[i][::-1] if r else ol[i] for i, r in ring]
        for k in range(len(seq)):
            a, b = seq[k][-1], seq[(k + 1) % len(seq)][0]
            d = math.dist(a, b) / K
            if d <= minlen:
                continue
            ab = LineString([a, b])
            samples = [ab.interpolate(j / 10, normalized=True) for j in range(1, 10)]
            cov = sum(any(w.distance(q) < 0.3 * K for w in walls) for q in samples) / 9 if walls else 0
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            near = min(st, key=lambda n: math.dist(st[n], mid)) if st else ''
            res.append((round(d, 2), near, tuple(round(v) for v in a), tuple(round(v) for v in b), cov))
    return res


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog='review')
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build'); b.add_argument('--config', default=PROJECT.cave['thconfig'])
    b.add_argument('--therion', default='therion', help='the command that runs therion (e.g. a docker wrapper)')
    b.add_argument('--survey', help='show only this survey (its plan map), e.g. GoSouth')
    b.add_argument('--plain', action='store_true', help='without station names, as the sheet')
    b.add_argument('-o', '--out', default=PLAN)
    s = sub.add_parser('show'); s.add_argument('out'); s.add_argument('stations', nargs='+')
    s.add_argument('--title', default=''); s.add_argument('--before'); s.add_argument('--after', default=PLAN)
    s.add_argument('--ring', nargs='*', default=()); s.add_argument('--pad', type=float, default=15)
    s.add_argument('--survey', help="the stations' survey, e.g. GoSouth (station names restart in each survey)")
    g = sub.add_parser('gaps'); g.add_argument('th2'); g.add_argument('scraps', nargs='+')
    c = sub.add_parser('check'); c.add_argument('th2'); c.add_argument('scraps', nargs='*')
    a = ap.parse_args(argv)
    if a.cmd == 'build':
        print(build(a.config, a.out, therion=a.therion.split(), survey=a.survey, names=not a.plain))
    elif a.cmd == 'show':
        print(show(a.out, a.stations, a.title, a.before, a.after, a.ring, a.pad, survey=a.survey))
    elif a.cmd == 'gaps':
        for s_ in a.scraps:
            for d, near, p, q, cov in gaps(a.th2, s_):
                print(f'{s_}: {d:.2f} m near {near}: sketch wall along {cov:.0%}  {p} -> {q}')
    else:
        for s_, n, ok, tn in check(a.th2, a.scraps or None):
            flag = '' if ok and tn != 0 else '   <- ' + ('crosses itself' if not ok else 'MetaPost will warn')
            print(f'{s_}: {n} lines, valid {ok}, turning {tn}{flag}')
        for s_, run, at in doubled_walls(a.th2, a.scraps or None):
            print(f'{s_}: a second wall on one side of the passage for {run:.1f} m at {at[0]} {at[1]}   <- hard rule 2')
