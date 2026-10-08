# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see tools/LICENSE.
"""Steps, pitches and overhangs read from their notation in the sketch.

Colours are only a hint (and sometimes wrong); the notation decides:

- a line with short ticks along one side is a floor step (`line
  floor-step`), or a pitch (`line pit`) where the elevation sketch shows
  a drop of `pitch_min` metres or more there. The ticks are on the low
  side;
- a dashed line with a tick on each dash is a ceiling step or overhang
  (`line overhang`), the ticks on the overhanging side.

Therion draws the ticks (and the overhang's teeth) on the left of a
line's direction (checked by a test render), so each line is written
with the sketch's ticks on its left. Strokes used as ticks and dashes
are consumed: they become nothing else. Hand-drawn notation is messy,
so the tests are loose; check the result in the review.
"""
import math

from shapely.geometry import LineString, Point

TICK_MAX = 0.45      # m: a tick is at most this long
TICK_MIN = 0.06
LINE_MIN = 0.6       # m: a ticked line is at least this long
TOUCH = 0.15         # m: a tick's end is this close to its line
MIN_TICKS = 2
DASH_MIN, DASH_MAX = 0.08, 0.5
DASH_GAP = 0.55      # m: dashes of one line are at most this far apart
MIN_DASHES = 3
JOIN = 1.2           # m: overhang pieces with ends this close are one overhang
SKIP = ('BLUE', 'GREEN', 'RED', 'ORANGE', 'PURPLE')


def length(pp):
    return sum(math.dist(a, b) for a, b in zip(pp, pp[1:]))


def _axis(pp):
    """Unit vector from the first to the last point (or along the longest chord)."""
    a, b = pp[0], pp[-1]
    d = math.dist(a, b)
    if d < 1e-9:
        return (1.0, 0.0)
    return ((b[0] - a[0]) / d, (b[1] - a[1]) / d)


def _angle(u, v):
    """0 to 90 degrees between two directions, either way along."""
    c = abs(u[0] * v[0] + u[1] * v[1])
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def _local_dir(line, d):
    a = line.interpolate(max(0.0, d - 0.15))
    b = line.interpolate(min(line.length, d + 0.15))
    return _axis([(a.x, a.y), (b.x, b.y)])


def _is_short(pp, lo, hi):
    L = length(pp)
    return lo <= L <= hi and math.dist(pp[0], pp[-1]) >= 0.6 * L


def ticks_of(line_pp, shorts):
    """[(index into shorts, side +1 left / -1 right)] of strokes ticking this line."""
    line = LineString(line_pp)
    out = []
    for i, pp in shorts:
        ends = [Point(pp[0]), Point(pp[-1])]
        dist = [line.distance(e) for e in ends]
        k = 0 if dist[0] <= dist[1] else 1
        if dist[k] > TOUCH or dist[1 - k] < dist[k] + 0.04:
            continue
        att, free = (pp[0], pp[-1]) if k == 0 else (pp[-1], pp[0])
        ld = _local_dir(line, line.project(Point(att)))
        td = _axis([att, free])
        if _angle(ld, td) < 45:
            continue
        side = 1 if ld[0] * td[1] - ld[1] * td[0] > 0 else -1
        out.append((i, side))
    return out


def dash_chains(cands):
    """Groups (lists of indices, in order) of short straight strokes in a row."""
    idx = [i for i, _ in cands]
    pp_of = dict(cands)
    link = {i: set() for i in idx}
    for a in idx:
        for b in idx:
            if b <= a:
                continue
            pa, pb = pp_of[a], pp_of[b]
            ua, ub = _axis(pa), _axis(pb)
            if _angle(ua, ub) > 30:
                continue
            ends = min(((p, q) for p in (pa[0], pa[-1]) for q in (pb[0], pb[-1])), key=lambda pq: math.dist(*pq))
            gap = math.dist(*ends)
            if gap > DASH_GAP or gap < 0.02:
                continue
            ca = ((pa[0][0] + pa[-1][0]) / 2, (pa[0][1] + pa[-1][1]) / 2)
            cb = ((pb[0][0] + pb[-1][0]) / 2, (pb[0][1] + pb[-1][1]) / 2)
            if _angle(ua, _axis([ca, cb])) > 25:
                continue
            link[a].add(b)
            link[b].add(a)
    seen, chains = set(), []
    for i in idx:
        if i in seen:
            continue
        comp, todo = [], [i]
        while todo:
            k = todo.pop()
            if k in seen:
                continue
            seen.add(k)
            comp.append(k)
            todo += list(link[k])
        if len(comp) >= MIN_DASHES:
            u = _axis(pp_of[comp[0]])
            comp.sort(key=lambda k: pp_of[k][0][0] * u[0] + pp_of[k][0][1] * u[1])
            chains.append(comp)
    return chains


def _oriented(pts, side):
    """Points ordered so that `side` (+1 left, -1 right of the order) is left."""
    return pts if side > 0 else pts[::-1]


def find(lines):
    """Notation in the sketch lines [(colour, points)], in metres.

    Returns (features [(kind, points, colour)], consumed {indices into lines}),
    kind 'step' (floor step or pitch, decided later) or 'overhang'."""
    usable = [(i, pp) for i, (c, pp) in enumerate(lines) if c not in SKIP and len(pp) > 1]
    longs = [(i, pp) for i, pp in usable if length(pp) >= LINE_MIN]
    shorts = [(i, pp) for i, pp in usable if _is_short(pp, TICK_MIN, TICK_MAX)]
    feats, used = [], set()
    # dashed lines with a tick on each dash (first, so their ticks are
    # not taken for the ticks of a nearby line)
    cands = [(i, pp) for i, pp in usable if _is_short(pp, DASH_MIN, DASH_MAX)]
    pp_all = dict(usable)
    pieces = []                          # [points in order, tick indices]
    for chain in dash_chains(cands):
        pts = []
        for k in chain:
            pts += [pp_all[k][0], pp_all[k][-1]]
        u = _axis(pts)
        pts.sort(key=lambda p: p[0] * u[0] + p[1] * u[1])
        others = [x for x in shorts if x[0] not in used and x[0] not in chain]
        t = ticks_of(pts, others)
        if len(t) < max(2, len(chain) // 2):
            continue                       # dashes without ticks: not this notation
        pieces.append([pts, {k for k, _ in t}])
        used |= set(chain) | {k for k, _ in t}
    # pieces of one overhang: ends close together are joined through any
    # short strokes in the gap (the curve where it turns, drawn as a dash
    # and a tick or two)
    merged = True
    while merged and len(pieces) > 1:
        merged = False
        for a in range(len(pieces)):
            for b in range(a + 1, len(pieces)):
                A, B = pieces[a][0], pieces[b][0]
                ends = [(math.dist(A[-1], B[0]), False, False), (math.dist(A[-1], B[-1]), False, True),
                        (math.dist(A[0], B[0]), True, False), (math.dist(A[0], B[-1]), True, True)]
                d, ra, rb = min(ends)
                if d > JOIN:
                    continue
                A2 = A[::-1] if ra else A
                B2 = B[::-1] if rb else B
                gap = LineString([A2[-1], B2[0]])
                bridge = [(i, pp) for i, pp in usable if i not in used and length(pp) <= DASH_MAX
                          and gap.distance(Point(pp[len(pp) // 2])) < 0.35]
                mid = sorted((p for _, pp in bridge for p in (pp[0], pp[-1])), key=lambda p: gap.project(Point(p)))
                pieces[a] = [A2 + mid + B2, pieces[a][1] | pieces[b][1] | {i for i, _ in bridge}]
                used |= {i for i, _ in bridge}
                del pieces[b]
                merged = True
                break
            if merged:
                break
    for pts, tick_ids in pieces:
        t = ticks_of(pts, [(k, pp_all[k]) for k in tick_ids if k in pp_all])
        side = 1 if sum(s for _, s in t) >= 0 else -1
        feats.append(('overhang', _oriented(pts, side), lines[next(iter(tick_ids), 0)][0] if tick_ids else 'GRAY'))
    # ticked lines
    from .settings import SETTINGS
    for i, pp in longs:
        cand = [x for x in shorts if x[0] not in used]
        if not SETTINGS['brown_ticks']:
            # brown short strokes are mud or rocks, not ticks, unless the line itself is brown
            cand = [x for x in cand if lines[x[0]][0] != 'BROWN' or lines[i][0] == 'BROWN']
        t = [(k, s) for k, s in ticks_of(pp, cand) if k not in used]
        if len(t) >= MIN_TICKS:
            side = 1 if sum(s for _, s in t) >= 0 else -1
            feats.append(('step', _oriented(list(pp), side), lines[i][0]))
            used.add(i)
            used |= {k for k, _ in t}
    return feats, used


def th2(feats, passage, px, climbs=(), pitch_min=2.0):
    """th2 text for the notation features inside the passage. `climbs` are
    [(point (m), height)] from the elevation sketch, to tell pitches."""
    o = []
    inside = passage.buffer(0.3)
    for kind, pts, _ in feats:
        line = LineString(pts)
        if not inside.intersects(line):
            continue
        if kind == 'overhang':
            head = 'line overhang'
        else:
            near = [h for p, h in climbs if line.distance(Point(p)) < 2.0]
            head = 'line pit' if near and max(near) >= pitch_min else 'line floor-step'
        from .marks import smooth_rows
        o += [head] + smooth_rows(pts, px) + ['endline', '']
    return o
