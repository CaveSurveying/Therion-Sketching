# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""An extended elevation for a survey that has none, unfolded from its
hand-drawn projected elevations.

    python3 -m tools.sketch2therion unfold X [--out DIR]

Older surveys (Entrance, GoWest, TennisBallRift, TickleRift, Triassic,
Triassic2) have projected elevations (XE000, XE90, XE315, XE0) but no
extended one and no elevation sketch. For each leg, the view that sees it
most side on is used; the walls drawn by it there are moved into the
extended view keeping their place along the leg and their height (their
offset along the passage scaled as the leg is seen). The extended layout
is Therion's, of the survey's centreline alone. A plain `-projection
elevation` (no angle) is matched to its stations' 3D positions to find
which way it faces. Written to DIR (default review/extended-new), not
filed: for the user to look at.
"""
import argparse
import math
import os
import re
import sqlite3
import subprocess
import sys
import tempfile

from shapely.geometry import LineString, Point

from . import project as _project
from . import register
from .tidy import bezier_points, parse_scrap
from .walls import bezier_lines

PROJECT = _project.load()
K = 78.74016            # drawing units a metre (as the 2026 extended drawings)
NEAR = 4.0              # m: a wall point this near its leg (in the view) is that leg's
SIDE_ON = 0.35          # a leg seen across the view at less than this share of its length: not from this view
MIN_RUN = 0.4           # m: shorter runs of wall are left out


def _database(sql_text, survey, names=None):
    db = sqlite3.connect(':memory:')
    db.executescript(sql_text)
    rows = list(db.execute("select ID, PARENT_ID from SURVEY where NAME = ?", (survey,)))
    if not rows:
        return None
    sid, parent = rows[0]

    def stations(s):
        return {i: (n, (x, y, z)) for i, n, x, y, z in db.execute(
            "select ID, NAME, X, Y, Z from STATION where SURVEY_ID = ?", (s,))}
    st = stations(sid)
    if not st and names:            # -namespace off: its stations are its parent's (Entrance)
        st = {i: v for i, v in stations(parent).items() if v[0] in names}
    pos = {n: p for n, p in st.values() if n not in ('.', '-', '')}
    byid = {i: n for i, (n, _) in st.items()}
    legs = set()
    for x, y in db.execute("select FROM_ID, TO_ID from SHOT"):
        na, nb = byid.get(x), byid.get(y)
        if na in pos and nb in pos and na != nb:
            legs.add(tuple(sorted((na, nb))))
    return pos, sorted(legs)


def _own_names(survey):
    """Station names in the survey's data (its legs' first two fields)."""
    th = open(PROJECT.path(PROJECT.survey_file(survey)), encoding='utf-8', errors='replace').read()
    names = set()
    for line in th.splitlines():
        v = line.split('#')[0].split()
        if len(v) >= 5 and re.match(r'^-?[\d.]+$', v[2]):
            names.update(v[:2])
    return names


def survey_3d(survey):
    """({station: (x, y, z)}, [(a, b) legs]) from Therion's database: the
    cave's, else one exported for the survey alone (GoWest, TickleRift are
    not in the cave's build)."""
    names = _own_names(survey)
    r = _database(open(PROJECT.path(PROJECT.build['sql']), encoding='utf-8', errors='replace').read(), survey, names)
    if r and r[0]:
        return r
    th = PROJECT.path(PROJECT.survey_file(survey))
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, 's.sql')
        with open(os.path.join(tmp, 'p.thcfg'), 'w', encoding='utf-8') as f:
            f.write(f"encoding  utf-8\nsource {th}\nexport database -fmt sql -o {out}\n")
        subprocess.run(['therion', '-l', 'p.log', 'p.thcfg'], cwd=tmp, capture_output=True, text=True)
        if os.path.exists(out):
            r = _database(open(out, encoding='utf-8', errors='replace').read(), survey, names)
    if not r or not r[0]:
        sys.exit(f"{survey}: no stations found in Therion's database")
    return r


def extended_layout(survey):
    """{station: (x, y) m}: Therion's extended layout of the survey's centreline."""
    th = PROJECT.path(PROJECT.survey_file(survey))
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, 'e.xvi')
        with open(os.path.join(tmp, 'm.th'), 'w', encoding='utf-8') as f:
            f.write(f"encoding  utf-8\nmap ExtendedCentreline -projection extended\n  {survey}\nendmap\n")
        with open(os.path.join(tmp, 'p.thcfg'), 'w', encoding='utf-8') as f:
            f.write(f"encoding  utf-8\nsource {th}\nsource m.th\nselect ExtendedCentreline\n"
                    f"export map -projection extended -fmt xvi -o {out}\n")
        subprocess.run(['therion', '-l', 'p.log', 'p.thcfg'], cwd=tmp, capture_output=True, text=True)
        if not os.path.exists(out):
            sys.exit(f"{survey}: therion could not export its extended centreline")
        lay = register.Layout(out)
    return {n: ps[0] for (n, sv), ps in lay.by_name.items() if sv in (survey, '') and ps}


def _angle_of(header):
    m = re.search(r'-projection \[elevation\s+(-?[\d.]+)', header)
    return float(m.group(1)) if m else None


def _view(p, theta):
    """(across the view, height) of a 3D point seen facing azimuth theta (degrees)."""
    t = math.radians(theta)
    return (p[0] * math.cos(t) - p[1] * math.sin(t), p[2])


def _fit(pairs):
    """Drawing (u, v) ~ s * (h, z) + (a, b), s may be negative across (a
    mirrored view): (s_h, s_z, a, b, rms in m)."""
    n = len(pairs)
    mh = sum(h for (h, z), _ in pairs) / n
    mz = sum(z for (h, z), _ in pairs) / n
    mu = sum(u for _, (u, v) in pairs) / n
    mv = sum(v for _, (u, v) in pairs) / n
    shh = sum((h - mh) ** 2 for (h, z), _ in pairs)
    szz = sum((z - mz) ** 2 for (h, z), _ in pairs)
    sh = sum((h - mh) * (u - mu) for (h, z), (u, v) in pairs) / shh if shh else 1.0
    sz = sum((z - mz) * (v - mv) for (h, z), (u, v) in pairs) / szz if szz else abs(sh)
    s = (abs(sh) + abs(sz)) / 2 or 1.0
    sh, sz = math.copysign(s, sh), math.copysign(s, sz)
    a, b = mu - sh * mh, mv - sz * mz
    rms = math.sqrt(sum((sh * h + a - u) ** 2 + (sz * z + b - v) ** 2 for (h, z), (u, v) in pairs) / n) / s
    return sh, sz, a, b, rms


def ee_layout(survey, pos):
    """(path, K, {station: (x, y) m}) of the survey's old extended drawing
    `X.ee.th2` (stations only, from Therion's extended xvi): its scale is
    found from its stations' heights against the 3D ones (most have no
    -scale), so the walls go on in its own frame."""
    folder = os.path.dirname(PROJECT.path(PROJECT.survey_file(survey)))
    path = next((os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.endswith('.ee.th2')), None)
    if not path:
        return None
    st = {}
    for m in re.finditer(r'^point (\S+) (\S+) station\b.*-name (\S+)', open(path, encoding='utf-8').read(), re.M):
        n = m.group(3).split('@')[0]
        if n in pos:
            st[n] = (float(m.group(1)), float(m.group(2)))
    zs = [(pos[n][2], st[n][1]) for n in st]
    mz, mv = sum(z for z, _ in zs) / len(zs), sum(v for _, v in zs) / len(zs)
    K = sum((z - mz) * (v - mv) for z, v in zs) / sum((z - mz) ** 2 for z, _ in zs)
    return path, K, {n: (x / K, y / K) for n, (x, y) in st.items()}


def views(survey, pos, skip=()):
    """[(file, theta, fit, {station: (h, z)}, [(subtype, [(h, z) m])])] for each drawn view scrap."""
    folder = os.path.dirname(PROJECT.path(PROJECT.survey_file(survey)))
    out = []
    for f in sorted(os.listdir(folder)):
        if not re.match(rf'{survey}E\d+\.th2$', f) or f[len(survey):-4] in skip:
            continue
        t = open(os.path.join(folder, f), encoding='utf-8', errors='replace').read()
        for m in re.finditer(r'^(scrap (\S+)[^\n]*)\n(.*?)^endscrap', t, re.S | re.M):
            objs = parse_scrap(m.group(3))
            st = {}
            for o in objs:
                p = re.match(r'point (\S+) (\S+) station .*-name (\S+)', o.head) if o.kind == 'point' else None
                if p and p.group(3).split('@')[0] in pos:
                    st[p.group(3).split('@')[0]] = (float(p.group(1)), float(p.group(2)))
            walls = [((re.search(r'-subtype (\S+)', o.head) or [None, None])[1], bezier_points(o.segments(), 8))
                     for o in objs if o.kind == 'line' and o.head.startswith('line wall')
                     and '-subtype invisible' not in o.head and len(o.segments()) > 1]
            if len(st) < 2 or not walls:
                continue
            theta = _angle_of(m.group(1))
            cands = [theta] if theta is not None else [float(a) for a in range(0, 360, 2)]
            best = None
            for th in cands:
                fit = _fit([(_view(pos[n], th), st[n]) for n in st])
                if best is None or fit[4] < best[1][4]:
                    best = (th, fit)
            th, (sh, sz, a, b, rms) = best
            to_m = lambda q: ((q[0] - a) / sh, (q[1] - b) / sz)
            out.append((f"{f} {m.group(2)}", th, rms, {n: _view(pos[n], th) for n in pos},
                        [(k, [to_m(q) for q in pp]) for k, pp in walls]))
    return out


def unfold(survey, ext=None, skip=()):
    """The extended walls; `ext` is the frame ({station: (x, y) m}, default
    Therion's extended layout), `skip` views left out (E315: to learn the
    315 from the others)."""
    pos, legs = survey_3d(survey)
    ext = ext or extended_layout(survey)
    legs = [l for l in legs if l[0] in ext and l[1] in ext]
    vs = views(survey, pos, skip)
    if not vs or not legs:
        sys.exit(f"{survey}: no drawn views with stations, or no legs")
    # each leg's best view: the one seeing it most side on
    def across(v, l):
        p, q = v[3][l[0]], v[3][l[1]]
        horiz = math.hypot(pos[l[1]][0] - pos[l[0]][0], pos[l[1]][1] - pos[l[0]][1])
        if horiz < 0.5 * abs(pos[l[1]][2] - pos[l[0]][2]) or horiz < 0.2:
            return 1.0                  # a pitch: seen side on from every view (GoWest 47)
        return abs(q[0] - p[0]) / horiz
    def drawn(i, l):                    # how much of the view's walls lie by the leg
        seg = LineString([vs[i][3][l[0]], vs[i][3][l[1]]]) if vs[i][3][l[0]] != vs[i][3][l[1]] else Point(vs[i][3][l[0]])
        return sum(1 for _, pp in vs[i][4] for p in pp if seg.distance(Point(p)) < NEAR)
    best = {l: max(range(len(vs)), key=lambda i: (round(across(vs[i], l), 1), drawn(i, l), -vs[i][2])) for l in legs}
    lines = []
    for vi, (name, th, rms, vpos, walls) in enumerate(vs):
        segs = {l: LineString([vpos[l[0]], vpos[l[1]]]) for l in legs if vpos[l[0]] != vpos[l[1]]}
        for kind, pp in walls:
            run = []
            for p in pp:
                q = Point(p)
                l = min(segs, key=lambda x: segs[x].distance(q), default=None)
                ok = l is not None and best[l] == vi and segs[l].distance(q) < NEAR and across(vs[vi], l) >= SIDE_ON
                if ok:
                    A, B = vpos[l[0]], vpos[l[1]]
                    L = segs[l]
                    t = max(0.0, min(1.0, L.project(q) / L.length))
                    foot = (A[0] + t * (B[0] - A[0]), A[1] + t * (B[1] - A[1]))
                    EA, EB = ext[l[0]], ext[l[1]]
                    dxv = B[0] - A[0]
                    s = (EB[0] - EA[0]) / dxv if abs(dxv) > 1e-6 else 1.0
                    run.append((EA[0] + t * (EB[0] - EA[0]) + s * (p[0] - foot[0]),
                                EA[1] + t * (EB[1] - EA[1]) + (p[1] - foot[1])))
                elif run:
                    lines.append((kind, run))
                    run = []
            if run:
                lines.append((kind, run))
    lines = [(k, r) for k, r in lines if len(r) > 1 and LineString(r).length >= MIN_RUN]
    return vs, ext, lines


def _extended_scrap(survey):
    from .settings import SETTINGS
    return f"{PROJECT.scrap_prefix(survey)}{SETTINGS['elevation_suffix']}1"


def write(survey, out_dir):
    vs, ext, lines = profile(survey)          # a profile, as the .ee walls (log row 159)
    px = lambda p: (K * p[0], K * p[1])
    name = _extended_scrap(survey)
    o = ["encoding  utf-8", PROJECT.licence_comment, "",
         f"# Extended elevation of {survey}, unfolded from its projected elevations by",
         "# tools/sketch2therion unfold (each leg from the view seeing it most side on):"]
    o += [f"#   {n}: facing {th:.0f}, stations within {rms:.2f} m" for n, th, rms, *_ in vs]
    o += ["", f"scrap {name} -projection extended -scale [0 0 {10 * K:.2f} {10 * K:.2f} 0.0 0.0 10 10 m]", ""]
    for k, r in lines:
        q = list(LineString(r).simplify(0.03).coords)
        o += [f"line wall{' -subtype ' + k if k and k != 'bedrock' else ''}"] + bezier_lines(q, px) + ["endline", ""]
    for n in sorted(ext, key=register.natural):
        o += ["point %.2f %.2f station -name %s" % (*px(ext[n]), n), ""]
    o += ["endscrap", ""]
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{survey}.extended.th2")
    open(path, 'w', encoding='utf-8').write("\n".join(o))
    print(f"wrote {path}: {len(lines)} walls from {len(vs)} view scrap(s) "
          + ", ".join(f"{n} facing {th:.0f} ({rms:.2f} m)" for n, th, rms, *_ in vs))
    return path


def write_ee(survey):
    """The walls drawn into the survey's old extended drawing X.ee.th2 (its
    stations as they are), as a profile from its projected elevations."""
    pos, _ = survey_3d(survey)
    found = ee_layout(survey, pos)
    if not found:
        sys.exit(f"{survey}: no .ee.th2")
    path, K, ext = found
    vs, ext, lines = profile(survey, ext)
    px = lambda p: (K * p[0], K * p[1])
    text = open(path, encoding='utf-8', newline='').read()
    nl = '\r\n' if '\r\n' in text else '\n'
    text = re.sub(r'(?m)^# Walls drawn by tools/sketch2therion unfold --ee.*?(?=^endscrap)', '', text.replace('\r\n', '\n'), flags=re.S)
    o = ["# Walls drawn by tools/sketch2therion unfold --ee: roof and floor along each leg as the",
         "# projected elevation seeing it most side on has them (walls either side of a pitch):"]
    o += [f"#   {n}: facing {th:.0f}, stations within {rms:.2f} m" for n, th, rms, *_ in vs]
    o.append("")
    for k, r in lines:
        q = list(LineString(r).simplify(0.03).coords)
        o += [f"line wall{' -subtype ' + k if k and k != 'bedrock' else ''}"] + bezier_lines(q, px) + ["endline", ""]
    at = text.rfind('endscrap')
    text = text[:at] + "\n".join(o) + "\n" + text[at:]
    open(path, 'w', encoding='utf-8', newline='').write(text.replace('\n', nl))
    print(f"wrote {len(lines)} walls into {path} (from {len(vs)} view scraps)")
    return path


def _in_cave(survey):
    """The map reference for the cave's maps, or None if the cave does not input the survey."""
    cave = open(PROJECT.path(PROJECT.cave['plan_map_file']), encoding='utf-8').read()
    if not re.search(rf'^\s*input {survey}/{survey}\.th\s*$', cave, re.M):
        return None
    th = open(PROJECT.path(PROJECT.survey_file(survey)), encoding='utf-8').read()
    return f"{survey}MEe" if re.search(r'-namespace off', th) else f"{survey}MEe@{survey}"


def file_map(survey, after, scraps):
    """`map XMEe` of the scraps in X.th after the line matching `after` (an input), and
    XMEe in the cave's extended map (LongwoodValleySinkMEe) if the cave has the survey."""
    th = PROJECT.path(PROJECT.survey_file(survey))
    s = open(th, encoding='utf-8', newline='').read()
    nl = '\r\n' if '\r\n' in s else '\n'
    if re.search(rf'^map {survey}MEe\b', s, re.M):
        sys.exit(f"{th} already has map {survey}MEe")
    m = re.search(after, s, re.M)
    block = f"{nl}map {survey}MEe{nl}" + "".join(f"  {n}{nl}" for n in scraps) + f"endmap{nl}"
    s = s[:m.end()] + nl + block + s[m.end():] if m else s
    open(th, 'w', encoding='utf-8', newline='').write(s)
    ref = _in_cave(survey)
    if ref:
        cave = PROJECT.path(PROJECT.cave['plan_map_file'])
        c = open(cave, encoding='utf-8', newline='').read()
        mm = re.search(r'^map LongwoodValleySinkMEe\s*\r?\n(.*?)^endmap', c, re.S | re.M)
        if mm and ref not in mm.group(1):
            c = c[:mm.end(1)] + f"  {ref}{nl}" + c[mm.end(1):]
            open(cave, 'w', encoding='utf-8', newline='').write(c)
    print(f"{th}: map {survey}MEe ({' '.join(scraps)})" + (f"; {ref} in LongwoodValleySinkMEe" if ref else " (not in the cave)"))


def _attribution(survey):
    """' -author DATE "NAME" -copyright YEAR "LICENCE"' from the survey's date and its notes
    team member (who drew the elevations it is unfolded from), or '' if not given."""
    th = open(PROJECT.path(PROJECT.survey_file(survey)), encoding='utf-8', errors='replace').read()
    d = re.search(r'^\s*date\s+(\d{4})([\d.]*)', th, re.M)
    t = re.search(r'^\s*team\s+"([^"]+)"\s+.*\bnotes\b', th, re.M)
    if not d or not t:
        return ''
    return f' -author {d.group(1)}{d.group(2)} "{t.group(1).strip()}" -copyright {d.group(1)} "{PROJECT.drawing['licence']}"'


def file_extended(survey):
    """X.extended.th2 written into the survey's folder and filed (input, map, cave map)."""
    folder = os.path.dirname(PROJECT.path(PROJECT.survey_file(survey)))
    if os.path.exists(os.path.join(folder, f"{survey}.extended.th2")):
        sys.exit(f"{survey}.extended.th2 exists: not overwritten")
    path = write(survey, folder)
    t = open(path, encoding='utf-8').read()
    open(path, 'w', encoding='utf-8').write(t.replace(' -projection extended -scale',
                                                      f' -projection extended{_attribution(survey)} -scale', 1))
    th = PROJECT.path(PROJECT.survey_file(survey))
    s = open(th, encoding='utf-8', newline='').read()
    nl = '\r\n' if '\r\n' in s else '\n'
    m = list(re.finditer(rf'^map {survey}ME315\b.*?^endmap[^\n]*\n', s, re.S | re.M)) or \
        list(re.finditer(r'^\s*input .*\n', s, re.M))
    at = m[-1].end() if m else 0
    s = s[:at] + f'{nl}input "{survey}.extended.th2"{nl}' + s[at:]
    open(th, 'w', encoding='utf-8', newline='').write(s)
    file_map(survey, rf'^input "{survey}\.extended\.th2".*$', [_extended_scrap(survey)])
    return path


def file_ee(survey):
    """map XMEe of the old extended drawing's scrap (X.ee.th2), filed as file_map."""
    folder = os.path.dirname(PROJECT.path(PROJECT.survey_file(survey)))
    f = next(f for f in sorted(os.listdir(folder)) if f.endswith('.ee.th2'))
    names = re.findall(r'^scrap (\S+)', open(os.path.join(folder, f), encoding='utf-8').read(), re.M)
    file_map(survey, rf'^\s*input "?{re.escape(f)}"?.*$', names)


def main(argv):
    p = argparse.ArgumentParser(prog='python3 -m tools.sketch2therion unfold')
    p.add_argument('surveys', nargs='+')
    p.add_argument('--out', default='review/extended-new')
    p.add_argument('--ee', action='store_true', help="draw the walls into the survey's own X.ee.th2")
    p.add_argument('--file', action='store_true',
                   help="file it: X.extended.th2 in the survey (or, with --ee, its X.ee.th2 as it is), "
                        "map XMEe in X.th and the cave's extended map")
    a = p.parse_args(argv)
    for s in a.surveys:
        if a.file:
            file_ee(s) if a.ee else file_extended(s)
        elif a.ee:
            write_ee(s)
        else:
            write(s, a.out)


STEP = 0.2              # m: roof and floor taken this often along a leg
REACH = 15.0             # m: the furthest a roof or floor is looked for from its leg
JOIN = 0.6              # m: profile runs whose ends are this close (in the extended) are one line
JUMP = 1.0              # m: a roof or floor height changing more than this between samples breaks the line


def profile(survey, ext=None, skip=()):
    """The extended walls as a profile: along each leg, in the view that
    sees it most side on, the nearest wall above and below the leg (the
    roof and the floor) are kept at their height above or below it, and
    drawn along the leg as unfolded. A pitch takes the walls either side
    instead, across the drawing. Only walls nearest the leg itself or one
    meeting it count (not a passage drawn behind it)."""
    pos, legs = survey_3d(survey)
    ext = ext or extended_layout(survey)
    legs = [l for l in legs if l[0] in ext and l[1] in ext]
    vs = views(survey, pos, skip)
    if not vs or not legs:
        sys.exit(f"{survey}: no drawn views with stations, or no legs")
    horiz = {l: math.hypot(pos[l[1]][0] - pos[l[0]][0], pos[l[1]][1] - pos[l[0]][1]) for l in legs}
    pitch = {l: horiz[l] < 0.5 * abs(pos[l[1]][2] - pos[l[0]][2]) or horiz[l] < 0.2 for l in legs}

    def across(v, l):
        if pitch[l]:
            return 1.0
        p, q = v[3][l[0]], v[3][l[1]]
        return abs(q[0] - p[0]) / horiz[l]
    geo = []
    for name, th, rms, vpos, walls in vs:
        segs = {l: LineString([vpos[l[0]], vpos[l[1]]]) if vpos[l[0]] != vpos[l[1]] else Point(vpos[l[0]]) for l in legs}
        wl = [(k, LineString(pp)) for k, pp in walls if len(pp) > 1]
        geo.append((segs, wl))

    def drawn(i, l):
        seg = geo[i][0][l]
        return sum(1 for _, w in geo[i][1] if w.distance(seg) < NEAR)
    best = {l: max(range(len(vs)), key=lambda i: (round(across(vs[i], l), 1), drawn(i, l), -vs[i][2])) for l in legs}
    meets = lambda l, m: bool(set(l) & set(m))

    def hit(i, l, a, b):
        """Nearest wall crossing on the ray a -> b owned by the leg (or one meeting it): (distance, subtype)."""
        segs, wl = geo[i]
        ray = LineString([a, b])
        out = None
        for k, w in wl:
            x = ray.intersection(w)
            pts = [x] if x.geom_type == 'Point' else list(getattr(x, 'geoms', []))
            for p in pts:
                if p.geom_type != 'Point':
                    continue
                own = min(segs, key=lambda m: segs[m].distance(p))
                if not (own == l or meets(own, l)) and segs[own].distance(p) < segs[l].distance(p) - 0.3:
                    continue
                d = math.dist(a, (p.x, p.y))
                if d > 0.02 and (out is None or d < out[0]):
                    out = (d, k)
        return out
    runs = []                   # [(subtype, [(x, y) m in the extended])]
    for l in legs:
        i = best[l]
        vpos = vs[i][3]
        A, B = vpos[l[0]], vpos[l[1]]
        EA, EB = ext[l[0]], ext[l[1]]
        if pitch[l]:
            # across the drawing: the side the passage goes on is that of the legs either side
            near = [m for m in legs if meets(m, l) and not pitch[m]]
            sg = 1.0
            if near:
                m = near[0]
                dv = vs[i][3][m[1]][0] - vs[i][3][m[0]][0]
                de = ext[m[1]][0] - ext[m[0]][0]
                sg = -1.0 if dv * de < 0 else 1.0
            n = max(2, int(abs(B[1] - A[1]) / STEP) + 1)
            for side in (1, -1):
                cur = []
                for j in range(n):
                    t = j / (n - 1)
                    f = (A[0] + t * (B[0] - A[0]), A[1] + t * (B[1] - A[1]))
                    h = hit(i, l, f, (f[0] + side * REACH, f[1]))
                    if h:
                        cur.append((h[1], (EA[0] + t * (EB[0] - EA[0]) + sg * side * h[0], EA[1] + t * (EB[1] - EA[1]))))
                    elif cur:
                        runs.append(cur)
                        cur = []
                if cur:
                    runs.append(cur)
            continue
        if across(vs[i], l) < SIDE_ON:
            continue
        n = max(2, int(math.dist(EA, EB) / STEP) + 1)
        for side in (1, -1):
            cur = []
            for j in range(n):
                t = j / (n - 1)
                f = (A[0] + t * (B[0] - A[0]), A[1] + t * (B[1] - A[1]))
                h = hit(i, l, f, (f[0], f[1] + side * REACH))
                if h and (not cur or abs(cur[-1][1][1] - (EA[1] + t * (EB[1] - EA[1]) + side * h[0])) < JUMP):
                    cur.append((h[1], (EA[0] + t * (EB[0] - EA[0]), EA[1] + t * (EB[1] - EA[1]) + side * h[0])))
                else:
                    if len(cur) > 1:
                        runs.append(cur)
                    cur = [(h[1], (EA[0] + t * (EB[0] - EA[0]), EA[1] + t * (EB[1] - EA[1]) + side * h[0]))] if h else []
            if len(cur) > 1:
                runs.append(cur)
    lines = _joined([[p for _, p in r] for r in runs], [r[0][0] for r in runs])
    lines = [(k, r) for k, r in lines if len(r) > 1 and LineString(r).length >= MIN_RUN]
    return vs, ext, lines


def _joined(runs, kinds):
    """Runs end to end (ends within JOIN) made one line, greedily."""
    runs = [list(r) for r in runs]
    kinds = list(kinds)
    changed = True
    while changed:
        changed = False
        for i in range(len(runs)):
            for j in range(len(runs)):
                if i == j or not runs[i] or not runs[j]:
                    continue
                a, b = runs[i], runs[j]
                for ra, rb in ((a, b), (a, b[::-1]), (a[::-1], b), (a[::-1], b[::-1])):
                    if math.dist(ra[-1], rb[0]) < JOIN:
                        runs[i] = ra + rb[1:]
                        runs[j] = []
                        changed = True
                        break
    return [(k, r) for k, r in zip(kinds, runs) if r]
