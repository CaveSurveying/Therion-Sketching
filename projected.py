# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see tools/LICENSE.
"""A projected elevation's walls from the survey's extended elevation drawing.

    python3 -m tools.sketch2therion projected X [--angle 315] [--file]

For survey X (in <Cave>/X/):
1. exports Therion's centreline of X alone, projected to the angle the
   viewer faces (`-proj [elevation 315]`), as the backdrop
   `X/Notes/XE315.xvi` (as tools/ElevationsExx.py does);
2. projects the walls of `X/X.extended.th2` onto it (walls only, each with
   its subtype): a point of the extended drawing keeps its place along its
   nearest leg and its height above or below it; its offset along the
   passage is scaled by how much of that leg is seen across the view
   (a leg running towards the viewer is seen end on);
3. splits the drawing into scraps where the passage turns back across the
   view, which would draw it over itself: legs heading the same way across
   the view, joined at stations, make one scrap (a leg seen end on goes
   with a neighbour);
4. writes `X/XE315.th2` (scraps `XSE315_1`, ...) and, with --file, inputs
   it in `X/X.th` with `map XME315` and adds `XME315@X` to the cave's 315
   map (`LongwoodValleySinkM315` in `LongwoodValleySink.th`).

The drawing keeps to the survey's own projected centreline: Therion morphs
each scrap onto its stations wherever they end up (plan stage 5d).
"""
import argparse
import math
import os
import re
import subprocess
import sys
import tempfile

from shapely.geometry import LineString, MultiPoint, Point

from .. import project as _project
from . import register
from .tidy import bezier_points, parse_scrap, scale_of
from .walls import bezier_lines

PROJECT = _project.load()
MIN_PIECE = 0.5      # m: a shorter piece of a wall stays with its neighbours' scrap
END_ON = 0.3         # a leg seen across the view at less than this share of its length is end on
STEEP = 0.3          # m: a leg shorter than this along the extended drawing is a pitch or climb


def export_centreline(survey, angle, out):
    """Therion's centreline of the survey alone, projected, as an XVI file."""
    th = PROJECT.path(PROJECT.survey_file(survey))
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, 'm.th'), 'w', encoding='utf-8') as f:
            f.write(f"encoding  utf-8\nmap ProjectedCentreline -projection [elevation {angle}]\n  {survey}\nendmap\n")
        with open(os.path.join(tmp, 'p.thcfg'), 'w', encoding='utf-8') as f:
            f.write(f"encoding  utf-8\nsource {th}\nsource m.th\nselect ProjectedCentreline\n"
                    f"export map -projection [elevation {angle}] -fmt xvi -o {os.path.abspath(out)}\n")
        r = subprocess.run(['therion', '-l', 'p.log', 'p.thcfg'], cwd=tmp, capture_output=True, text=True)
        if r.returncode or not os.path.exists(out):
            log = open(os.path.join(tmp, 'p.log')).read() if os.path.exists(os.path.join(tmp, 'p.log')) else ''
            sys.exit(f"therion could not export {out}:\n{log[-2000:]}")


def read_extended(path):
    """[(scrap name, K, {station: (x, y) m}, [(subtype, [(x, y) m])])]: each
    scrap's stations and outline walls, subtypes on the line or its points."""
    text = open(path, encoding='utf-8').read().replace('\r\n', '\n')
    out = []
    for m in re.finditer(r'^(scrap (\S+)[^\n]*)\n(.*?)^endscrap', text, re.S | re.M):
        header, name, body = m.group(1), m.group(2), m.group(3)
        if '-projection extended' not in header:
            continue
        K = scale_of(header)
        st, walls = {}, []
        for o in parse_scrap(body):
            if o.kind == 'point':
                p = re.match(r'point (\S+) (\S+) station\b.*-name (\S+)', o.head)
                if p:
                    st[p.group(3).split('@')[0]] = (float(p.group(1)) / K, float(p.group(2)) / K)
                continue
            if o.kind != 'line' or not o.head.startswith('line wall') or '-outline none' in o.head:
                continue
            kind = (re.search(r'-subtype (\S+)', o.head) or [None, 'bedrock'])[1]
            # a subtype on a point (the old way) starts a new piece
            run, rows = [], []
            for r in o.rows:
                sm = re.match(r'\s*subtype (\S+)', r)
                if sm:
                    if len(rows) > 1:
                        run.append((kind, rows))
                    rows = rows[-1:] if rows else []
                    kind = sm.group(1)
                    continue
                if re.match(r'\s*-?[\d.]', r):
                    rows.append([float(v) for v in r.split()])
            if len(rows) > 1:
                run.append((kind, rows))
            for k, segs in run:
                pts = [(x / K, y / K) for x, y in bezier_points(segs, 8)]
                if len(pts) > 1:
                    walls.append((k, pts))
        out.append((name, K, st, walls))
    return out


class Projection:
    """Extended-drawing metres -> projected metres, leg by leg."""

    def __init__(self, ext, proj, legs):
        self.E, self.P = ext, proj
        self.legs = [(a, b) for a, b in legs if a in ext and b in ext and a in proj and b in proj
                     and math.dist(ext[a], ext[b]) > 1e-6]
        self.s = {}
        for a, b in self.legs:
            dx = ext[b][0] - ext[a][0]
            if abs(dx) >= STEEP:
                self.s[(a, b)] = (proj[b][0] - proj[a][0]) / dx
        for a, b in self.legs:              # a pitch: as the legs either side of it
            if (a, b) not in self.s:
                near = [v for (c, d), v in self.s.items() if {c, d} & {a, b}]
                self.s[(a, b)] = sum(near) / len(near) if near else 1.0

    def nearest(self, p):
        q = Point(p)
        return min(self.legs, key=lambda l: LineString([self.E[l[0]], self.E[l[1]]]).distance(q))

    def __call__(self, p, leg=None):
        a, b = leg or self.nearest(p)
        A, B = self.E[a], self.E[b]
        L = LineString([A, B])
        t = max(0.0, min(1.0, L.project(Point(p)) / L.length))
        foot = (A[0] + t * (B[0] - A[0]), A[1] + t * (B[1] - A[1]))
        r = (p[0] - foot[0], p[1] - foot[1])
        PA, PB = self.P[a], self.P[b]
        s = self.s[(a, b)]
        return (PA[0] + t * (PB[0] - PA[0]) + s * r[0], PA[1] + t * (PB[1] - PA[1]) + r[1])

    def heading(self, leg):
        """+1 or -1: which way the leg runs across the view, 0 if seen end on
        or a pitch (it then goes with a neighbour)."""
        a, b = leg
        dxe = self.E[b][0] - self.E[a][0]
        dxp = self.P[b][0] - self.P[a][0]
        if abs(dxe) < STEEP or abs(dxp) < END_ON * abs(dxe):
            return 0
        return 1 if dxp * dxe > 0 else -1


def scrap_groups(pr):
    """Groups of legs heading the same way across the view, joined at stations."""
    legs = pr.legs
    parent = list(range(len(legs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    head = [pr.heading(l) for l in legs]
    at = {}
    for i, (a, b) in enumerate(legs):
        at.setdefault(a, []).append(i)
        at.setdefault(b, []).append(i)
    for ls in at.values():
        for i in ls:
            for j in ls:
                if i < j and head[i] == head[j] != 0:
                    parent[find(i)] = find(j)
    for _ in range(len(legs)):              # a group of legs all seen end on joins a neighbour
        changed = False
        members = {}
        for i in range(len(legs)):
            members.setdefault(find(i), []).append(i)
        for root, ms in members.items():
            if any(head[i] for i in ms):
                continue
            nb = [j for i in ms for n in legs[i] for j in at[n] if find(j) != root and head[j]]
            if nb:
                parent[root] = find(nb[0])
                changed = True
                break
        if not changed:
            break
    groups = {}
    for i in range(len(legs)):
        groups.setdefault(find(i), []).append(legs[i])
    return list(groups.values())


OVERLAP = 0.3       # two legs that do not meet, overlapping in the view by more than this share of the
                    # smaller, are passage drawn over passage: separate scraps


def footprint(pieces, pr, legs):
    """The projected passage of a group: its walls and legs closed up."""
    from shapely.ops import unary_union
    geoms = [LineString([pr(p, _leg_for(pr, p, legs)) for p in pts]) for _, pts in pieces if len(pts) > 1]
    geoms += [LineString([pr.P[a], pr.P[b]]) for a, b in legs if pr.P[a] != pr.P[b]]
    if not geoms:
        return None
    return unary_union(geoms).buffer(1.0, join_style=1).buffer(-0.8, join_style=1)


def merge_groups(groups, walls, pr):
    """Groups joined at a station merge unless their projected passages
    overlap (drawn over each other), largest overlap-free joins first."""
    groups = [list(g) for g in groups]
    while len(groups) > 1:
        group_of = {l: gi for gi, g in enumerate(groups) for l in g}
        pieces = split_walls(walls, pr, group_of)
        fp = [footprint([(k, pts) for gg, k, pts in pieces if gg == gi], pr, g) for gi, g in enumerate(groups)]
        best = None
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                si = {n for l in groups[i] for n in l}
                if not si & {n for l in groups[j] for n in l}:
                    continue                    # not joined at a station
                if fp[i] is None or fp[j] is None or fp[i].is_empty or fp[j].is_empty:
                    share = 0.0
                else:
                    share = fp[i].intersection(fp[j]).area / max(1e-6, min(fp[i].area, fp[j].area))
                if share <= OVERLAP and (best is None or share < best[0]):
                    best = (share, i, j)
        if best is None:
            break
        _, i, j = best
        groups[i] += groups.pop(j)
    return groups


def _seg_dist3(p, a, b):
    ab = [b[i] - a[i] for i in range(3)]
    L2 = sum(v * v for v in ab)
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, sum((p[i] - a[i]) * ab[i] for i in range(3)) / L2))
    return math.dist(p, [a[i] + t * ab[i] for i in range(3)])


def model_groups(legs, model, angle):
    """Scraps from the 3D model: each wall triangle goes with its nearest
    leg; legs joined at a station are merged, the least overlapping first,
    while their passages seen facing `angle` overlap by no more than OVERLAP
    of the smaller: a scrap is as large as it can be without the passage
    drawn over itself."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    st = model.stations
    legs = [l for l in legs if l[0] in st and l[1] in st]
    if not legs:
        return []
    r = math.radians(angle + 90)            # the viewer's right
    view = lambda p: (p[0] * math.sin(r) + p[1] * math.cos(r), p[2])
    parts = {l: [] for l in legs}
    for tri in model.triangles:
        c = [sum(v[i] for v in tri) / 3 for i in range(3)]
        l = min(legs, key=lambda l: _seg_dist3(c, st[l[0]], st[l[1]]))
        if _seg_dist3(c, st[l[0]], st[l[1]]) > 8.0:
            continue
        g = Polygon([view(v) for v in tri])
        if g.area > 1e-6:
            parts[l].append(g.buffer(0.02))
    fp = {l: unary_union(ps) if ps else LineString([view(st[l[0]]), view(st[l[1]])]).buffer(0.3) for l, ps in parts.items()}
    # overlap of legs that do not meet at a station (legs that meet always overlap round it)
    ov = {}
    for i, l1 in enumerate(legs):
        for l2 in legs[i + 1:]:
            if set(l1) & set(l2):
                continue
            inter = fp[l1].intersection(fp[l2]).area
            if inter > 0:
                ov[(l1, l2)] = ov[(l2, l1)] = inter / max(1e-6, min(fp[l1].area, fp[l2].area))
    groups = [[l] for l in legs]

    def clash(gi, gj):
        return max((ov.get((a, b), 0.0) for a in gi for b in gj), default=0.0)
    while len(groups) > 1:
        best = None
        for i in range(len(groups)):
            si = {n for l in groups[i] for n in l}
            for j in range(i + 1, len(groups)):
                if not si & {n for l in groups[j] for n in l}:
                    continue
                c = clash(groups[i], groups[j])
                if c <= OVERLAP and (best is None or c < best[0]):
                    best = (c, i, j)
        if best is None:
            break
        _, i, j = best
        groups[i] += groups.pop(j)
    return groups


def chosen_groups(survey, legs, angle):
    """Leg groups from the scrap chooser for this view (autoscraps, set from
    the hand-drawn 315 splits: they keep larger overlaps in one scrap, so
    fewer scraps than model_groups gave, GoSouth 2 not 7); a leg between
    groups goes with its first station's. None if it cannot say."""
    if angle != 315:
        return None
    try:
        from . import autoscraps
        st_groups = autoscraps.scraps_for(PROJECT.path(PROJECT.survey_file(survey)), survey, '315', 'both')[0]
    except Exception as e:                  # (no model: the drawing's own groups)
        print(f"warning: scrap chooser: {e}", file=sys.stderr)
        return None
    home = {n: gi for gi, g in enumerate(st_groups) for n in g}
    out = [[] for _ in st_groups]
    for a, b in legs:
        gi = home.get(a, home.get(b))
        if gi is not None:
            out[gi].append((a, b))
    return [g for g in out if g] or None


def split_walls(walls, pr, group_of):
    """[(group, subtype, points)]: each wall cut where its nearest leg's
    group changes (a piece under MIN_PIECE stays with its neighbours)."""
    out = []
    for kind, pts in walls:
        gs = [group_of[pr.nearest(p)] for p in pts]
        runs = []
        for p, g in zip(pts, gs):
            if runs and runs[-1][0] == g:
                runs[-1][1].append(p)
            else:
                runs.append([g, ([runs[-1][1][-1]] if runs else []) + [p]])
        changed = True
        while changed and len(runs) > 1:
            changed = False
            for i, (g, rp) in enumerate(runs):
                if LineString(rp).length < MIN_PIECE if len(rp) > 1 else True:
                    j = i - 1 if i else i + 1
                    if j < i:
                        runs[j][1].extend(rp[1:])
                    else:
                        runs[j][1][:0] = rp[:-1]
                    runs.pop(i)
                    changed = True
                    break
        out += [(g, kind, rp) for g, rp in runs if len(rp) > 1]
    return out


NODE_GAP = 0.06      # m: no two nodes closer than this (lint node-gap is 0.05 m)


def _fitted(q, px, K):
    """th2 rows of a projected wall refitted as the plans are (smooth's Bezier fit within its
    TOL of the wall): nodes as sparse as the plans', about a metre apart, not one a point."""
    from .smooth import _fit_within
    rows = [[float(v) for v in r.split()] for r in bezier_lines(q, px)]
    return ["  " + " ".join("%.2f" % v for v in r) for r in _fit_within(rows, K)]


def _spaced(q):
    """The points with none closer than NODE_GAP to the one before (the ends kept)."""
    out = [q[0]]
    for p in q[1:-1]:
        if math.dist(p, out[-1]) >= NODE_GAP:
            out.append(p)
    if len(q) > 1:
        if len(out) > 1 and math.dist(q[-1], out[-1]) < NODE_GAP:
            out.pop()
        out.append(q[-1])
    return out


def stations_only(survey, angle=315, file_it=False, author=None, copyright=None):
    """One scrap with the survey's stations on the dots of its projected
    centreline (Notes/XE315.xvi), as tools/ElevationsExx.py lays it out:
    in the xvi's own units, offset from its lowest station, with the xvi
    as the backdrop. The walls are drawn round them by hand for now (log
    row 125: projected walls parked)."""
    folder = os.path.dirname(PROJECT.path(PROJECT.survey_file(survey)))
    tag = f"E{angle:03d}"
    name = f"{survey}S{tag}_1"
    if file_it:            # first, so the survey's map names only this scrap when Therion reads it
        file_into(survey, tag, [name])
    xvi_path = os.path.join(folder, 'Notes', f"{survey}{tag}.xvi")
    os.makedirs(os.path.dirname(xvi_path), exist_ok=True)
    export_centreline(survey, angle, xvi_path)
    t = open(xvi_path, encoding='utf-8').read()
    part = t.split('XVIstations', 1)[1].split('XVIshots', 1)[0]
    st = []
    for m in re.finditer(r'\{\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(\S+?)\s*\}', part):
        n, sv = (m.group(3).split('@') + [''])[:2]
        if sv.split('.')[0] in (survey, ''):
            st.append((float(m.group(1)), float(m.group(2)), n))
    if not st:
        sys.exit(f"{survey}: no stations in {xvi_path}")
    unit = float(re.search(r'XVIgrid\s+\{\s*\S+\s+\S+\s+(\S+)', t).group(1))     # xvi units a metre
    x0, y0 = min(x for x, _, _ in st), min(y for _, y, _ in st)
    W, H = max(x for x, _, _ in st) - x0, max(y for _, y, _ in st) - y0
    x1, y1, first = st[0]
    a = ''
    if author:
        a += ' -author %s "%s"' % tuple(author)
    if copyright:
        a += ' -copyright %s "%s"' % tuple(copyright)
    rel = os.path.relpath(xvi_path, folder)
    o = ["encoding  utf-8", PROJECT.licence_comment,
         f"##XTHERION## xth_me_area_adjust -128.0 -128.0 {W + 128:.2f} {H + 128:.2f}",
         "##XTHERION## xth_me_area_zoom_to 100",
         f"##XTHERION## xth_me_image_insert {{{x1 - x0:.2f} 1 1.0}} {{{y1 - y0:.2f} {first}}} {rel} 0 {{}}", "",
         f"# Projected elevation, facing {angle}: the stations on the dots of {rel}",
         "# (tools/sketch2therion projected). Walls to be drawn round them.", "",
         f"scrap {name} -projection [elevation {angle}]{a} -scale [0 0 {10 * unit:.3f} 0 0.0 0.0 10 0 m]", ""]
    for x, y, n in sorted(st, key=lambda s: register.natural(s[2])):
        o += ["point %.2f %.2f station -name %s" % (x - x0, y - y0, n), ""]
    o += ["endscrap", ""]
    out = os.path.join(folder, f"{survey}{tag}.th2")
    open(out, 'wb').write(("\n".join(o)).replace('\n', PROJECT.newline).encode('utf-8'))
    print(f"wrote {out}: {len(st)} stations on the dots of {xvi_path}")
    return out, [name]


def projected(survey, angle=315, file_it=False, author=None, copyright=None, out_dir=None):
    from . import convert
    from .roofs import Splays, SQL
    folder = os.path.dirname(PROJECT.path(PROJECT.survey_file(survey)))
    ext_path = os.path.join(folder, f"{survey}.extended.th2")
    if not os.path.exists(ext_path):
        sys.exit(f"{ext_path} not found: draw the extended elevation first")
    tag = f"E{angle:03d}"
    xvi_path = os.path.join(folder, 'Notes', f"{survey}{tag}.xvi")
    os.makedirs(os.path.dirname(xvi_path), exist_ok=True)
    export_centreline(survey, angle, xvi_path)
    lay = register.Layout(xvi_path)
    splays = Splays.from_database(PROJECT.path(SQL))
    legs = sorted({tuple(sorted((a.split('@')[0], b.split('@')[0])))
                   for a, bs in splays.legs.items() if a.endswith('@' + survey)
                   for b in bs if b.endswith('@' + survey)})
    proj = {}
    for (n, sv), ps in lay.by_name.items():
        if sv in (survey, '') and ps:
            proj.setdefault(n, ps[0])
    # in the xvi's own units, offset from its lowest station, as stations_only (and the hand-drawn
    # 315s): the stations on the dots of the backdrop (log row 131)
    xt = open(xvi_path, encoding='utf-8').read()
    unit = float(re.search(r'XVIgrid\s+\{\s*\S+\s+\S+\s+(\S+)', xt).group(1))
    x0 = min(p[0] for p in proj.values()) * unit
    y0 = min(p[1] for p in proj.values()) * unit
    px = lambda p: (unit * p[0] - x0, unit * p[1] - y0)
    model = None
    try:                                    # the 3D model, walls from the splays (as Loch shows it)
        from . import loch
        model = loch.export(PROJECT.path(PROJECT.survey_file(survey)))
        if not model.triangles:
            model = None
    except RuntimeError as e:
        print(f"warning: {e}; scraps from the drawing alone", file=sys.stderr)
    K = None
    body, names, hull = [], [], []
    for sname, Ke, ext, walls in read_extended(ext_path):
        K = K or Ke
        pr = Projection(ext, proj, legs)
        if not pr.legs:
            continue
        groups = chosen_groups(survey, pr.legs, angle) or \
            (model_groups(pr.legs, model, angle) if model else merge_groups(scrap_groups(pr), walls, pr))
        group_of = {l: gi for gi, g in enumerate(groups) for l in g}
        pieces = split_walls(walls, pr, group_of)
        for gi, g in enumerate(groups):
            mine = [(k, pts) for gg, k, pts in pieces if gg == gi]
            if not mine:
                continue
            name = f"{survey}S{tag}_{len(names) + 1}"
            attrs = _attrs(K, author, copyright).split(' -scale')[0]
            o = [f"scrap {name} -projection [elevation {angle}]{attrs} -scale [0 0 {10 * unit:.3f} 0 0.0 0.0 10 0 m]", "",
                 f"# Walls of {sname} ({os.path.basename(ext_path)}) projected to {angle}.", ""]
            lines = []
            for k, pts in mine:
                used = [_leg_for(pr, p, g) for p in pts]
                q = [pr(p, l) for p, l in zip(pts, used)]
                if sum(pr.s[l] for l in used) < 0:
                    q.reverse()                 # mirrored across the view: the passage stays on the same side
                q = LineString(q).simplify(0.01).coords[:]
                q = _spaced(q)
                if len(q) >= 2 and LineString(q).length >= MIN_PIECE:     # a scrap of wall only confuses the outline
                    lines.append((k, list(q)))
            for k, q in lines:
                hull += q
                o += [f"line wall{'' if k == 'bedrock' else ' -subtype ' + k}"] + _fitted(q, px, unit) + ["endline", ""]
            # no closing walls: Therion closes the outline itself (Style.md, lint wall-invisible)
            for n in sorted({n for l in g for n in l}, key=register.natural):
                o += ["point %.2f %.2f station -name %s" % (*px(proj[n]), n), ""]
            o += ["endscrap", ""]
            body += o
            names.append(name)
    if not names:
        sys.exit(f"{survey}: nothing to project")
    anchor = next(iter(proj))
    poly = MultiPoint(hull).convex_hull.buffer(1.0)
    head = convert.header(xvi_path, os.path.join(folder, 'x.th2'), anchor, px(proj[anchor]), [poly], px)
    note = [f"# Projected elevation, facing {angle}: the walls of {os.path.basename(ext_path)} projected by",
            "# tools/sketch2therion projected (walls only; one scrap per run of passage heading one way",
            "# across the view).", ""]
    from .tidy import tidy_text
    text = tidy_text("\n".join(head + note + body), PROJECT.drawing.get('map_scale', 500), elevation=True)
    out = os.path.join(out_dir or folder, f"{survey}{tag}.th2")
    if out_dir:                     # a copy to look at: its backdrop path from where it is
        os.makedirs(out_dir, exist_ok=True)
        text = text.replace(os.path.relpath(xvi_path, folder), os.path.relpath(xvi_path, out_dir))
        file_it = False
    text = text.replace('\r\n', '\n').replace('\n', PROJECT.newline)
    open(out, 'wb').write(text.encode('utf-8'))
    print(f"wrote {out}: {len(names)} scraps ({' '.join(names)}); backdrop {xvi_path}")
    if file_it:
        file_into(survey, tag, names)
    return out, names


def closures(lines, gap=0.05):
    """[(a, b)]: invisible walls closing a scrap's walls into one outline:
    from the longest wall, on to the nearest free end of another (its
    direction kept), and back to the start."""
    if not lines:
        return []
    left = sorted(range(len(lines)), key=lambda i: -LineString(lines[i]).length)
    first = left.pop(0)
    start, tail = lines[first][0], lines[first][-1]
    out = []
    while left:
        i, end = min(((i, e) for i in left for e in (0, -1)), key=lambda ie: math.dist(tail, lines[ie[0]][ie[1]]))
        left.remove(i)
        a = lines[i][end]
        if math.dist(tail, a) > gap:
            out.append((tail, a))
        tail = lines[i][-1 if end == 0 else 0]
    if math.dist(tail, start) > gap:
        out.append((tail, start))
    return out


def _leg_for(pr, p, group):
    """The nearest leg of the scrap's own group (so a wall does not jump to
    a passage folded over it)."""
    q = Point(p)
    return min(group, key=lambda l: LineString([pr.E[l[0]], pr.E[l[1]]]).distance(q))


def _attrs(K, author, copyright):
    a = ''
    if author:
        a += ' -author %s "%s"' % tuple(author)
    if copyright:
        a += ' -copyright %s "%s"' % tuple(copyright)
    r = 10 * K
    return a + f" -scale [0 0 {r:.2f} {r:.2f} 0.0 0.0 10 10 m]"


def file_into(survey, tag, names):
    """Input XE315.th2 in X.th with `map XME315`, and XME315@X in the cave's 315 map."""
    th = PROJECT.path(PROJECT.survey_file(survey))
    s = open(th, encoding='utf-8', newline='').read()
    nl = '\r\n' if '\r\n' in s else '\n'
    mapname = f"{survey}M{tag}"
    block = f"map {mapname}{nl}" + "".join(f"  {n}{nl}" for n in names) + f"endmap{nl}"
    if re.search(rf'^\s*input "?{survey}{tag}\.th2"?', s, re.M):
        s = re.sub(rf'map {mapname}\r?\n(?:.*\r?\n)*?endmap\r?\n', block, s, count=1)
    else:
        m = re.search(r'^\s*input "?' + re.escape(survey) + r'\.extended\.th2"?.*$', s, re.M)
        at = m.end() if m else 0
        s = s[:at] + f'{nl}input "{survey}{tag}.th2"{nl}{nl}{block}' + s[at:]
    open(th, 'w', encoding='utf-8', newline='').write(s)
    cave = PROJECT.path(PROJECT.cave['plan_map_file'])
    c = open(cave, encoding='utf-8', newline='').read()
    m = re.search(r'^map LongwoodValleySinkM315\s*\r?\n(.*?)^endmap', c, re.S | re.M)
    entry = f"{mapname}@{survey}"
    if m and entry not in m.group(1):
        c = c[:m.end(1)] + f"  {entry}{nl}" + c[m.end(1):]
        open(cave, 'w', encoding='utf-8', newline='').write(c)
    print(f"{th}: input {survey}{tag}.th2, map {mapname} ({' '.join(names)}); {entry} in LongwoodValleySinkM315")


def main(argv):
    p = argparse.ArgumentParser(prog='python3 -m tools.sketch2therion projected')
    p.add_argument('survey')
    p.add_argument('--angle', type=int, default=315, help='the direction the viewer faces (default 315)')
    p.add_argument('--file', action='store_true', help="input it in the survey and the cave's 315 map")
    p.add_argument('--author', nargs=2, metavar=('DATE', 'NAME'))
    p.add_argument('--copyright', nargs=2, metavar=('YEAR', 'HOLDER'))
    p.add_argument('--walls', action='store_true',
                   help='also project the extended drawing\'s walls (parked: log row 125)')
    p.add_argument('--out', help='with --walls: write into this folder instead (not filed)')
    a = p.parse_args(argv)
    if a.walls:
        projected(a.survey, a.angle, a.file, a.author, a.copyright, a.out)
    else:
        stations_only(a.survey, a.angle, a.file, a.author, a.copyright)


FORESHORTENED = 0.7  # a leg seen across the view at less than this share of its length: the passage behind
                     # it is seen too, so only the outermost roof and floor are drawn (hand-drawn 315s: there
                     # the roof is a median 0.23 m higher, the floor lower, than in a view seeing it side on)
BIN = 0.25           # m: the envelope is taken over this width across the view
UNDER = 0.1          # m: a roof point this far under the envelope (a floor point above it) is hidden


def across_share(pr, leg):
    a, b = leg
    de = abs(pr.E[b][0] - pr.E[a][0])
    return abs(pr.P[b][0] - pr.P[a][0]) / de if de >= STEEP else 1.0


def enveloped(pr, lines, group_of=None):
    """[(subtype, [(x, y) projected])] from [(subtype, [(x, y) extended], [leg per point])]: points on
    foreshortened legs are kept only where they are the outermost roof (above the leg) or floor
    (below it) of the passage seen there; a line is broken where its points are hidden."""
    top, bottom = {}, {}
    marked = []
    for k, pts, used in lines:
        q = []
        for p, l in zip(pts, used):
            v = pr(p, l)
            a, b = l
            A, B = pr.E[a], pr.E[b]
            t = ((p[0] - A[0]) * (B[0] - A[0]) + (p[1] - A[1]) * (B[1] - A[1])) / max(1e-9, math.dist(A, B) ** 2)
            up = p[1] > A[1] + max(0.0, min(1.0, t)) * (B[1] - A[1])
            # only a roof or floor (over or under the leg) can be hidden; not a wall beyond its ends
            # nor beside a pitch (WestPassage 58 to 62)
            fs = (across_share(pr, l) < FORESHORTENED and 0.0 < t < 1.0 and abs(B[0] - A[0]) >= STEEP
                  and abs(B[0] - A[0]) > abs(B[1] - A[1]))       # a steep leg: walls beside it, not over
            key = ((round(v[0] / BIN), (group_of or {}).get(l, 0)), up)
            if fs:
                if up:
                    top[key[0]] = max(top.get(key[0], -1e9), v[1])
                else:
                    bottom[key[0]] = min(bottom.get(key[0], 1e9), v[1])
            q.append((v, fs, key))
        marked.append((k, q))
    # the envelope also takes the passage seen side on there (it is in front of or behind it)
    for k, q in marked:
        for v, fs, (x, up) in q:
            if not fs:
                if up and x in top:
                    top[x] = max(top[x], v[1])
                if not up and x in bottom:
                    bottom[x] = min(bottom[x], v[1])
    out = []
    for k, q in marked:
        run = []
        for v, fs, (x, up) in q:
            hidden = fs and ((up and v[1] < top.get(x, v[1]) - UNDER) or (not up and v[1] > bottom.get(x, v[1]) + UNDER))
            if hidden:
                if len(run) > 1:
                    out.append((k, run))
                run = []
            else:
                run.append(v)
        if len(run) > 1:
            out.append((k, run))
    return out


def predict(ext, proj, legs, ext_lines, envelope=True, **kw):
    """Projected walls (lists of points) of extended walls, for scoring against hand-drawn views."""
    pr = Projection(ext, proj, legs)
    lines = [(k, pts, [pr.nearest(p) for p in pts]) for k, pts in ext_lines]
    if not envelope:
        return [[pr(p, l) for p, l in zip(pts, used)] for k, pts, used in lines]
    groups = scrap_groups(pr) if envelope == 'groups' else [pr.legs]
    group_of = {l: gi for gi, g in enumerate(groups) for l in g}
    return [q for k, q in enveloped(pr, lines, group_of)]
