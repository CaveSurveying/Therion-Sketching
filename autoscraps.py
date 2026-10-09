# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see tools/LICENSE.
"""Scraps chosen from Therion's 3D model of the survey (Style.md, Scraps).

Passages drawn over one another in a view go in separate scraps. Which
legs' passages overlap is read from the model Loch shows: each wall
triangle goes with its nearest leg and is seen in the view (from above
for a plan; for an extended elevation along the leg as Therion lays it
out, height up; facing the angle for a projected elevation). Two legs
that don't meet at a station and whose passages overlap by more than
OVERLAP of the smaller are a clash.

The scraps start as one and are cut until no scrap holds a clash:

- a cut is a leg between two scraps (in neither: scraps.py). In a plan
  it is on a simple, linear part of the passage, both its stations with
  only two legs, never at a junction (a hard rule); near a junction a leg
  or more down one of the passages. In an elevation it is near a junction
  most of the time, on a short piece of passage by it (WestPassage 57 to
  59), maybe on it (a rule still being developed);
- of the places that part a clash, the one leaving the two scraps most
  alike in length is taken (two medium scraps are better than a short
  one and a very long one);
- every scrap keeps at least two stations (one leg).

The order matters: plan scraps come from the model built from the
splays, before the plans are drawn; elevation scraps wait for the plans,
from the model built from the drawn plans (`-wall-source maps`) taken
together with the one from the splays (each leg's passage the union of
the two: the drawn plan is narrower where the splays reach further).

    python3 -m tools.sketch2therion scraps X [--view plan|extended|315] [--from splays|maps]
"""
import math
import os
import subprocess
import sys
import tempfile
from collections import defaultdict

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

OVERLAP = 0.7        # of the smaller passage: more is a clash (`scraps --calibrate`, log row 135)
MIN_AREA = 0.3       # m2: and at least this much
AREA_ALONE = 2.0     # m2: in an extended elevation, or this much whatever share of the smaller it is
                     # (TritonSouth, log row 137; the older 315 drawings keep larger overlaps in one scrap)
REACH = 8.0          # m: a wall triangle further than this from every leg is left out


def _seg_dist3(p, a, b):
    ab = [b[i] - a[i] for i in range(3)]
    ap = [p[i] - a[i] for i in range(3)]
    L = sum(v * v for v in ab)
    t = 0.0 if L < 1e-12 else max(0.0, min(1.0, sum(ap[i] * ab[i] for i in range(3)) / L))
    q = [a[i] + t * ab[i] for i in range(3)]
    return math.dist(p, q), t


def model(th, source='splays'):
    """The Loch model of a survey alone, its walls from the splays or from the drawn plans."""
    from . import loch
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, 'm.lox')
        with open(os.path.join(tmp, 'm.thcfg'), 'w', encoding='utf-8') as f:
            f.write(f"encoding  utf-8\nsource {os.path.abspath(th)}\n"
                    f"export model -fmt loch -enable walls -wall-source {source} -o m.lox\n")
        subprocess.run(['therion', '-l', 'm.log', 'm.thcfg'], cwd=tmp, capture_output=True)
        if not os.path.exists(out):
            raise RuntimeError(f"therion made no model of {th}")
        return loch.read(out)


def extended_positions(th, survey):
    """{station: (x, y)} in metres, as Therion lays the survey alone out in extended elevation."""
    from .register import Layout
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, 'e.xvi')
        with open(os.path.join(tmp, 'm.th'), 'w', encoding='utf-8') as f:
            f.write(f"encoding  utf-8\nmap ExtendedCentreline -projection extended\n  {survey}\nendmap\n")
        with open(os.path.join(tmp, 'p.thcfg'), 'w', encoding='utf-8') as f:
            f.write(f"encoding  utf-8\nsource {os.path.abspath(th)}\nsource m.th\nselect ExtendedCentreline\n"
                    f"export map -projection extended -fmt xvi -o {out}\n")
        subprocess.run(['therion', '-l', 'p.log', 'p.thcfg'], cwd=tmp, capture_output=True)
        if not os.path.exists(out):
            raise RuntimeError(f"therion made no extended layout of {th}")
        lay = Layout(out)
        return {n: ps[0] for (n, sv), ps in lay.by_name.items() if sv in (survey, '') and ps}


ZRANGE = {}          # leg -> (lowest, highest) of its passage, from the last footprints()
SOLID = {}           # leg -> (from, to, radius): the leg in 3D and how far its walls are from it
LEVEL_GAP = 0.0      # m: in plan, passages clash only one above the other, this much rock between (`scraps --calibrate`)
PLAN_OVERLAP = 0.3   # plan: share of the smaller passage (`scraps --calibrate`, from the older plans)
PLAN_MIN_AREA = 0.3  # m2


def footprints(m, view, ext=None):
    """{leg: polygon} of each leg's passage in the view: 'plan', 'extended'
    (ext: the stations' extended positions) or an angle faced."""
    st = m.stations
    legs = sorted({tuple(sorted(l)) for l in m.legs if l[0] in st and l[1] in st and l[0] != l[1]})
    if view == 'extended':
        legs = [l for l in legs if l[0] in ext and l[1] in ext]
    if not legs:
        return {}
    if view == 'plan':
        flat = lambda p, l, t: (p[0], p[1])
    elif view == 'extended':
        def flat(p, l, t):
            a, b = st[l[0]], st[l[1]]
            ea, eb = ext[l[0]], ext[l[1]]
            z = a[2] + t * (b[2] - a[2])
            return (ea[0] + t * (eb[0] - ea[0]), ea[1] + t * (eb[1] - ea[1]) + (p[2] - z))
    else:
        r = math.radians(float(view) + 90)          # the viewer's right
        flat = lambda p, l, t: (p[0] * math.sin(r) + p[1] * math.cos(r), p[2])
    parts = defaultdict(list)
    ZRANGE.clear()
    SOLID.clear()
    reach = defaultdict(list)
    for tri in m.triangles:
        c = [sum(v[i] for v in tri) / 3 for i in range(3)]
        d, l = min((_seg_dist3(c, st[l[0]], st[l[1]])[0], l) for l in legs)
        if d > REACH:
            continue
        reach[l] += [_seg_dist3(v, st[l[0]], st[l[1]])[0] for v in tri]
        lo, hi = ZRANGE.get(l, (1e9, -1e9))
        ZRANGE[l] = (min(lo, *(v[2] for v in tri)), max(hi, *(v[2] for v in tri)))
        g = Polygon([flat(v, l, _seg_dist3(v, st[l[0]], st[l[1]])[1]) for v in tri])
        if g.area > 1e-6:
            parts[l].append(g.buffer(0.02))
    import statistics
    for l in legs:
        SOLID[l] = (st[l[0]], st[l[1]], statistics.median(reach[l]) if reach[l] else 0.5)
    out = {}
    for l in legs:
        if parts[l]:
            out[l] = unary_union(parts[l])
        else:
            out[l] = LineString([flat(st[l[0]], l, 0.0), flat(st[l[1]], l, 1.0)]).buffer(0.3)
    return out


def _seg_seg3(a, b, c, d, n=12):
    """Least distance between two 3D segments (sampled)."""
    return min(_seg_dist3([a[i] + (b[i] - a[i]) * k / n for i in range(3)], c, d)[0] for k in range(n + 1))


ROCK = 1.0           # m: and one leg this much further from the other than its walls (not the same space)
JUNCTION_ROCK = 1.5  # m: two legs from one station, each far end this much further from the other leg than
                     # its walls (Trident 10 to 12 over 10 to 13: 2.8 m, walls 1.0; BoldStep 5 to 7 and 5 to 8,
                     # one passage as the user sees it: 2.4 m, walls 1.0)


def clashes(fp, zr=None, solid=None, alone=None):
    """[(leg, leg, overlap)]: legs not meeting at a station whose passages
    overlap. zr ({leg: (low, high)}, plans): only passages one above the
    other, not the same space seen from two legs."""
    legs = list(fp)
    out = []
    for i, a in enumerate(legs):
        for b in legs[i + 1:]:
            if set(a) & set(b):
                # two legs from one station: in an extended elevation, a branch drawn over the
                # passage it leaves when each goes well away from the other (Trident 10: the
                # ramp to 12 over 10 to 13), at least `alone` m2 of it
                if not (alone and solid and a in solid and b in solid):
                    continue
                (p, q, ra), (u, v, rb) = solid[a], solid[b]
                far_a = q if a[0] in b else p
                far_b = v if b[0] in a else u
                apart = max(ra, rb) + JUNCTION_ROCK
                if _seg_dist3(far_a, u, v)[0] < apart or _seg_dist3(far_b, p, q)[0] < apart:
                    continue
                inter = fp[a].intersection(fp[b]).area
                small = min(fp[a].area, fp[b].area)
                if inter >= alone and inter / max(small, 1e-6) > OVERLAP:
                    out.append((a, b, inter / small))
                continue
            if zr and a in zr and b in zr and not (zr[a][0] > zr[b][1] + LEVEL_GAP or zr[b][0] > zr[a][1] + LEVEL_GAP):
                continue
            if solid and a in solid and b in solid:      # the same space seen from two legs, not one passage behind another
                (p, q, ra), (u, v, rb) = solid[a], solid[b]
                if _seg_seg3(p, q, u, v) < max(ra, rb) + ROCK:     # one leg within the other's passage
                    continue
            inter = fp[a].intersection(fp[b]).area
            small = min(fp[a].area, fp[b].area)
            ov, least = (PLAN_OVERLAP, PLAN_MIN_AREA) if zr is not None else (OVERLAP, MIN_AREA)
            if inter >= least and (inter / max(small, 1e-6) > ov or (alone and inter >= alone)):
                out.append((a, b, inter / small))
    return out


def _components(legs, cut):
    """[[legs] per scrap]. cut: legs in no scrap, or {leg: station}: a leg
    detached at a junction station goes with the passage at its other end
    (a branch: Trident 10 to 12), None for a leg in neither."""
    end = cut if isinstance(cut, dict) else dict.fromkeys(cut)
    adj = defaultdict(set)
    node = lambda l, n: (n, l) if end.get(l) == n else n
    for l in legs:
        if l in end and end[l] is None:
            continue
        adj[node(l, l[0])].add(l)
        adj[node(l, l[1])].add(l)
    seen, comps = set(), []
    for l in legs:
        if (l in end and end[l] is None) or l in seen:
            continue
        comp, todo = [], [l]
        while todo:
            x = todo.pop()
            if x in seen:
                continue
            seen.add(x)
            comp.append(x)
            for n in (node(x, x[0]), node(x, x[1])):
                todo += [y for y in adj[n] if y not in seen]
        comps.append(comp)
    return comps


def _path(legs, a, b, cut):
    """Legs from leg a to leg b, through legs not cut (breadth first)."""
    adj = defaultdict(set)
    for l in legs:
        if l not in cut:
            adj[l[0]].add(l)
            adj[l[1]].add(l)
    prev, todo = {a: None}, [a]
    while todo:
        x = todo.pop(0)
        if x == b:
            break
        for n in x:
            for y in adj[n]:
                if y not in prev:
                    prev[y] = x
                    todo.append(y)
    if b not in prev:
        return []
    out, x = [], b
    while x is not None:
        out.append(x)
        x = prev[x]
    return out[::-1]


def choose(legs, clash, length, degree, view='extended'):
    """The legs to cut so that no scrap holds a clash. legs: [(a, b)];
    clash: [(leg, leg, overlap)]; length: {leg: m}; degree: {station: legs}.
    A leg is cut in neither scrap; in an elevation a leg at a junction is
    detached there instead, going with the passage beyond it (each scrap a
    passage: the branch its own scrap, the passage through the junction
    whole, Trident 10 to 12). Returns ({cut leg: junction or None},
    [[legs] per scrap], clashes left)."""
    cut = {}
    for _ in range(4 * len(legs)):
        comps = _components(legs, cut)
        where = {l: i for i, c in enumerate(comps) for l in c}
        live = [(a, b, o) for a, b, o in clash if a in where and where.get(a) == where.get(b)]
        if not live:
            return cut, comps, []
        comp = comps[where[live[0][0]]]
        mine = [(a, b) for a, b, _ in live if where[a] == where[live[0][0]]]
        best = None
        # the passage through each junction: the two legs leading on to the most
        # passage; a leg off it is a branch
        through = {}
        for n in {n for l in comp for n in l if degree[n] > 2}:
            at = [l for l in comp if n in l and l not in cut]
            sides = _components(comp, {**cut, **{l: n for l in at}})
            of = {x: sum(length[y] for y in p) for p in sides for x in p}
            through[n] = set(sorted(at, key=lambda l: -of.get(l, 0.0))[:2])
        for l in comp:
            if l in cut:
                continue
            simple = degree[l[0]] <= 2 and degree[l[1]] <= 2
            # a leg or more from a junction: the legs either side of it simple too
            nbrs = [x for x in comp if x != l and set(x) & set(l)]
            clear = simple and all(degree[y] <= 2 for x in nbrs for y in x)
            ends = [n for n in l if degree[n] > 2] if view != 'plan' else []
            for j in ends or [None]:
                parts = _components(comp, {**cut, l: j})
                if len(parts) < 2:
                    continue                          # in a loop: cutting it parts nothing
                side = {x: i for i, p in enumerate(parts) for x in p}
                resolved = sum(1 for a, b in mine if side.get(a) is not None and side.get(b) is not None
                               and side[a] != side[b])
                if not resolved:
                    continue
                sizes = sorted(sum(length[x] for x in p) for p in parts)
                balance = sizes[0] / max(sizes[-1], 1e-6)
                if view == 'plan':
                    # plans: on simple passage; a leg by a junction keeps the junction
                    # whole in one scrap, a little back from it (CJS, CrossRoads, CJPitch)
                    score = (simple, clear, resolved, balance)
                else:
                    # elevations: near a junction, most of the time on a short piece of
                    # passage by it (WestPassage 57 to 59), maybe on it; at the junction
                    # the branch goes, the passage through it stays whole
                    near = not simple or not clear
                    branch = j is not None and l not in through.get(j, ())
                    score = (resolved, near, branch, -length[l], balance)
                if best is None or score > best[0]:
                    best = (score, l, j)
        if best is None:
            break
        cut[best[1]] = best[2]
    # cuts that are not needed go, the smallest scraps first: as few scraps as hold no clash
    pairs = {frozenset((a, b)) for a, b, _ in clash}
    changed = True
    while changed:
        changed = False
        comps = _components(legs, cut)
        size = {l: sum(length[x] for x in c) for c in comps for l in c}
        for l in sorted(cut, key=lambda l: min((size.get(x, 0) for x in legs if set(x) & set(l) and x != l),
                                              default=0)):
            trial = {k: v for k, v in cut.items() if k != l}
            merged = _components(legs, trial)
            where = {x: i for i, c in enumerate(merged) for x in c}
            if not any(where.get(a) == where.get(b) for a, b in map(tuple, pairs) if a in where):
                cut, changed = trial, True
                break
    comps = _components(legs, cut)
    where = {l: i for i, c in enumerate(comps) for l in c}
    return cut, comps, [(a, b, o) for a, b, o in clash if a in where and where.get(a) == where.get(b)]


def scraps_for(th, survey, view, source='splays'):
    """(station groups, cut legs, clashes left, clashes) for a survey in a view."""
    fp, length, degree, zr, solid = survey_data(th, survey, view, source)
    legs = list(fp)
    cl = clashes(fp, zr, solid, AREA_ALONE if view == 'extended' else None)
    cut, comps, left = choose(legs, cl, length, degree, view)
    from .register import natural
    groups = []
    for c in comps:
        g = sorted({n for l in c for n in l}, key=natural)
        if len(g) >= 2:
            groups.append(g)
    # a station of a cut leg sits in one scrap only (scraps.py: the cut leg is in neither);
    # a junction a branch is detached at sits in the branch (Trident 10 in 10 to 12)
    where = {l: i for i, c in enumerate(comps) for l in c}
    first = {j: where[l] for l, j in cut.items() if j is not None and l in where}
    order = sorted(range(len(groups)), key=lambda i: -sum(1 for j, k in first.items() if k == i))
    seen = set()
    for g in [groups[i] for i in order]:
        g[:] = [n for n in g if n not in seen]
        seen |= set(g)
    groups = [g for g in groups if len(g) >= 2]
    return groups, sorted(cut), left, cl


def leg_scrap(groups, legs):
    """{leg: scrap index} for legs with both stations in one scrap (a
    station shared at a join may be in two)."""
    member = defaultdict(set)
    for i, g in enumerate(groups):
        for n in g:
            member[n].add(i)
    out = {}
    for a, b in legs:
        both = member[a] & member[b]
        if both:
            out[(a, b)] = min(both)
    return out


SHORT = 0.25         # a scrap under this share of its neighbour's length beside it is short


def check_split(groups, fp, length, degree, zr=None, solid=None, view='extended'):
    """A split judged by the rules (Style.md, Scraps), not by matching
    another: more than one can be right. Returns [(rule, detail)]: an
    empty list keeps them all."""
    legs = list(fp)
    where = leg_scrap(groups, legs)
    out = []
    for a, b, o in clashes(fp, zr, solid):
        if a in where and where.get(a) == where.get(b):
            out.append(('overlap', f"{a[0]}-{a[1]} over {b[0]}-{b[1]} ({o:.0%}) in one scrap"))
    drawn = {n for g in groups for n in g}
    at = defaultdict(list)
    for l in legs:
        if l[0] not in drawn or l[1] not in drawn:
            continue                             # to a station no scrap draws: not a join
        for n in l:
            at[n].append(where.get(l))           # None: a leg between scraps, in neither
    for n, sc in at.items():                     # scraps meet at a station whose legs are in different scraps
        # a leg cut by the junction (None: in neither) keeps the junction whole in one scrap
        # (CJPitch, CJS, CrossRoads); elevations: joins by junctions are usual
        if view == 'plan' and degree[n] > 2 and len(set(sc) - {None}) > 1:
            out.append(('junction', f"scraps meet at {n}, a junction"))
    size = defaultdict(float)
    for l, i in where.items():
        size[i] += length.get(l, 0.0)
    for i, g in enumerate(groups):
        if len(g) < 2:
            out.append(('stations', f"scrap {i + 1} has {len(g)} station"))
    nbr = {(where[x], where[y]) for x in where for y in where
           if where[x] != where[y] and set(x) & set(y)}
    for i, j in nbr:
        if size[i] < SHORT * size[j] and size[i] < 10.0:
            out.append(('short', f"scrap {i + 1} ({size[i]:.0f} m) beside scrap {j + 1} ({size[j]:.0f} m)"))
    return sorted(set(out))


def survey_data(th, survey, view, source):
    """(footprints, lengths, degrees, height ranges) of a survey's legs in a view."""
    ext = extended_positions(th, survey) if view == 'extended' else None
    fp, zr, st, solid = {}, {}, {}, {}
    for src in (('splays', 'maps') if source == 'both' else (source,)):
        try:
            m = model(th, src)
        except RuntimeError:
            continue
        st = st or m.stations
        for l, g in footprints(m, view, ext).items():
            fp[l] = fp[l].union(g) if l in fp else g
        for l, (p, q, r) in SOLID.items():
            solid[l] = (p, q, max(r, solid.get(l, (p, q, 0.0))[2]))
        for l, (lo, hi) in ZRANGE.items():
            zr[l] = (min(lo, zr.get(l, (lo, hi))[0]), max(hi, zr.get(l, (lo, hi))[1]))
    length = {l: math.dist(st[l[0]], st[l[1]]) for l in fp}
    degree = defaultdict(int)
    for l in fp:
        degree[l[0]] += 1
        degree[l[1]] += 1
    return fp, length, degree, (zr if view == 'plan' else None), solid


NEW = ('GoSouth', 'Trident', 'TridentCentre', 'TridentLeft', 'IDontCare', 'BoldStep', 'TritonNorth',
       'TritonSouth', 'Connection', 'FairyChimneys', 'GoWest', 'TickleRift')   # 2026, or not built: not examples
REFERENCES = ('CJPitch', 'CrossRoads', 'WestPassage', 'Century', 'RoundTheBend', 'CrystalPitch',
              'TickleWest', 'NorthRift', 'Cyclops')    # older surveys with 315 scraps drawn by hand


def references(proj):
    """[(survey, view, station groups)]: splits made by hand, each one right:
    the pre-2026 315 drawings and plans."""
    import re
    from . import scraps as by_hand
    out = []
    for x in REFERENCES:
        path = os.path.join(os.path.dirname(proj.path(proj.survey_file(x))), f"{x}E315.th2")
        if os.path.exists(path):
            t = open(path, encoding='utf-8', errors='replace').read()
            g = [sorted(set(re.findall(r'station -name (\S+)', m.group(2))))
                 for m in re.finditer(r'(?ms)^scrap (\S+)[^\n]*\n(.*?)^endscrap', t)]
            out.append((x, '315', [h for h in g if h]))
    root = os.path.dirname(proj.path(proj.cave['master']))
    for x in sorted(os.listdir(root)):
        if x in NEW or not os.path.isdir(os.path.join(root, x)):
            continue
        for name in (f"{x}.plan.th2", f"{x}P.th2") + tuple(f for f in os.listdir(os.path.join(root, x))
                                                           if f.endswith('.plan.th2')):
            path = os.path.join(root, x, name)
            if os.path.exists(path):
                t = open(path, encoding='utf-8', errors='replace').read()
                g = [sorted(set(re.findall(r'station -name (\S+)', m.group(2))))
                     for m in re.finditer(r'(?ms)^scrap (\S+) [^\n]*-projection plan[^\n]*\n(.*?)^endscrap', t)]
                g = [h for h in g if len(h) >= 2]
                if g:
                    out.append((x, 'plan', g))
                break
    return out          # the 2026 splits ([scraps], [scraps_extended]) are ours, not examples


def _set(view, a, b, c):
    global OVERLAP, MIN_AREA, ROCK, PLAN_OVERLAP, PLAN_MIN_AREA, LEVEL_GAP
    if view == 'plan':
        PLAN_OVERLAP, PLAN_MIN_AREA, LEVEL_GAP = a, b, c
    else:
        OVERLAP, MIN_AREA, ROCK = a, b, c


GRIDS = {'plan': ((0.3, 0.5, 0.7, 0.9), (0.3, 1.0, 2.0, 4.0), (0.0, 0.5, 1.0, 2.0)),
         'elevation': ((0.2, 0.3, 0.4, 0.5, 0.7), (0.3, 0.5, 1.0, 2.0, 3.0), (0.0, 0.25, 0.5, 1.0))}


def calibrate(proj, grids=GRIDS):
    """Thresholds from the splits made by hand, plans and elevations apart
    (more than one split can be right: each of these is one): the fewest
    hand scraps holding a clash, then the most hand splits explained (a
    clash across them), then the most sensitive. Returns ({kind: (a, b,
    c)}, [(survey, view, scraps by hand, findings, our scraps, findings)])."""
    from . import scraps as by_hand
    data = []
    for x, view, hand in references(proj):
        th = proj.path(proj.survey_file(x))
        try:
            fp, length, degree, zr, solid = survey_data(th, x, view, 'splays' if view == 'plan' else 'both')
        except RuntimeError:
            continue
        if not fp:
            continue
        names = sorted({n for l in fp for n in l})
        if hand and isinstance(hand[0], str):
            hand = by_hand.parse(hand, names)
        data.append((x, view, hand, fp, length, degree, zr, solid))
    best = {}
    for kind in ('plan', 'elevation'):
        mine = [d for d in data if (d[1] == 'plan') == (kind == 'plan')]
        tried = []
        for a in grids[kind][0]:
            for b in grids[kind][1]:
                for c in grids[kind][2]:
                    _set(kind, a, b, c)
                    bad = sum(1 for d in mine for r, _ in check_split(d[2], *d[3:], view=d[1]) if r == 'overlap')
                    explained = 0
                    for x, view, hand, fp, length, degree, zr, solid in mine:
                        if len(hand) < 2:
                            continue
                        where = leg_scrap(hand, list(fp))
                        if any(p in where and q in where and where[p] != where[q] for p, q, _ in clashes(fp, zr, solid)):
                            explained += 1
                    tried.append((bad, -explained, a, b, c))
        _, _, *t = min(tried)
        best[kind] = tuple(t)
        _set(kind, *t)
    report = []
    for x, view, hand, fp, length, degree, zr, solid in data:
        legs = list(fp)
        cut, comps, left = choose(legs, clashes(fp, zr, solid), length, degree, view)
        ours = [sorted({n for l in c for n in l}) for c in comps]
        report.append((x, view, len(hand), check_split(hand, fp, length, degree, zr, solid, view),
                       len(ours), check_split(ours, fp, length, degree, zr, solid, view)))
    return best, report


def specs(groups):
    """Station lists as [scraps] specs."""
    return [", ".join(g) for g in groups]


def main(argv):
    import argparse
    from ..project import load
    p = argparse.ArgumentParser(prog='python3 -m tools.sketch2therion scraps')
    p.add_argument('survey', nargs='*')
    p.add_argument('--calibrate', action='store_true',
                   help='thresholds from the splits made by hand, and every split checked by the rules')
    p.add_argument('--view', default='extended', help="plan, extended or an angle faced (315)")
    p.add_argument('--from', dest='source', default=None, choices=('splays', 'maps', 'both'),
                   help='walls of the model (default: splays for a plan; for elevations both the drawn plans and the splays)')
    a = p.parse_args(argv)
    proj = load()
    if a.calibrate:
        best, report = calibrate(proj)
        a, b, c = best['plan']
        print(f"plan thresholds from the hand splits: overlap {a}, area {b} m2, rock between levels {c} m")
        a, b, c = best['elevation']
        print(f"elevation thresholds from the hand splits: overlap {a}, area {b} m2, rock {c} m")
        for x, view, nh, fh, no, fo in report:
            print(f"  {x} {view}: hand {nh} scraps, " + (", ".join(sorted({r for r, _ in fh})) or "keeps the rules")
                  + f"; ours {no} scraps, " + (", ".join(sorted({r for r, _ in fo})) or "keeps the rules"))
        return
    for s in a.survey:
        th = proj.path(proj.survey_file(s))
        src = a.source or ('splays' if a.view == 'plan' else 'both')
        groups, cut, left, cl = scraps_for(th, s, a.view, src)
        print(f"{s} ({a.view}, model from {src}): {len(cl)} clashes, {len(groups)} scraps: "
              + " | ".join(specs(groups)))
        if cut:
            print("  cut at legs " + ", ".join(f"{x}-{y}" for x, y in cut))
        for x, y, o in left:
            print(f"  clash left: {x[0]}-{x[1]} over {y[0]}-{y[1]} ({o:.0%})", file=sys.stderr)
