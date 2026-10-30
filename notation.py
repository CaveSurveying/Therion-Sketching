# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
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

from shapely.geometry import LineString, Point, Polygon

from . import scale
from .geom import length

TICK_MAX = 0.45      # m: a tick is at most this long
TICK_MIN = 0.06
LINE_MIN = 0.6       # m: a ticked line is at least this long
TOUCH = 0.15         # m: a tick's end is this close to its line
MIN_TICKS = 2
SHORT_LINE = 0.4     # m: a ticked line this short is a step only with SHORT_TICKS ticks or more
SHORT_TICKS = 3
DASH_MIN, DASH_MAX = 0.08, 0.5
DASH_GAP = 0.55      # m: dashes of one line are at most this far apart
MIN_DASHES = 3
JOIN = 1.2           # m: overhang pieces with ends this close are one overhang
SKIP = ('BLUE', 'GREEN', 'RED', 'ORANGE', 'PURPLE')


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


def ticks_of(line_pp, shorts, reach=TOUCH):
    """[(index into shorts, side +1 left / -1 right)] of strokes ticking this line."""
    line = LineString(line_pp)
    out = []
    for i, pp in shorts:
        ends = [Point(pp[0]), Point(pp[-1])]
        dist = [line.distance(e) for e in ends]
        k = 0 if dist[0] <= dist[1] else 1
        if dist[k] > reach or dist[1 - k] < dist[k] + 0.04:
            continue
        att, free = (pp[0], pp[-1]) if k == 0 else (pp[-1], pp[0])
        ld = _local_dir(line, line.project(Point(att)))
        td = _axis([att, free])
        if _angle(ld, td) < 45:
            continue
        side = 1 if ld[0] * td[1] - ld[1] * td[0] > 0 else -1
        out.append((i, side))
    return out


JOIN_TURN = 35.0     # degrees: dashed lines carrying on across a gap turn no more than this


def _end_dir(pts, at_end):
    """Unit direction a polyline leaves its end (at_end) or start, over its last 0.5 m."""
    q = pts if at_end else pts[::-1]
    e = q[-1]
    b = next((p for p in reversed(q[:-1]) if math.dist(p, e) >= 0.5), q[0])
    d = math.dist(b, e) or 1.0
    return ((e[0] - b[0]) / d, (e[1] - b[1]) / d)


def join_dashed(lines, lone, gap):
    """Dashed lines carrying on across a gap (up to `gap`) joined into one,
    in order: through lone dashes lying along the gap, or straight across a
    short one (FairyChimneys 36 to 38: a big chamber's roof drawn sparsely,
    the user). lone: [points] of dashes in no line. Returns (lines, lone used)."""
    lines = [list(l) for l in lines]
    used = set()
    changed = True
    while changed:
        changed = False
        best = None
        for i, a in enumerate(lines):
            for j, b in enumerate(lines):
                if i == j:
                    continue
                for ea in (True, False):
                    for eb in (True, False):
                        pa, pb = (a[-1] if ea else a[0]), (b[-1] if eb else b[0])
                        d = math.dist(pa, pb)
                        if d < 1e-6 or d > gap:
                            continue
                        g = ((pb[0] - pa[0]) / d, (pb[1] - pa[1]) / d)
                        da, db = _end_dir(a, ea), _end_dir(b, eb)
                        db = (-db[0], -db[1])                  # b entered from the gap
                        if _angle(da, g) > JOIN_TURN or _angle(db, g) > JOIN_TURN:
                            continue
                        seg = [pa, pb]
                        on = [k for k, q in enumerate(lone) if k not in used and
                              min(_seg_dist(p, seg) for p in (q[0], q[-1])) < 0.3]
                        if d > 1.5 * gap / 3 and not on:
                            continue
                        if best is None or d < best[0]:
                            best = (d, i, j, ea, eb, on)
        if best:
            d, i, j, ea, eb, on = best
            a = lines[i] if ea else lines[i][::-1]
            b = lines[j] if not eb else lines[j][::-1]
            lines[i] = a + b
            lines.pop(j)
            used |= set(on)
            changed = True
    return lines, used


def _seg_dist(p, seg):
    (ax, ay), (bx, by) = seg
    L2 = (bx - ax) ** 2 + (by - ay) ** 2
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * (bx - ax) + (p[1] - ay) * (by - ay)) / L2))
    return math.dist(p, (ax + t * (bx - ax), ay + t * (by - ay)))


def presumed(lines, dash_gap=DASH_GAP, join_gap=None):
    """Black dashed lines with no ticks: a wall the surveyors could not see
    all of, where the passage carries on (`line wall -subtype presumed`).
    lines: [(colour, points)], what notation.find left. Returns
    ([points of each dashed line, in order], {indices of the dashes used})."""
    cands = [(i, pp) for i, (c, pp) in enumerate(lines) if c == 'BLACK' and len(pp) > 1
             and 0.02 <= length(pp) <= DASH_MAX * scale.factor(pp[0]) and math.dist(pp[0], pp[-1]) >= 0.5 * length(pp)]
    pp_of = dict(cands)
    out, used = [], set()
    for chain in dash_chains(cands, dash_gap, MIN_DASHES):
        pts = [p for k in chain for p in (pp_of[k][0], pp_of[k][-1])]
        u = _axis(pts)
        pts.sort(key=lambda p: p[0] * u[0] + p[1] * u[1])
        if length(pts) < 0.5:
            continue
        out.append(pts)
        used |= set(chain)
    if join_gap and out:
        lone_idx = [i for i, _ in cands if i not in used]
        out, got = join_dashed(out, [pp_of[i] for i in lone_idx], join_gap)
        used |= {lone_idx[k] for k in got}
    return out, used


RIDGE = 0.15        # m: rock edges this close at one end meet at a ridge point


def _boulder(pp, shorts):
    """A closed loop holding three or more short strokes, two of them meeting at
    one end: a boulder and its rock edges (Style.md), not a step and its ticks
    (TridentLeft; Trident's hole rim has two ticks close together)."""
    from .marks import is_closed
    if not is_closed(pp):
        return False
    inside = Polygon(pp).buffer(0)
    edges = [q for q in shorts if inside.contains(Point(q[0])) or inside.contains(Point(q[-1]))]
    meet = lambda a, b: min(math.dist(p, q) for p in (a[0], a[-1]) for q in (b[0], b[-1])) < RIDGE
    return len(edges) >= 3 and any(meet(a, b) for k, a in enumerate(edges) for b in edges[k + 1:])


def dash_chains(cands, dash_gap=DASH_GAP, min_dashes=MIN_DASHES):
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
            if gap > dash_gap * scale.factor(ends[0]) or gap < 0.02:     # sparser in a bigger passage
                continue
            ca = ((pa[0][0] + pa[-1][0]) / 2, (pa[0][1] + pa[-1][1]) / 2)
            cb = ((pb[0][0] + pb[-1][0]) / 2, (pb[0][1] + pb[-1][1]) / 2)
            if _angle(ua, _axis([ca, cb])) > 25:
                continue
            link[a].add(b)
            link[b].add(a)
    # each dash joins only its nearest dash ahead and behind along its line, and only if that
    # one takes it back too (two dashed lines side by side are not one zigzag: FairyChimneys 12)
    def centre(k):
        pp = pp_of[k]
        return ((pp[0][0] + pp[-1][0]) / 2, (pp[0][1] + pp[-1][1]) / 2)

    def nearest(a):
        u, ca = _axis(pp_of[a]), centre(a)
        best = {}
        for b in link[a]:
            cb = centre(b)
            t = (cb[0] - ca[0]) * u[0] + (cb[1] - ca[1]) * u[1]
            side = t > 0
            if side not in best or math.dist(ca, cb) < math.dist(ca, centre(best[side])):
                best[side] = b
        return set(best.values())
    from .settings import SETTINGS
    if SETTINGS.get('dash_neighbours'):
        keep = {a: nearest(a) for a in idx}
        link = {a: {b for b in keep[a] if a in keep[b]} for a in idx}
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
        if len(comp) >= min_dashes:
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
    from .settings import SETTINGS
    usable = [(i, pp) for i, (c, pp) in enumerate(lines) if c not in SKIP and len(pp) > 1]
    # a short step (down to SHORT_LINE) counts if it has at least SHORT_TICKS ticks
    longs = [(i, pp) for i, pp in usable if length(pp) >= (SHORT_LINE if SETTINGS['short_notation'] else LINE_MIN)]
    # ticks and dashes are drawn bigger in a bigger passage (the sketch is zoomed out: scale.factor)
    f = lambda pp: scale.factor(pp[len(pp) // 2])
    shorts = [(i, pp) for i, pp in usable if _is_short(pp, TICK_MIN, TICK_MAX * f(pp))]
    longs = [(i, pp) for i, pp in longs if not _boulder(pp, [q for _, q in shorts])]
    feats, used = [], set()
    # dashed lines with a tick on each dash (first, so their ticks are
    # not taken for the ticks of a nearby line)
    cands = [(i, pp) for i, pp in usable if _is_short(pp, DASH_MIN, DASH_MAX * f(pp))]
    if not SETTINGS['brown_ticks']:          # brown dashes are mud, not an overhang
        cands = [(i, pp) for i, pp in cands if lines[i][0] != 'BROWN']
    pp_all = dict(usable)
    pieces = []                          # [points in order, tick indices]
    two = 2 if SETTINGS['short_notation'] else MIN_DASHES
    for chain in dash_chains(cands, DASH_GAP, two):
        pts = []
        for k in chain:
            pts += [pp_all[k][0], pp_all[k][-1]]
        u = _axis(pts)
        pts.sort(key=lambda p: p[0] * u[0] + p[1] * u[1])
        if len({lines[k][0] for k in chain}) > 1:
            continue                       # one overhang is drawn in one colour
        others = [x for x in shorts if x[0] not in used and x[0] not in chain]
        if not SETTINGS['brown_ticks']:
            others = [x for x in others if lines[x[0]][0] != 'BROWN']
        t = ticks_of(pts, others)
        if len(t) < max(2, len(chain) // 2) or (len(chain) < MIN_DASHES and len(t) < len(chain)):
            continue                       # dashes without ticks (two dashes: a tick on each)
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
    # ticked lines: each line's candidate ticks found first, then every tick
    # given to the line it is nearest (two step lines side by side share the
    # ticks between them by distance, not by which was looked at first)
    from .settings import SETTINGS
    found = {}
    for i, pp in longs:
        if i in used:
            continue
        cand = [x for x in shorts if x[0] not in used and x[0] != i]
        if not SETTINGS['brown_ticks']:
            # brown short strokes are mud or rocks, not ticks, unless the line itself is brown
            cand = [x for x in cand if lines[x[0]][0] != 'BROWN' or lines[i][0] == 'BROWN']
        t = list(ticks_of(pp, cand))
        if SETTINGS['mud_ticks'] and lines[i][0] == 'BROWN' and t:
            # brown "ticks" on a brown line in a field of mud dashes are mud, not a step
            ln = LineString(pp)
            got = {k for k, _ in t}
            mud = sum(1 for k, q in usable if k not in got and k != i and lines[k][0] == 'BROWN'
                      and _is_short(q, TICK_MIN, SETTINGS['mud_ticks']) and ln.distance(LineString(q)) < 1.0)
            # sparse ticks (under 0.8 a metre) or many more dashes about than ticks: mud
            if len(t) / max(ln.length, 1e-9) < 0.8 or mud >= 4 * len(t):
                t = []
        if SETTINGS['tick_reach'] > TOUCH and lines[i][0] not in ('BLACK', 'BROWN'):
            # ticks drawn a little clear of the line: only of the line's own colour, and never
            # for a black line (wall) or brown (whose dashes beside it are mud)
            got = {k for k, _ in t}
            far = [x for x in cand if x[0] not in got and lines[x[0]][0] == lines[i][0]]
            t += list(ticks_of(pp, far, SETTINGS['tick_reach']))
        if t:
            found[i] = t
    pp_of = dict(longs)
    owner = {}
    for i, t in found.items():
        L = LineString(pp_of[i])
        for k, side in t:
            tick = LineString(pp_all[k])
            d = L.distance(tick)
            if k not in owner or d < owner[k][0]:
                owner[k] = (d, i, side)
    mine = {}
    for k, (_, i, side) in owner.items():
        mine.setdefault(i, []).append((k, side))
    for i, pp in longs:
        t = mine.get(i, [])
        if i in used or len(t) < MIN_TICKS or (length(pp) < LINE_MIN and len(t) < SHORT_TICKS):
            continue
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
