# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""Legs and splays against Therion's fill (tools/sketch2therion/Style.md, Checking).

The fill is where Therion thinks the passage is: inside the scraps'
outlines. Legs are all inside it, except at passage ends where the
continuation is not drawn yet; a splay end may go outside a wall, and is
listed to check when it is more than 0.5 m outside.

Reads what LongwoodValleySink/Whole_cave.thcfg writes to output/check/:
for each projection, the ESRI export (scrap outlines, and the stations
where the drawings put them, in Therion's coordinates) and the XVI export
(stations and every shot, splays too, in its own frame: the same scale,
shifted). The shift is found from the stations both have.

    python3 -m tools.sketch2therion fillcheck [--build] [--survey X ...] [--projection plan|extended|e315]

--build first runs the cave's check_build (project.toml) with Therion and
lists its errors and the scraps MetaPost says cross themselves. The
report is also written to output/check/fillcheck.txt.
"""
import math
import os
import re
import statistics
import struct

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

SPLAY_OUT = 0.5      # m: a splay end further outside the fill than this is listed to check
LEG_OUT = 0.1        # m: a leg is outside where it is further than this from the fill
PROJECTIONS = ('plan', 'extended', 'e315')


def _dbf(path):
    raw = open(path, 'rb').read()
    n, hl, rl = struct.unpack_from('<IHH', raw, 4)
    fields, i = [], 32
    while raw[i] != 0x0D:
        fields.append((raw[i:i + 11].split(b'\0')[0].decode(), raw[i + 16]))
        i += 32
    out = []
    for k in range(n):
        rec = raw[hl + k * rl + 1:hl + (k + 1) * rl]
        d, o = {}, 0
        for name, size in fields:
            d[name] = rec[o:o + size].decode('latin1').strip()
            o += size
        out.append(d)
    return out


def _shp(path):
    """Each record's parts (rings or points), as lists of (x, y)."""
    raw = open(path, 'rb').read()
    i, out = 100, []
    while i + 8 <= len(raw):
        _n, clen = struct.unpack_from('>2i', raw, i)
        rec = raw[i + 8:i + 8 + clen * 2]
        i += 8 + clen * 2
        t = struct.unpack_from('<i', rec)[0]
        if t in (1, 11, 21):
            out.append([[struct.unpack_from('<2d', rec, 4)]])
        elif t in (3, 5, 13, 15, 23, 25):
            nparts, npts = struct.unpack_from('<2i', rec, 36)
            starts = list(struct.unpack_from('<%di' % nparts, rec, 44)) + [npts]
            pts = [struct.unpack_from('<2d', rec, 44 + 4 * nparts + 16 * k) for k in range(npts)]
            out.append([pts[starts[j]:starts[j + 1]] for j in range(nparts)])
        else:
            out.append([])
    return out


def _area(ring):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1])) / 2


def read_fill(folder):
    """{scrap name: polygon} and {station: (x, y)} (station as name@survey)."""
    fill = {}
    for rec, parts in zip(_dbf(os.path.join(folder, 'outline2d.dbf')), _shp(os.path.join(folder, 'outline2d.shp'))):
        rings = [r for r in parts if len(r) > 3]
        outer = [Polygon(r).buffer(0) for r in rings if _area(r) < 0]      # shapefile: outer rings clockwise
        holes = [Polygon(r).buffer(0) for r in rings if _area(r) > 0]
        if not outer:
            outer, holes = holes, []
        g = unary_union(outer)
        if holes:
            g = g.difference(unary_union(holes))
        if not g.is_empty:
            fill[rec['_NAME']] = unary_union([fill[rec['_NAME']], g]) if rec['_NAME'] in fill else g
    stations = {}
    pts = os.path.join(folder, 'points2d.dbf')
    if os.path.exists(pts):
        for rec, parts in zip(_dbf(pts), _shp(os.path.join(folder, 'points2d.shp'))):
            if rec.get('_TYPE') == 'station' and parts and rec.get('_STNAME'):
                stations[f"{rec['_STNAME']}@{rec['_STSURVEY']}"] = parts[0][0]
    return fill, stations


def read_xvi(path):
    """(px a metre, {station: (x, y)}, [(x1, y1, x2, y2)]) in the xvi's own frame (y up)."""
    t = open(path, encoding='utf-8').read()
    num = r'(-?[\d.]+)'
    scale = float(re.search(r'XVIgrid\s+\{\s*\S+\s+\S+\s+(\S+)', t).group(1))
    st_part = t.split('XVIstations', 1)[1].split('XVIshots', 1)[0]
    stations = {m[2]: (float(m[0]), float(m[1]))
                for m in re.findall(r'\{\s*%s\s+%s\s+(\S+?)\s*\}' % (num, num), st_part)}
    sh_part = t.split('XVIshots', 1)[1].split('XVIgrid ', 1)[0]
    shots = [tuple(map(float, m)) for m in re.findall(r'\{\s*%s\s+%s\s+%s\s+%s\s*\}' % (num, num, num, num), sh_part)]
    return scale, stations, shots


def _survey(name):
    """'12@GoSouth.LongwoodValleySink' -> 'GoSouth'."""
    s = name.split('@', 1)[1] if '@' in name else ''
    return s.split('.')[0]


class Report:
    def __init__(self, projection):
        self.projection = projection
        self.shift = None              # median misfit of the stations (m), how well the frames agree
        self.legs_out = []             # (survey, from, to, metres outside, ends outside)
        self.splays_out = []           # (survey, station, metres outside)
        self.undrawn = []              # stations outside the fill (passage not drawn)


def check(folder, xvi, surveys=None, projection='plan'):
    fill, drawn = read_fill(folder)
    scale, xst, shots = read_xvi(xvi)
    common = [n for n in xst if n in drawn]
    r = Report(projection)
    if not common or not fill:
        return r
    dx = statistics.median(drawn[n][0] - xst[n][0] / scale for n in common)
    dy = statistics.median(drawn[n][1] - xst[n][1] / scale for n in common)
    to_m = lambda x, y: (x / scale + dx, y / scale + dy)
    r.shift = statistics.median(math.dist(drawn[n], to_m(*xst[n])) for n in common)
    passage = unary_union(list(fill.values()))
    at = {}
    for n, (x, y) in xst.items():
        at.setdefault((round(x, 2), round(y, 2)), n)
    want = lambda n: surveys is None or _survey(n) in surveys
    outside = {n for n in xst if want(n) and passage.distance(Point(to_m(*xst[n]))) > LEG_OUT}
    r.undrawn = sorted(outside)
    seen = set()
    for x1, y1, x2, y2 in shots:
        a, b = at.get((round(x1, 2), round(y1, 2))), at.get((round(x2, 2), round(y2, 2)))
        if a is None and b is None:
            continue
        if a is not None and b is not None:          # a leg
            if not (want(a) or want(b)) or (a, b) in seen or (b, a) in seen or a == b:
                continue
            seen.add((a, b))
            line = LineString([to_m(x1, y1), to_m(x2, y2)])
            if line.length < 0.05:
                continue
            out = line.difference(passage.buffer(LEG_OUT)).length
            if out > 0.05:
                r.legs_out.append((_survey(a) or _survey(b), a, b, out, (a in outside) + (b in outside)))
        else:                                        # a splay, from the named end
            n, (ex, ey) = (a, (x2, y2)) if a is not None else (b, (x1, y1))
            if not want(n) or n in outside:          # from passage not drawn: nothing to check
                continue
            d = passage.distance(Point(to_m(ex, ey)))
            if d > SPLAY_OUT:
                r.splays_out.append((_survey(n), n, d))
    return r


def run(root, surveys=None, projections=PROJECTIONS):
    out = []
    for p in projections:
        folder, xvi = os.path.join(root, p), os.path.join(root, p + '.xvi')
        if os.path.exists(os.path.join(folder, 'outline2d.shp')) and os.path.exists(xvi):
            out.append(check(folder, xvi, surveys, p))
    return out


def short(n):
    return n.split('.')[0]


def text(reports):
    o = []
    for r in reports:
        o.append(f"== {r.projection}" + (f" (stations agree within {r.shift:.2f} m)" if r.shift is not None else
                                        " (no stations in common: not checked)"))
        bad = [x for x in r.legs_out if x[4] == 0]
        ends = [x for x in r.legs_out if x[4] > 0]
        o.append(f"  legs outside the fill, both stations inside: {len(bad)}")
        o += [f"    {short(a)} - {short(b)}: {m:.1f} m outside" for _, a, b, m, _ in sorted(bad, key=lambda x: -x[3])]
        o.append(f"  legs out of the fill at a station outside it (passage not drawn yet?): {len(ends)}")
        o += [f"    {short(a)} - {short(b)}: {m:.1f} m" for _, a, b, m, _ in sorted(ends, key=lambda x: (x[0], x[1]))]
        o.append(f"  splay ends more than {SPLAY_OUT} m outside the fill, to check: {len(r.splays_out)}")
        o += [f"    from {short(n)}: {d:.1f} m" for _, n, d in sorted(r.splays_out, key=lambda x: -x[2])]
    return '\n'.join(o)


def build(cfg, log):
    """Run Therion on the whole-cave check build: (return code, problems in its log)."""
    import subprocess
    os.makedirs(os.path.dirname(log), exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(log), 'check'), exist_ok=True)
    rc = subprocess.run(['therion', '-l', os.path.abspath(log), os.path.basename(cfg)],
                        cwd=os.path.dirname(cfg), capture_output=True).returncode
    lines = open(log, encoding='utf-8', errors='replace').read().splitlines() if os.path.exists(log) else []
    bad = sorted({l.strip() for l in lines if l.startswith('therion: error') or 'invalid scrap outline' in l
                  or 'intersects itself' in l})
    return rc, bad


def main(argv):
    import argparse
    from .project import load, REPO
    p = argparse.ArgumentParser(prog='python3 -m tools.sketch2therion fillcheck')
    p.add_argument('--build', action='store_true', help="run the cave's whole-cave check build first")
    p.add_argument('--survey', nargs='+', help='only these surveys (default: all)')
    p.add_argument('--projection', nargs='+', choices=PROJECTIONS, default=list(PROJECTIONS))
    a = p.parse_args(argv)
    root = os.path.join(REPO, 'output', 'check')
    o = []
    if a.build:
        cfg = os.path.join(REPO, load().cave.get('check_build', 'LongwoodValleySink/Whole_cave.thcfg'))
        rc, bad = build(cfg, os.path.join(REPO, 'output', 'whole-cave.log'))
        o.append(f"whole-cave build ({os.path.relpath(cfg, REPO)}): therion returned {rc}, "
                 f"{len(bad)} errors or warnings (output/whole-cave.log)")
        o += ['  ' + b for b in bad]
    o.append(text(run(root, set(a.survey) if a.survey else None, a.projection)))
    report = '\n'.join(o)
    print(report)
    with open(os.path.join(root, 'fillcheck.txt'), 'w', encoding='utf-8') as f:
        f.write(report + '\n')
