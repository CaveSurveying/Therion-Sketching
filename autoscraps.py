# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
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
    """{station: [(x, y), ...]} in metres, as the extended elevation was
    sketched (SexyTopo, Notes/<survey>E.xvi or EE/Ee): the drawing as it was
    drawn decides what overlaps, not Therion's layout, which the `extend`
    lines tune for the final output (user, 2026-10-11). A station sketched
    in more than one place has each."""
    import re
    from . import xvi
    notes = os.path.join(os.path.dirname(os.path.abspath(th)), 'Notes')
    names = sorted(f for f in os.listdir(notes) if re.match(rf'^{re.escape(survey)}E[Ee]?\.xvi$', f)) \
        if os.path.isdir(notes) else []
    if not names:
        raise RuntimeError(f"no extended elevation sketch for {survey} in {notes}")
    sk = xvi.read(os.path.join(notes, names[0]))
    return {n.split('@')[0]: list(dict.fromkeys((round(x, 3), round(y, 3)) for x, y in ps))
            for n, ps in sk.stations.items() if ps}


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
        # each leg between the places of its stations (one sketched twice) as far apart across
        # the page as the leg's horizontal length
        def horiz(l):
            a, b = st[l[0]], st[l[1]]
            return math.hypot(b[0] - a[0], b[1] - a[1])
        at = {l: min(((p, q) for p in ext[l[0]] for q in ext[l[1]]),
                     key=lambda pq: (round(abs(abs(pq[1][0] - pq[0][0]) - horiz(l)), 2), math.dist(*pq)))
              for l in legs}

        def flat(p, l, t):
            a, b = st[l[0]], st[l[1]]
            ea, eb = at[l]
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


def _branch(legs, degree, j, l):
    """The legs of the passage leaving junction j by leg l, on to the next
    junctions or its end."""
    out, todo, seen = [], [(l, j)], set()
    while todo:
        x, frm = todo.pop()
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
        n = x[0] if x[1] == frm else x[1]
        if degree[n] <= 2:
            todo += [(y, n) for y in legs if n in y and y != x]
    return out


def branch_clashes(fp, solid, alone):
    """[(leg, leg, overlap)]: in an extended elevation, two ways from one
    junction whose passages, each on to the next junction, are drawn over
    one another (`alone` m2 or more of the drawing) though they are
    different passages: each reaches more than JUNCTION_ROCK beyond the
    other's walls (FairyChimneys 9 to 12 over 8 to 9, 16 to 21 over 9 to
    16; the first legs alone overlap too little)."""
    legs = list(fp)
    degree = defaultdict(int)
    for l in legs:
        degree[l[0]] += 1
        degree[l[1]] += 1
    out = []
    for j in sorted(n for n in degree if degree[n] > 2):
        at = [l for l in legs if j in l]
        br = {l: _branch(legs, degree, j, l) for l in at}
        def beyond(a, b):
            far = 0.0
            for x in br[a]:
                for n, pt in zip(x, solid[x][:2]):
                    if n != j:
                        far = max(far, min(_seg_dist3(pt, solid[y][0], solid[y][1])[0] - solid[y][2] for y in br[b]))
            return far
        for i, a in enumerate(at):
            for b in at[i + 1:]:
                if not all(x in solid for x in br[a] + br[b]):
                    continue
                ua, ub = unary_union([fp[x] for x in br[a]]), unary_union([fp[x] for x in br[b]])
                inter = ua.intersection(ub).area
                if inter >= alone and beyond(a, b) > JUNCTION_ROCK and beyond(b, a) > JUNCTION_ROCK:
                    out.append((a, b, inter / max(min(ua.area, ub.area), 1e-6)))
    return out


def clashes(fp, zr=None, solid=None, alone=None):
    """[(leg, leg, overlap)]: legs not meeting at a station whose passages
    overlap. zr ({leg: (low, high)}, plans): only passages one above the
    other, not the same space seen from two legs. In an extended elevation
    (alone given) also two ways from a junction drawn over one another
    (branch_clashes)."""
    legs = list(fp)
    out = []
    if alone and solid:
        out += branch_clashes(fp, solid, alone)
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
                if inter >= alone and inter / max(small, 1e-6) > OVERLAP and \
                        not any({a, b} == {x, y} for x, y, _ in out):
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


MAX_SCRAP = 150.0    # m of legs: no scrap longer (user, a starting figure; mean length otherwise as long as can be)
STUB = 5.0           # m: a dead-end branch this long or less is its own scrap (Trident 10 to 12: 3.3 m;
                     # FairyChimneys 9 to 12: 4.2 m); a longer one, the scrap coming in ends at the junction


def incoming(legs, start):
    """{station: leg}: the leg by which each station is reached from the
    start (the way the extended elevation is laid out from)."""
    adj = defaultdict(list)
    for l in legs:
        adj[l[0]].append(l)
        adj[l[1]].append(l)
    if start not in adj:
        start = legs[0][0] if legs else start
    came, todo = {start: None}, [start]
    while todo:
        n = todo.pop(0)
        for l in adj[n]:
            m = l[1] if l[0] == n else l[0]
            if m not in came:
                came[m] = l
                todo.append(m)
    return came


def choose(legs, clash, length, degree, view='extended', start=None):
    """The legs to cut so that no scrap holds a clash. legs: [(a, b)];
    clash: [(leg, leg, overlap)]; length: {leg: m}; degree: {station: legs};
    start: the station the survey is laid out from.
    A leg is cut in neither scrap; in an elevation a leg at a junction is
    detached there instead, going with the passage beyond it (each scrap a
    passage). Of two ways from a junction drawn over one another, a short
    dead-end branch goes (its own scrap: Trident 10 to 12); otherwise the
    scrap coming in ends there and a new one carries on from the junction
    with the other ways (FairyChimneys 16, the user's way). Returns ({cut
    leg: junction or None}, [[legs] per scrap], clashes left)."""
    came = incoming(legs, start)
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
        through, goes = {}, {}
        for n in {n for l in comp for n in l if degree[n] > 2}:
            at = [l for l in comp if n in l and l not in cut]
            sides = _components(comp, {**cut, **{l: n for l in at}})
            of = {x: sum(length[y] for y in p) for p in sides for x in p}
            through[n] = set(sorted(at, key=lambda l: -of.get(l, 0.0))[:2])
            # the way to detach at a junction where two of its ways clash: a short dead
            # end, or else the way coming in (that scrap ends; the next starts here)
            pair = {x for a, b in mine if n in a and n in b for x in (a, b)}
            if pair:
                dead = {l for l in pair if not any(degree[y] > 2 for p in sides if l in p
                                                   for x in p for y in x if y != n)}
                stub = {l for l in dead if of.get(l, 0.0) <= STUB}
                stub = {min(stub, key=lambda l: of.get(l, 0.0))} if stub else stub     # the shorter goes
                goes[n] = stub or ({came.get(n)} & pair) or set(at) - through[n]
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
                    branch = j is not None and (l in goes[j] if j in goes else l not in through.get(j, ()))
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


def start_station(th):
    """The station a survey's extended elevation is laid out from: its
    `extend start`, or the first station of its first leg."""
    import re
    try:
        text = open(th, encoding='utf-8').read()
    except OSError:
        return None
    m = re.search(r'(?m)^\s*extend\s+start\s+(\S+)', text)
    return m.group(1) if m else None


PAIR_TURN = 90.0     # degrees: two ways at a junction turning less than this (in 3D) are one passage through it
PASSAGE_AREA = 2.0   # m2: two passages drawn over one another this much (and apart in 3D) clash
PASSAGE_ROCK = 0.8   # m: legs of two passages this much further apart than their walls are in different spaces
                     # (FairyChimneys 11 to 12 over 8 to 9: 0.97 m beyond its walls)
LEG_TOUCH = 0.01     # m2: a leg of a branch touching the other passage this much (away from the junction)
                     # is part of its overlap: only legs clear of it go with the passage left (Connection 4 to 6:
                     # 0; FairyChimneys 16 to 18 touch the crawl, 0.05 m2 each, its walls doubling theirs)


def _unit(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def pair_ways(legs, pos, degree):
    """{junction: [(leg, leg)]}: at each junction its ways paired into passages
    running through it, the straightest first (3D), each turning less than
    PAIR_TURN (Trident 10: 9 to 10 to 12 and 11 to 10 to 13; 15: 17 to 15 to
    16, the passage from 14 turning there). Straight on is the default: which
    passage carries on from which is not always the straightest (user)."""
    import itertools
    out = {}
    for j in sorted(n for n in degree if degree[n] > 2):
        at = [l for l in legs if j in l]

        def way(l):
            o = l[1] if l[0] == j else l[0]
            return _unit([pos[o][i] - pos[j][i] for i in range(3)])
        cand = []
        for a, b in itertools.combinations(at, 2):
            u, v = way(a), way(b)
            turn = math.degrees(math.acos(max(-1.0, min(1.0, -sum(u[i] * v[i] for i in range(3))))))
            if turn < PAIR_TURN:
                cand.append((turn, a, b))
        used, pairs = set(), []
        for _, a, b in sorted(cand):
            if a not in used and b not in used:
                pairs.append((a, b))
                used |= {a, b}
        out[j] = pairs
    return out


def passages(legs, pairs, degree):
    """[[legs] in order along it]: the legs chained through stations with two
    legs and through the paired ways at junctions."""
    link = defaultdict(set)
    for a in legs:
        for b in legs:
            if a < b and set(a) & set(b) and degree[next(iter(set(a) & set(b)))] == 2:
                link[a].add(b)
                link[b].add(a)
    for ps in pairs.values():
        for a, b in ps:
            link[a].add(b)
            link[b].add(a)
    seen, out = set(), []
    for l in legs:
        if l in seen:
            continue
        comp, todo = set(), [l]
        while todo:
            x = todo.pop()
            if x not in comp:
                comp.add(x)
                todo += list(link[x])
        # in order from an end (a loop from anywhere)
        first = next((x for x in sorted(comp) if len(link[x]) < 2), sorted(comp)[0])
        chain = [first]
        while True:
            nxt = [x for x in link[chain[-1]] if x not in chain]
            if not nxt:
                break
            chain.append(nxt[0])
        chain += [x for x in sorted(comp) if x not in chain]
        seen |= comp
        out.append(chain)
    return out


def passage_split(legs, fp, length, degree, solid, start=None):
    """Scraps for an extended elevation as passages (Style.md, Scraps; log row
    150): the ways at each junction paired into passages through it; a passage
    drawn over itself cut as before (choose); a branch whose overlap with the
    passage it leaves starts further along split at its first overlapping leg
    (Connection 5 to 6); then neighbouring passages merged, the longest first,
    while no two in a scrap clash and none is over MAX_SCRAP. Returns
    ([[legs] per scrap], [(leg, leg, overlap)] clashes between passages)."""
    pos = {}
    for l in legs:
        if l in solid:
            pos[l[0]], pos[l[1]] = solid[l][0], solid[l][1]
    legs = [l for l in legs if l[0] in pos and l[1] in pos]
    pairs = pair_ways(legs, pos, degree)
    units = passages(legs, pairs, degree)
    # a passage drawn over itself: cut by the leg rules
    within = clashes({l: fp[l] for l in legs}, None, solid, AREA_ALONE)
    pieces = []
    for u in units:
        mine = [(a, b, o) for a, b, o in within if a in u and b in u]
        if mine:
            sub = defaultdict(int)
            for l in u:
                sub[l[0]] += 1
                sub[l[1]] += 1
            _, comps, _ = choose(u, mine, length, sub, 'extended', start)
            pieces += [[l for l in u if l in c] for c in comps if c]
        else:
            pieces.append(u)
    units = pieces
    shape = lambda u: unary_union([fp[l] for l in u])

    def beyond(u, v):
        """How far u reaches beyond v's walls (3D)."""
        shared = {n for l in u for n in l} & {n for l in v for n in l}
        far = 0.0
        for l in u:
            for n, pt in zip(l, solid[l][:2]):
                if n not in shared:
                    far = max(far, min(_seg_dist3(pt, solid[y][0], solid[y][1])[0] - solid[y][2] for y in v))
        return far

    apart = {}

    def far(a, b):
        """Legs a and b in different spaces: each beyond the other's walls (3D)."""
        k = (a, b) if a < b else (b, a)
        if k not in apart:
            (p, q, ra), (x, y, rb) = solid[a], solid[b]
            if set(a) & set(b):                  # from one station: each far end beyond the other's walls
                fa = q if a[0] in b else p
                fb = y if b[0] in a else x
                need = max(ra, rb) + JUNCTION_ROCK
                apart[k] = _seg_dist3(fa, x, y)[0] > need and _seg_dist3(fb, p, q)[0] > need
            else:
                apart[k] = _seg_seg3(p, q, x, y) > max(ra, rb) + PASSAGE_ROCK
        return apart[k]

    def clash(u, v):
        # only the overlap of legs in different spaces counts: two legs in one chamber, or
        # the two sides of a small loop, are the same space seen from each (BoldStep 0 to 4
        # over 6 to 5; TritonSouth 12 to 13 to 19 and 12 to 14 to 19)
        bits = [fp[a].intersection(fp[b]) for a in u for b in v if far(a, b)]
        inter = unary_union([g for g in bits if not g.is_empty]).area if bits else 0.0
        # or a passage mostly drawn over the other, as for two legs (FairyChimneys 9 to 12 over
        # 8 to 9: 72%; BoldStep 0 to 4 over 6 to 5, one chamber: 47%; TritonSouth's loop: 41%)
        su, sv = shape(u), shape(v)
        whole = su.intersection(sv).area
        small, big = (u, v) if su.area <= sv.area else (v, u)
        mostly = whole >= MIN_AREA and whole > OVERLAP * min(su.area, sv.area) and beyond(small, big) > JUNCTION_ROCK
        # (and reaching well beyond the other's walls: not a short stub overlapping by the junction,
        # BoldStep 13 to 14, TridentLeft 8 to 9)
        return inter >= PASSAGE_AREA or mostly, max(inter, whole if mostly else 0.0)

    # a branch overlapping only further along: its first legs go with the passage it leaves
    changed = True
    while changed:
        changed = False
        for i, u in enumerate(units):
            for v in units:
                if v is u:
                    continue
                shared = {n for l in u for n in l} & {n for l in v for n in l}
                if not shared or not clash(u, v)[0]:
                    continue
                j = next(iter(shared))
                order = u if j in u[0] else u[::-1] if j in u[-1] else None
                if order is None:
                    continue
                away = [l for l in v if j not in l]        # (by the junction every way overlaps)
                if not away:
                    continue
                sv = shape(away)
                k = next((k for k, l in enumerate(order) if fp[l].intersection(sv).area >= LEG_TOUCH), None)
                # (and only if the rest still clashes on its own: else the branch is judged whole,
                # FairyChimneys 9 to 12, its overlap by the junction)
                if k and k < len(order) and clash(order[k:], v)[0]:
                    units[i:i + 1] = [order[:k], order[k:]]
                    changed = True
                    break
            if changed:
                break
    # merge neighbours, the longest scrap first, while nothing in it clashes
    size = lambda u: sum(length[l] for l in u)
    groups = [[u] for u in units]
    bad = {}

    def ok(a, b):
        for u in a:
            for v in b:
                k = (id(u), id(v))
                if k not in bad:
                    bad[k] = clash(u, v)[0]
                if bad[k]:
                    return False
        return True
    while True:
        best = None
        for i in range(len(groups)):
            si = {n for u in groups[i] for l in u for n in l}
            for j in range(i + 1, len(groups)):
                sj = {n for u in groups[j] for l in u for n in l}
                if not si & sj:
                    continue
                total = sum(size(u) for u in groups[i] + groups[j])
                if total > MAX_SCRAP or not ok(groups[i], groups[j]):
                    continue
                if best is None or total > best[0]:
                    best = (total, i, j)
        if best is None:
            break
        _, i, j = best
        groups[i] += groups[j]
        del groups[j]
    comps = [[l for u in g for l in u] for g in groups]
    found = []
    for a in range(len(units)):
        for b in range(a + 1, len(units)):
            c, inter = clash(units[a], units[b])
            if c:
                found.append((units[a][0], units[b][0], inter))
    return comps, found


def _passage_groups(th, legs, fp, length, degree, solid, start):
    """(station groups, legs between scraps, [], clashes) from passage_split:
    a station in more than one scrap goes in the one with most of its legs
    (on a tie, the one the survey starts in: Trident 10 with 9 to 12; 15 with
    17 to 16)."""
    from .register import natural
    comps, found = passage_split(legs, fp, length, degree, solid, start)
    alias = equates(th)
    first = next((i for i, c in enumerate(comps) if any(start in l for l in c)), 0)
    count = defaultdict(lambda: defaultdict(int))
    for i, c in enumerate(comps):
        for l in c:
            for n in l:
                count[n][i] += 1
    home = {n: max(by, key=lambda i: (by[i], i == first, -i)) for n, by in count.items()}
    for k in range(len(comps)):                  # but every scrap keeps at least two stations
        mine = [n for n in count if k in count[n]]
        if sum(1 for n in mine if home[n] == k) < 2:
            for n in sorted(mine, key=lambda n: -count[n][k]):
                if sum(1 for m in mine if home[m] == k) >= 2:
                    break
                home[n] = k
    groups = [sorted({n for n, i in home.items() if i == k} | {a for a, b in alias.items() if home.get(b) == k},
                     key=natural) for k in range(len(comps))]
    keep = [k for k, g in enumerate(groups) if len(g) >= 2]
    groups = [groups[k] for k in keep]
    where = {n: k for k, g in enumerate(groups) for n in g}
    between = sorted(l for l in legs if where.get(l[0]) != where.get(l[1]))
    return groups, between, [], found


def scraps_for(th, survey, view, source='splays'):
    """(station groups, cut legs, clashes left, clashes) for a survey in a view."""
    fp, length, degree, zr, solid = survey_data(th, survey, view, source)
    legs = list(fp)
    start = start_station(th)
    if view == 'extended':
        return _passage_groups(th, legs, fp, length, degree, solid, start)
    cl = clashes(fp, zr, solid, AREA_ALONE if view == 'extended' else None)
    cut, comps, left = choose(legs, cl, length, degree, view, start)
    # as few scraps as hold no clash (each as long as can be), but none over MAX_SCRAP: a long
    # one is parted as a clash between its two legs furthest apart would be
    extra = []
    for _ in range(len(legs)):
        long_ = [c for c in comps if sum(length[l] for l in c) > MAX_SCRAP]
        if not long_:
            break
        c = long_[0]
        mid = {l: [(solid[l][0][i] + solid[l][1][i]) / 2 for i in range(3)] for l in c if l in solid}
        a, b = max(((x, y) for x in mid for y in mid), key=lambda xy: math.dist(mid[xy[0]], mid[xy[1]]))
        extra.append((a, b, 0.0))
        cut, comps, left = choose(legs, cl + extra, length, degree, view, start)
    from .register import natural
    alias = equates(th)
    groups = [sorted({n for l in c for n in l} | {a for a, b in alias.items() if any(b in l for l in c)},
                     key=natural) for c in comps]
    # a station of a cut leg sits in one scrap only (scraps.py: the cut leg is in neither);
    # a junction a branch is detached at sits in the branch (Trident 10 in 10 to 12); where
    # the scrap coming in ends at it, in the next scrap (FairyChimneys 16)
    where = {l: i for i, c in enumerate(comps) for l in c}
    came = incoming(legs, start)
    first = {}
    for l, j in cut.items():
        if j is None or l not in where:
            continue
        if came.get(j) == l:
            nxt = [where[x] for x in legs if j in x and x != l and x in where and where[x] != where[l]]
            if nxt:
                first[j] = nxt[0]
                continue
        first[j] = where[l]
    for j, k in first.items():
        for i, g in enumerate(groups):
            if i != k and j in g:
                g.remove(j)
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


def equates(th):
    """{station: the one it is equated to} from a survey's `equate` lines
    (a loop closed there: TritonSouth 10 and 18, 13 and 21)."""
    import re
    try:
        text = open(th, encoding='utf-8').read()
    except OSError:
        return {}
    parent = {}

    def find(n):
        while parent.get(n, n) != n:
            n = parent[n]
        return n
    for m in re.finditer(r'(?m)^\s*equate\s+(.+?)\s*(?:#.*)?$', text):
        names = [n for n in m.group(1).split() if '@' not in n and '.' not in n]
        from .register import natural
        names.sort(key=natural)
        for n in names[1:]:
            parent[find(n)] = find(names[0])
    return {n: find(n) for n in parent}


def _merge_equated(fp, length, solid, zr, alias):
    """The legs with equated stations named as one (a leg's two ends the same
    station once equated is dropped)."""
    c = lambda n: alias.get(n, n)
    out = [{}, {}, {}, {} if zr is not None else None]
    for l in fp:
        k = tuple(sorted((c(l[0]), c(l[1]))))
        if k[0] == k[1]:
            continue
        out[0][k] = out[0][k].union(fp[l]) if k in out[0] else fp[l]
        out[1][k] = max(out[1].get(k, 0.0), length.get(l, 0.0))
        if l in solid:
            out[2][k] = solid[l]
        if zr is not None and l in zr:
            lo, hi = zr[l]
            out[3][k] = (min(lo, out[3].get(k, (lo, hi))[0]), max(hi, out[3].get(k, (lo, hi))[1]))
    return out


def survey_data(th, survey, view, source):
    """(footprints, lengths, degrees, height ranges) of a survey's legs in a view
    (equated stations as one: a loop, not two passages over one another)."""
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
    alias = equates(th)
    if alias:
        fp, length, solid, zr = _merge_equated(fp, length, solid, zr, alias)
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


def score(hand, auto):
    """How a split compares with one made by hand: [(hand scrap, best auto
    scrap, stations it lacks, stations it has besides)], each hand scrap
    matched to the automatic scrap sharing most of its stations."""
    out = []
    for i, h in enumerate(hand):
        hs = set(h)
        j = max(range(len(auto)), key=lambda k: (len(hs & set(auto[k])), -len(set(auto[k]) - hs))) if auto else None
        a = set(auto[j]) if j is not None else set()
        out.append((i, j, sorted(hs - a, key=_natural), sorted(a - hs, key=_natural)))
    return out


def _natural(n):
    from .register import natural
    return natural(n)


def score_report(proj, view='extended', surveys=None):
    """Lines comparing the chooser with the user's splits ([scraps] or
    [scraps_extended] in project.toml): the targets the rules learn from
    (log row 150). Different splits that keep the rules may be as good."""
    from . import scraps as by_hand
    table = proj.scraps_extended if view == 'extended' else proj.scraps
    lines = []
    for s in surveys or sorted(table):
        th = proj.path(proj.survey_file(s))
        src = 'splays' if view == 'plan' else 'both'
        auto, cut, left, cl = scraps_for(th, s, view, src)
        legs = [l for l in survey_legs(th)]
        names = sorted({n for l in legs for n in l} | {n for g in auto for n in g}, key=_natural)
        hand = by_hand.complete(by_hand.parse(table[s], names), names, legs)
        rows = score(hand, auto)
        same = all(not lack and not extra for _, _, lack, extra in rows) and len(hand) == len(auto)
        lines.append(f"{s} ({view}): " + ("same as the hand split" if same else
                     f"hand {len(hand)} scraps, ours {len(auto)}"))
        if not same:
            lines.append("  hand: " + " | ".join(specs(hand)))
            lines.append("  ours: " + " | ".join(specs(auto)))
            for i, j, lack, extra in rows:
                if lack or extra:
                    lines.append(f"  hand scrap {i + 1} ~ ours {j + 1 if j is not None else '-'}: "
                                 + (f"lacks {', '.join(lack)}" if lack else "")
                                 + ("; " if lack and extra else "") + (f"has besides {', '.join(extra)}" if extra else ""))
    return lines


def survey_legs(th):
    """[(a, b)] the legs of a survey's centreline (station names as written)."""
    import re
    legs = []
    text = open(th, encoding='utf-8').read()
    for m in re.finditer(r'(?ms)^\s*centreline\b(.*?)^\s*endcentreline', text):
        fields = None
        for line in m.group(1).splitlines():
            w = line.split('#')[0].split()
            if not w:
                continue
            if w[0] == 'data':
                fields = w[2:]
                continue
            if fields and 'from' in fields and 'to' in fields and len(w) >= len(fields):
                a, b = w[fields.index('from')], w[fields.index('to')]
                if a != '-' and b != '-' and a != '.' and b != '.':
                    legs.append((a, b))
    return legs


def main(argv):
    import argparse
    from ..project import load
    p = argparse.ArgumentParser(prog='python3 -m tools.sketch2therion scraps')
    p.add_argument('survey', nargs='*')
    p.add_argument('--calibrate', action='store_true',
                   help='thresholds from the splits made by hand, and every split checked by the rules')
    p.add_argument('--view', default='extended', help="plan, extended or an angle faced (315)")
    p.add_argument('--score', action='store_true',
                   help="compare the chooser with the user's splits in project.toml (all of them, or those named)")
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
    if a.score:
        print("\n".join(score_report(proj, a.view, a.survey or None)))
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
