# Ported from caves-mendip-swildons, tools/sketch2therion (commit 198bf46,
# https://github.com/paperclipmonkey/caves-mendip-swildons). GPLv3: see tools/LICENSE.
"""Walls with fewer, smoother points.

Converted walls follow the sketch stroke by stroke: four or five points a
metre, some straight and some curved. A hand-drawn Therion wall has about
one point a metre, each a smooth Bezier node. This refits each wall with
as few cubic Beziers as keep within TOL of where it was (Schneider's
curve fitting, "An Algorithm for Automatically Fitting Digitized Curves",
Graphics Gems 1990): a node where the fit splits gets one tangent for both
sides, so it is smooth, and a sharp corner in the wall stays a corner.

A wall keeps its two end points exactly, so the outline joins up as
before. A scrap whose refitted walls would cross themselves or each other
where they didn't, or whose outline Therion would no longer join up
cleanly, is fitted more tightly, and if that fails too, left as it was.

    python3 -m tools.sketch2therion smooth FILE.th2 [...] [--scrap NAME]
"""
import math
import re

from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

from .tidy import Obj, bezier_points, parse_scrap, reverse_segments, scale_of, therion_chain, therion_rings

TOL = 0.10          # m: how far a refitted wall may stray from the old one
CORNER = 55         # degrees: a sharper turn than this stays a corner
TANGENT = 0.25      # m: how far along the wall to look for a tangent
SPARSE = 2.0        # points a metre: a wall with no more than this is left as it is
SPUR = 0.5          # m: a stroke doubling back on itself for less than this is cut out
REVERSE = 150       # degrees: a node turning back more sharply is a cusp


# -- fitting --------------------------------------------------------------------------

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def _mul(a, k):
    return (a[0] * k, a[1] * k)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _unit(a):
    d = math.hypot(*a)
    return (a[0] / d, a[1] / d) if d > 1e-12 else (0.0, 0.0)


def _bez(b, t):
    u = 1 - t
    return _add(_add(_mul(b[0], u ** 3), _mul(b[1], 3 * u * u * t)),
                _add(_mul(b[2], 3 * u * t * t), _mul(b[3], t ** 3)))


def _bez1(b, t):
    u = 1 - t
    return _add(_add(_mul(_sub(b[1], b[0]), 3 * u * u), _mul(_sub(b[2], b[1]), 6 * u * t)),
                _mul(_sub(b[3], b[2]), 3 * t * t))


def _bez2(b, t):
    return _add(_mul(_add(_sub(b[2], _mul(b[1], 2)), b[0]), 6 * (1 - t)),
                _mul(_add(_sub(b[3], _mul(b[2], 2)), b[1]), 6 * t))


def _chord_params(d):
    u = [0.0]
    for a, b in zip(d, d[1:]):
        u.append(u[-1] + math.dist(a, b))
    return [x / u[-1] for x in u] if u[-1] > 0 else u


def _generate(d, u, t1, t2):
    """The Bezier from d[0] to d[-1], leaving along t1 and arriving along
    t2, closest (least squares) to the points at parameters u."""
    c00 = c01 = c11 = x0 = x1 = 0.0
    p0, p3 = d[0], d[-1]
    for p, t in zip(d, u):
        s = 1 - t
        a1 = _mul(t1, 3 * s * s * t)
        a2 = _mul(t2, 3 * s * t * t)
        c00 += _dot(a1, a1)
        c01 += _dot(a1, a2)
        c11 += _dot(a2, a2)
        tmp = _sub(p, _add(_mul(p0, s ** 3 + 3 * s * s * t), _mul(p3, 3 * s * t * t + t ** 3)))
        x0 += _dot(a1, tmp)
        x1 += _dot(a2, tmp)
    det = c00 * c11 - c01 * c01
    seg = math.dist(p0, p3)
    if abs(det) > 1e-12:
        al = (x0 * c11 - x1 * c01) / det
        ar = (c00 * x1 - c01 * x0) / det
    else:
        al = ar = seg / 3
    # handles that point backwards or run far past the chord make loops,
    # and very short ones cusps (MetaPost then miscounts the outline's turns):
    # fall back to the usual third of the chord
    if al < 0.1 * seg or ar < 0.1 * seg or al > seg or ar > seg:
        al = ar = seg / 3
    return (p0, _add(p0, _mul(t1, al)), _add(p3, _mul(t2, ar)), p3)


def _max_error(d, b, u):
    worst, at = 0.0, len(d) // 2
    for i in range(1, len(d) - 1):
        e = math.dist(_bez(b, u[i]), d[i])
        if e > worst:
            worst, at = e, i
    return worst, at


def _reparam(d, b, u):
    out = []
    for p, t in zip(d, u):
        q, q1, q2 = _bez(b, t), _bez1(b, t), _bez2(b, t)
        diff = _sub(q, p)
        den = _dot(q1, q1) + _dot(diff, q2)
        out.append(min(1.0, max(0.0, t - _dot(diff, q1) / den)) if abs(den) > 1e-12 else t)
    return out


def _tangent(d, i, step, ahead):
    """Unit tangent at d[i] from a point about `step` along the line."""
    j = i
    while 0 <= j + (1 if ahead else -1) < len(d):
        j += 1 if ahead else -1
        if math.dist(d[i], d[j]) >= step:
            break
    return _unit(_sub(d[j], d[i]))


def _fit(d, t1, t2, err, step, depth=0):
    if len(d) == 2 or depth > 30:
        k = math.dist(d[0], d[-1]) / 3
        return [(d[0], _add(d[0], _mul(t1, k)), _add(d[-1], _mul(t2, k)), d[-1])]
    u = _chord_params(d)
    b = _generate(d, u, t1, t2)
    worst, at = _max_error(d, b, u)
    if worst <= err:
        return [b]
    if worst <= 4 * err:
        for _ in range(12):
            u = _reparam(d, b, u)
            b = _generate(d, u, t1, t2)
            worst, at = _max_error(d, b, u)
            if worst <= err:
                return [b]
    at = min(max(at, 1), len(d) - 2)
    # one tangent either side of the split: a smooth node
    back, fwd = _tangent(d, at, step, False), _tangent(d, at, step, True)
    tc = _unit(_sub(back, fwd))
    if tc == (0.0, 0.0):
        tc = _unit(_sub(d[at - 1], d[at + 1]))
    return (_fit(d[:at + 1], t1, tc, err, step, depth + 1)
            + _fit(d[at:], _mul(tc, -1), t2, err, step, depth + 1))


def _rdp(pts, eps):
    """Indices of the Douglas-Peucker simplification of pts."""
    keep = {0, len(pts) - 1}
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = pts[i], pts[j]
        seg = LineString([a, b]) if a != b else Point(a)
        k, worst = None, eps
        for m in range(i + 1, j):
            e = seg.distance(Point(pts[m]))
            if e > worst:
                k, worst = m, e
        if k is not None:
            keep.add(k)
            stack += [(i, k), (k, j)]
    return sorted(keep)


def _turn(v1, v2):
    """How far v2 turns from v1, in degrees (0 to 180)."""
    return math.degrees(abs(math.atan2(v1[0] * v2[1] - v1[1] * v2[0], _dot(v1, v2))))


def _despur(d, K):
    """The polyline without spurs: places where the sketched stroke runs
    out and straight back for a short way. Fitted, a spur is a node where
    the wall turns right back, and MetaPost then miscounts the outline's
    turns ("scrap outline intersects itself")."""
    for _ in range(200):
        idx = _rdp(d, 0.05 * K)
        for a, b, c in zip(idx, idx[1:], idx[2:]):
            ab, bc = math.dist(d[a], d[b]), math.dist(d[b], d[c])
            if min(ab, bc) < SPUR * K and _turn(_sub(d[b], d[a]), _sub(d[c], d[b])) > REVERSE:
                d = d[:a + 1] + d[b + 1:] if ab <= bc else d[:b] + d[c:]
                break
        else:
            return d
    return d


def reversals(segs):
    """How many nodes of a line turn right back on themselves."""
    n = 0
    for s, t, prev in zip(segs[1:], segs[2:], segs):
        p = (s[-2], s[-1])
        a = (s[2], s[3]) if len(s) == 6 else (prev[-2], prev[-1])
        b = (t[0], t[1]) if len(t) == 6 else (t[-2], t[-1])
        v1, v2 = _sub(p, a), _sub(b, p)
        if math.hypot(*v1) > 1e-9 and math.hypot(*v2) > 1e-9 and _turn(v1, v2) > REVERSE:
            n += 1
    return n


JOIN_REACH = 1.0    # m: with [convert] join_local, a join is refitted this far either side


def _join_local(sa, sb, qa, qb, K):
    """Walls sa and sb (segments) as one, refitted only near the join
    (qa: where sa is cut, qb: where sb is taken up): from sa's last node
    at least JOIN_REACH before qa to sb's first node at least JOIN_REACH
    after qb. The rest of both stays exactly as it was, so joining one
    wall after another does not add up the refit's error."""
    la, lb = LineString(bezier_points(sa, 8)), LineString(bezier_points(sb, 8))
    ta, tb = la.project(Point(qa)), lb.project(Point(qb))
    na = max([k for k in range(len(sa)) if la.project(Point(sa[k][-2:])) <= ta - JOIN_REACH * K], default=0)
    nb = min([k for k in range(len(sb)) if lb.project(Point(sb[k][-2:])) >= tb + JOIN_REACH * K],
             default=len(sb) - 1)
    pa = bezier_points([[sa[na][-2], sa[na][-1]]] + sa[na + 1:], 8)
    pb = bezier_points([[sb[0][-2], sb[0][-1]]] + sb[1:nb + 1], 8)
    pts = [p for p in pa if la.project(Point(p)) <= ta] + [p for p in pb if lb.project(Point(p)) >= tb]
    mid = _fit_within([[x, y] for x, y in pts], K)
    mid[0] = [sa[na][-2], sa[na][-1]]
    if len(mid[-1]) == 6:
        mid[-1][4:] = [sb[nb][-2], sb[nb][-1]]
    else:
        mid[-1] = [sb[nb][-2], sb[nb][-1]]
    return [list(r) for r in sa[:na + 1]] + mid[1:] + [list(r) for r in sb[nb + 1:]]


def _fit_within(rows, K):
    """fit_wall, at a finer tolerance where the fit strays more than TOL
    from the points (a long gentle curve fitted as one segment can); in
    the end the points as they are."""
    line = LineString([r[-2:] for r in rows])
    for tol in (TOL, TOL / 2, TOL / 4):
        segs = fit_wall(rows, K, tol)
        if all(line.distance(Point(p)) <= TOL * K for p in bezier_points(segs, 20)):
            return segs
    return rows


def _running_mean(d, window, step):
    """Points every `step` along d, each the mean of those within window / 2
    either side along the line; the ends stay where they are."""
    line = LineString(d)
    n = max(2, int(line.length / step))
    pts = [line.interpolate(k / n, normalized=True).coords[0] for k in range(n + 1)]
    h = max(1, int(window / step / 2))
    out = [pts[0]]
    for k in range(1, n):
        a, b = max(0, k - h), min(n, k + h)
        # near the ends the window shrinks evenly, so the ends do not drift
        r = min(k - a, b - k)
        win = pts[k - r:k + r + 1]
        out.append((sum(p[0] for p in win) / len(win), sum(p[1] for p in win) / len(win)))
    out.append(pts[-1])
    return out


def fit_wall(segs, K, tol=TOL):
    """The rows of a wall refitted with fewer, smooth Bezier nodes."""
    d = []
    for p in bezier_points(segs, 8):
        if not d or math.dist(p, d[-1]) > 1e-6:
            d.append(p)
    if len(d) < 3:
        return segs
    d = _despur(d, K)
    from .settings import SETTINGS
    # corners: sharp turns that a coarse simplification still shows (with
    # pre-smoothing, only clear ones: hand wobble is not a corner)
    presmooth = SETTINGS['wall_presmooth']
    idx = _rdp(d, (1.5 if presmooth else 0.5) * tol * K)
    corners = [0]
    for a, b, c in zip(idx, idx[1:], idx[2:]):
        if _turn(_sub(d[b], d[a]), _sub(d[c], d[b])) > (70 if presmooth else CORNER):
            corners.append(b)
    corners.append(len(d) - 1)
    if SETTINGS['wall_presmooth']:
        # hand wobble smoothed out (a running mean over a few times the tolerance)
        # between the corners, which stay sharp: a deliberate bulge keeps its shape
        w = SETTINGS['wall_presmooth'] * tol * K
        nd, nc = [], [0]
        for i, j in zip(corners, corners[1:]):
            run = d[i:j + 1]
            run = _running_mean(run, w, 0.02 * K) if len(run) > 2 and LineString(run).length > 0 else run
            nd += run if not nd else run[1:]
            nc.append(len(nd) - 1)
        d, corners = nd, nc
    step = TANGENT * K
    out = [[d[0][0], d[0][1]]]
    for i, j in zip(corners, corners[1:]):
        run = d[i:j + 1]
        if len(run) == 2 or math.dist(run[0], run[-1]) < 1e-9 and len(run) < 4:
            out.append([run[-1][0], run[-1][1]])
            continue
        t1 = _tangent(run, 0, step, True)
        t2 = _tangent(run, len(run) - 1, step, False)
        for b in _fit(run, t1, t2, tol * K, step):
            out.append([b[1][0], b[1][1], b[2][0], b[2][1], b[3][0], b[3][1]])
    return out


# -- checking a scrap ------------------------------------------------------------------

def _crossings(lines):
    """Pairs of walls that cross or touch away from their own ends."""
    geoms = [LineString(l) for l in lines]
    tree = STRtree(geoms)
    out = set()
    for i, g in enumerate(geoms):
        for j in tree.query(g):
            j = int(j)
            if j <= i:
                continue
            x = g.intersection(geoms[j])
            if x.is_empty:
                continue
            ends = [Point(p) for l in (lines[i], lines[j]) for p in (l[0], l[-1])]
            pts = [x] if x.geom_type == 'Point' else list(getattr(x, 'geoms', [x]))
            if any(min(e.distance(p) for e in ends) > 1e-3 for p in pts):
                out.add((i, j))
    return out


def ring_ok(ring):
    """What Therion and MetaPost need of an outline: (it doesn't cross
    itself, for the 3D model; it turns round, so MetaPost's turningnumber
    isn't 0 and it doesn't warn "scrap outline intersects itself")."""
    pts = [ring[0]]
    for q in ring[1:]:
        if math.dist(q, pts[-1]) > 1e-3:
            pts.append(q)
    if len(pts) > 1 and math.dist(pts[0], pts[-1]) < 1e-3:
        pts.pop()
    if len(pts) < 3:
        return False, False
    turn = 0.0
    for i in range(len(pts)):
        a, b, c = pts[i - 2], pts[i - 1], pts[i]
        t = math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(b[1] - a[1], b[0] - a[0])
        turn += (t + math.pi) % (2 * math.pi) - math.pi
    return Polygon(pts).is_valid, abs(turn) > math.pi


def _red(a):
    while a > 180:
        a -= 360
    while a <= -180:
        a += 360
    return a


def _arg(v):
    return 0.0 if v == (0.0, 0.0) else math.degrees(math.atan2(v[1], v[0]))


def _sweep(p0, c1, c2, p3, n=16):
    """How far the direction turns along a Bezier, in degrees."""
    s, prev = 0.0, None
    for k in range(n + 1):
        t = k / n
        u = 1 - t
        v = (3 * u * u * (c1[0] - p0[0]) + 6 * u * t * (c2[0] - c1[0]) + 3 * t * t * (p3[0] - c2[0]),
             3 * u * u * (c1[1] - p0[1]) + 6 * u * t * (c2[1] - c1[1]) + 3 * t * t * (p3[1] - c2[1]))
        if math.hypot(*v) < 1e-12:
            continue
        a = _arg(v)
        if prev is not None:
            s += _red(a - prev)
        prev = a
    return s


def mp_turning(lines):
    """MetaPost's turningnumber of the outline Therion draws from these
    lines (each a list of th2 rows, in order and the right way round).
    Therion joins them with `--`, so where one line ends on the next
    there is a segment of no length; MetaPost takes its direction as 0
    (east) and reduces the turn at each end of it to under 180 degrees,
    so where the walls run west across the join it miscounts a whole
    turn, and can make 0 of an outline that turns once round. Therion
    then warns "scrap outline intersects itself"."""
    pts, left, right = [], [], []
    for segs in lines:
        for k, r in enumerate(segs):
            p = (r[-2], r[-1])
            if not pts:
                pts.append(p), left.append(p), right.append(p)
                continue
            if len(r) == 6 and k > 0:
                right[-1] = (r[0], r[1])
                left.append((r[2], r[3]))
            else:
                right[-1] = pts[-1]
                left.append(p)
            pts.append(p), right.append(p)
    n = len(pts)
    if n < 3:
        return 0
    right[-1], left[0] = pts[-1], pts[0]          # -- cycle
    res, turns = 0.0, 0
    for i in range(n):
        j = (i + 1) % n
        p, q, c1, c2 = pts[i], pts[j], right[i], left[j]
        if c1 == p and c2 == q:
            c1 = (p[0] + (q[0] - p[0]) / 3, p[1] + (q[1] - p[1]) / 3)
            c2 = (p[0] + 2 * (q[0] - p[0]) / 3, p[1] + 2 * (q[1] - p[1]) / 3)
        res += _sweep(p, c1, c2, q) if p != q else 0.0
        while res > 180:
            res, turns = res - 360, turns + 1
        while res <= -180:
            res, turns = res + 360, turns - 1
        # the turn at the next knot, as MetaPost finds the directions in and out
        x = left[j] if left[j] != q else (right[i] if right[i] != q else pts[i])
        y = right[j] if right[j] != q else (left[(j + 1) % n] if left[(j + 1) % n] != q else pts[(j + 1) % n])
        res += _red(_arg((y[0] - q[0], y[1] - q[1])) - _arg((q[0] - x[0], q[1] - x[1])))
        while res >= 180:
            res, turns = res - 360, turns + 1
        while res <= -180:
            res, turns = res + 360, turns - 1
    return turns


def _state(walls, outline):
    lines = [bezier_points(o.segments(), 20) for o in walls]
    simple = [LineString(l).is_simple for l in lines]
    # the outlines only depend on where the walls end, which refitting
    # keeps, so they are the same outlines before and after
    ol = [bezier_points(o.segments(), 20) for o in outline]
    sound = []
    for ring in therion_rings(ol):
        pts = [p for i, rev in ring for p in (ol[i][::-1] if rev else ol[i])]
        segs = [reverse_segments(outline[i].segments()) if rev else outline[i].segments() for i, rev in ring]
        sound += list(ring_ok(pts)) + [mp_turning(segs) != 0]
    return lines, simple, _crossings(lines), sound


def smooth_scrap(objs, K, base=None):
    """Refit the scrap's walls. Returns (points before, points after).
    base(wall) gives a wall's tolerance in metres (default TOL)."""
    walls = [o for o in objs if o.kind == 'line' and o.head.startswith('line wall') and len(o.segments()) > 2
             and len(o.segments()) > SPARSE * LineString(bezier_points(o.segments())).length / K]
    if not walls:
        return 0, 0
    outline = [o for o in objs if o.kind == 'line' and o.head.startswith('line wall')
               and '-outline none' not in o.head and '-close on' not in o.head and len(o.segments()) > 1]
    old = {id(o): o.rows for o in walls}
    before = sum(len(o.segments()) for o in walls)
    _, simple0, cross0, sound0 = _state(walls, outline)
    # which outline each wall is part of
    rings = [set(map(tuple, r)) for r in therion_chain([bezier_points(o.segments(), 20) for o in outline])]
    ring_of = [next((k for k, r in enumerate(rings) if tuple(o.segments()[0][-2:]) in r), None) for o in walls]
    tols = (1.0, 0.5, 0.25, None)               # times the wall's tolerance; None: as it was
    base_of = [base(o) if base else TOL for o in walls]
    level = [0] * len(walls)

    def refit(i):
        o = walls[i]
        o.rows = old[id(o)]
        if tols[level[i]] is not None:
            o.set_segments(fit_wall(o.segments(), K, tols[level[i]] * base_of[i]))
            # fitted away to nothing, or not much better (already smooth:
            # run again, it leaves walls as they are)
            n = len(Obj('line', '', old[id(o)]).segments())
            if not 2 <= len(o.segments()) <= min(0.75 * n, n - 2):
                o.rows = old[id(o)]

    old_line = {id(o): LineString(bezier_points(o.segments(), 8)) for o in walls}

    def strays(i):
        # (the fit's own check misses a long gentle curve made one segment)
        o = walls[i]
        return any(old_line[id(o)].distance(Point(p)) > base_of[i] * K for p in bezier_points(o.segments(), 20))

    for i in range(len(walls)):
        refit(i)
    # walls that now cross themselves or another wall, turn right back,
    # stray more than TOL from where they were, or are part of an outline that Therion would no longer accept, are
    # fitted more tightly, and in the end left as they were
    while True:
        _, simple, cross, sound = _state(walls, outline)
        bad = {i for i, (s, s0) in enumerate(zip(simple, simple0)) if s0 and not s}
        bad |= {i for i, o in enumerate(walls) if tols[level[i]] is not None and reversals(o.segments())}
        bad |= {i for i, o in enumerate(walls) if tols[level[i]] is not None and strays(i)}
        bad |= {i for pair in cross - cross0 for i in pair}
        broken = {k // 3 for k, (s, s0) in enumerate(zip(sound, sound0)) if s0 and not s}
        bad |= {i for i, k in enumerate(ring_of) if k in broken}
        bad = {i for i in bad if tols[level[i]] is not None}
        if not bad:
            break
        for i in bad:
            level[i] += 1
            refit(i)
    if any(s0 and not s for s, s0 in zip(sound, sound0)):
        for o in walls:
            o.rows = old[id(o)]
        return before, before
    return before, sum(len(o.segments()) for o in walls)


# -- one line per wall ------------------------------------------------------------------

DOUBLE = 0.3        # m: a wall piece off the outline this close along an outline wall doubles it
GAP = 0.6           # m: walls of the same kind this close, end to start and heading on, are one wall
BRIDGE = 0.75       # m: a presumed wall across less than this, between two walls, goes
SNAP = 0.1          # m: closer than this the next wall's start just moves onto the end
STUB = 1.0          # m: a wall piece off the outline and outside the passage shorter than this goes


def _outline_score(objs):
    """How bad the scrap's outlines are, as Therion and MetaPost see them:
    (outlines MetaPost says cross themselves, outlines that cross
    themselves, outlines)."""
    outline = [o for o in objs if o.kind == 'line' and o.head.startswith('line wall')
               and '-outline none' not in o.head and '-close on' not in o.head and len(o.segments()) > 1]
    ol = [bezier_points(o.segments(), 20) for o in outline]
    zero = bad = 0
    rings = therion_rings(ol)
    for ring in rings:
        pts = [p for i, rev in ring for p in (ol[i][::-1] if rev else ol[i])]
        segs = [reverse_segments(outline[i].segments()) if rev else outline[i].segments() for i, rev in ring]
        zero += mp_turning(segs) == 0
        bad += not ring_ok(pts)[0]
    return zero, bad, len(rings)


def _smooth_join(segs, k):
    """Make the node at row k smooth if the line only bends a little there."""
    if k + 1 >= len(segs) or len(segs[k]) != 6 or len(segs[k + 1]) != 6:
        return
    p = (segs[k][4], segs[k][5])
    a, b = _sub(p, (segs[k][2], segs[k][3])), _sub((segs[k + 1][0], segs[k + 1][1]), p)
    la, lb = math.hypot(*a), math.hypot(*b)
    if la < 1e-9 or lb < 1e-9 or _turn(a, b) > 45:
        return
    u = _unit(_add(_unit(a), _unit(b)))
    segs[k][2], segs[k][3] = p[0] - u[0] * la, p[1] - u[1] * la
    segs[k + 1][0], segs[k + 1][1] = p[0] + u[0] * lb, p[1] + u[1] * lb


LINKS_MADE = []        # the wall links one_line_per_wall made in the scrap being redone
SKIP_LINKS = set()     # links to leave out (redo_file tries without any that spoil the outline)


def _quality(objs):
    """(outlines that don't cross themselves, outlines that turn once): to compare."""
    out = [o for o in objs if o.kind == 'line' and len(o.segments()) > 1 and '-close on' not in o.head
           and o.head.startswith('line wall') and '-outline none' not in o.head and '-subtype invisible' not in o.head]
    ol = [bezier_points(o.segments(), 20) for o in out]
    valid = once = 0
    for ring in therion_rings(ol):
        pts = [p for i, r in ring for p in (ol[i][::-1] if r else ol[i])]
        segs = [reverse_segments(out[i].segments()) if r else out[i].segments() for i, r in ring]
        valid += ring_ok(pts)[0]
        once += abs(mp_turning(segs)) == 1
    return valid, once


def _rings_now(objs):
    out = [o for o in objs if o.kind == 'line' and len(o.segments()) > 1 and '-close on' not in o.head
           and o.head.startswith('line wall') and '-outline none' not in o.head and '-subtype invisible' not in o.head]
    return therion_rings([bezier_points(o.segments(), 20) for o in out])


def one_line_per_wall(objs, K):
    """Walls drawn as one line each, not in pieces:
    - pieces of the sketched walls that didn't end up on the outline
      (`-outline none`) go where they double an outline wall or stick out
      a little past it; inside the passage they are the edge of something,
      a `line border`
    - walls of the same kind that run on from one another (one ends where
      the next starts) are joined into one line, smooth through the join
      if it is a gentle bend, so long as Therion still makes the outline
      as well as before.
    Returns (dropped, made borders, joined)."""
    walls = [o for o in objs if o.kind == 'line' and o.head.startswith('line wall')]
    outline = [o for o in walls if '-outline none' not in o.head and '-close on' not in o.head
               and len(o.segments()) > 1]
    LINKS_MADE.clear()
    dropped = bordered = joined = 0
    if outline:
        lines = [LineString(bezier_points(o.segments())) for o in outline]
        tree = STRtree(lines)
        polys = [Polygon(r).buffer(0) for r in therion_chain([list(l.coords) for l in lines]) if len(r) > 3]
        passage = None
        for g in polys:
            passage = g if passage is None else passage.union(g)
        from .settings import SETTINGS
        ends = [tuple(o.segments()[k][-2:]) for o in outline for k in (0, -1)]

        def runs_on(o):
            # (interior_borders) drawn on from the end of an outline wall,
            # the same stroke: still the wall
            sg = o.segments()
            return SETTINGS['interior_borders'] and any(
                math.dist(tuple(sg[k][-2:]), p) < 0.05 * K for k in (0, -1) for p in ends)

        def splice_pocket(o):
            # a piece off the outline, both ends on one outline wall and lying outside the
            # passage: a pocket the wall goes out round (a deliberate bulge, not a stray
            # piece). The wall is rerouted round it; the refit smooths the join.
            from .nodes import nearest_on
            sg = o.segments()
            g = LineString(bezier_points(sg))
            if g.length > 2.0 * K or passage is None or passage.contains(g.interpolate(0.5, normalized=True)):
                return False
            e0, e1 = tuple(sg[0][-2:]), tuple(sg[-1][-2:])
            for w in outline:
                h0, h1 = nearest_on(w.segments(), e0), nearest_on(w.segments(), e1)
                if not h0 or not h1 or h0[0] > 0.15 * K or h1[0] > 0.15 * K:
                    continue
                from .nodes import split_segment
                ws = [list(x) for x in w.segments()]
                (_, i0, u0, _), (_, i1, u1, _) = h0, h1
                ps = [list(x) for x in sg]
                if (i0, u0) > (i1, u1):              # the pocket runs the other way round
                    (i0, u0), (i1, u1) = (i1, u1), (i0, u0)
                    ps = [list(x) for x in reverse_segments(sg)]
                line = LineString(bezier_points(ws))
                mouth = abs(line.project(Point(ps[-1][-2:])) - line.project(Point(ps[0][-2:])))
                if mouth > 3 * g.length:             # not across a pocket's mouth
                    continue
                # the wall cut where the pocket leaves it and where it comes back,
                # keeping its own curves either side
                a, _ = split_segment(tuple(ws[i0 - 1][-2:]), ws[i0], u0)
                _, b = split_segment(tuple(ws[i1 - 1][-2:]), ws[i1], u1)
                head = ws[:i0] + [a]
                tail = [b] + ws[i1 + 1:]
                start = [ps[0][-2], ps[0][-1]]
                new = head + [start] + ps[1:] + tail
                before_score, old_rows = _outline_score(objs), w.rows
                w.set_segments(new)
                o.kind = 'drop'
                if _outline_score(objs) <= before_score:
                    return True
                w.rows, o.kind = old_rows, 'line'     # it spoilt the outline: not a pocket after all
                return False
            return False

        def links(o):
            # both ends on the ends of two different outline walls: the piece
            # of the stroke between them (round a bend the fill took in)
            sg = o.segments()
            # (within 15 cm: TridentLeft 10, a drawn line 7 cm short, dropped, hand edit)
            hit = [next((w for w in outline for k in (0, -1)
                         if math.dist(tuple(sg[e][-2:]), tuple(w.segments()[k][-2:])) < LINK_REACH * K), None)
                   for e in (0, -1)]
            return hit[0] is not None and hit[1] is not None and hit[0] is not hit[1]

        for o in walls:
            if '-outline none' not in o.head or len(o.segments()) < 2:
                continue
            key = tuple(round(v) for v in o.segments()[0][-2:] + o.segments()[-1][-2:])
            if SETTINGS['pockets'] and splice_pocket(o):
                continue
            if SETTINGS['wall_links'] and links(o) and key not in SKIP_LINKS and \
                    LineString(bezier_points(o.segments())).length >= SETTINGS['wall_links'] * K:
                before = _outline_score(objs)
                head, rows = o.head, o.rows
                o.head = o.head.replace(' -outline none', '')
                # run on from the wall whose end it starts at (so the walls join into one line)
                sg = o.segments()
                if not any(math.dist(tuple(sg[0][-2:]), tuple(w.segments()[-1][-2:])) < LINK_REACH * K for w in outline):
                    o.set_segments(reverse_segments(sg))
                after = _outline_score(objs)
                if after <= before:     # only if Therion makes the outline as well as before
                    LINKS_MADE.append(key)
                    continue
                o.head, o.rows = head, rows
            g = LineString(bezier_points(o.segments()))
            samples = [g.interpolate(i / 10, normalized=True) for i in range(11)]
            near = [lines[int(j)] for j in tree.query(g.buffer(DOUBLE * K))]
            along = sum(any(l.distance(q) < DOUBLE * K for l in near) for q in samples)
            inside = sum(passage is not None and passage.buffer(-0.05 * K).contains(q) for q in samples)
            outside = sum(passage is None or not passage.buffer(0.05 * K).contains(q) for q in samples)
            if along >= 9 or (outside >= 9 and g.length < STUB * K):
                o.kind = 'drop'
                dropped += 1
            elif inside >= 9 and not runs_on(o):
                from .settings import inner_wall_head
                if inner_wall_head() == 'line border':
                    o.head = 'line border'
                    bordered += 1
    # join walls that run on from one another: one ends where the next
    # starts, or a little short of it and heading for it
    def end_dir(segs, at_end):
        """Which way the wall runs at its end (or start), over the last
        30 cm or so: a sketched wall wobbles right at its end."""
        d = bezier_points(segs, 8)
        if at_end:
            return _mul(_tangent(d, len(d) - 1, 0.3 * K, False), -1)
        return _tangent(d, 0, 0.3 * K, True)

    score = _outline_score(objs)
    # spurs (a short wall with one end free, off another's end) and
    # presumed walls bridging less than BRIDGE between two walls go, so the
    # walls either side can join up
    walls = [o for o in objs if o.kind == 'line' and o.head.startswith('line wall')
             and '-close on' not in o.head and ' -id ' not in o.head + ' ' and len(o.segments()) > 1]
    for o in walls:
        sg = o.segments()
        e0, e1 = tuple(sg[0][-2:]), tuple(sg[-1][-2:])
        other = [tuple(w.segments()[k][-2:]) for w in walls if w is not o and w.kind != 'drop' for k in (0, -1)]
        n0 = sum(math.dist(e0, p) <= GAP * K for p in other)
        n1 = sum(math.dist(e1, p) <= GAP * K for p in other)
        length = LineString(bezier_points(sg)).length
        spur = length < STUB * K and (n0 == 0) != (n1 == 0)
        bridge = '-subtype presumed' in o.head and math.dist(e0, e1) < BRIDGE * K and n0 and n1
        if not (spur or bridge):
            continue
        o.kind = 'drop'
        new = _outline_score(objs)
        if new <= score:
            score = new
            dropped += 1
        else:
            o.kind = 'line'
    objs[:] = [o for o in objs if o.kind != 'drop']
    failed = set()
    while True:
        walls = [o for o in objs if o.kind == 'line' and o.head.startswith('line wall')
                 and '-close on' not in o.head and ' -id ' not in o.head + ' ' and len(o.segments()) > 1]
        ends = [(tuple(o.segments()[k][-2:]), o, k) for o in walls for k in (0, -1)]
        done = False
        for a in walls:
            sa = a.segments()
            end = tuple(sa[-1][-2:])
            # pieces off the outline don't stand in the way of outline walls
            near = [(math.dist(end, p), o, k) for p, o, k in ends
                    if not (o is a and k == -1) and math.dist(end, p) <= GAP * K
                    and ('-outline none' in a.head or '-outline none' not in o.head)]
            # the wall end there (or, where they meet exactly, the only one
            # at that point; else the nearest, if much the nearest), the
            # start of a wall of the same kind
            near.sort(key=lambda x: x[0])
            exact = [x for x in near if x[0] == 0]
            if exact:
                if len(exact) != 1:
                    continue
            elif not near or (len(near) > 1 and near[1][0] < 2 * near[0][0] + 0.05 * K):
                continue
            d, b, k = near[0]
            key = (a.rows[0], a.rows[-1], b.rows[0], b.rows[-1])
            if k != 0 or b is a or b.head != a.head or key in failed:
                continue
            sb = [list(r) for r in b.segments()]
            old_a, old_kind = a.rows, b.kind
            if d == 0:
                segs = sa + sb[1:]
                _smooth_join(segs, len(sa) - 1)
            else:
                # the two as one: where one runs a little past the other's
                # end, cut that bit off, then refit the whole wall
                if _turn(end_dir(sa, True), end_dir(sb, False)) > 60:
                    continue
                pa, pb = bezier_points(sa, 8), bezier_points(sb, 8)
                q = pb[0]
                tail = [i for i in range(len(pa)) if math.dist(pa[i], pa[-1]) < GAP * K]
                i = min(tail, key=lambda i: math.dist(pa[i], q))
                head = [j for j in range(len(pb)) if math.dist(pb[j], pb[0]) < GAP * K]
                j = min(head, key=lambda j: math.dist(pb[j], pa[i]))
                pts = pa[:i + 1] + pb[j:]
                if len(pts) < 3 or not LineString(pts).is_simple:
                    continue
                from .settings import SETTINGS
                if SETTINGS['join_local']:
                    segs = _join_local(sa, sb, pa[i], pb[j], K)
                else:
                    segs = fit_wall([[x, y] for x, y in pts], K)
                    # keep the two outer ends exactly where they were
                    segs[0] = [sa[0][-2], sa[0][-1]]
                    if len(segs[-1]) == 6:
                        segs[-1][4:] = [sb[-1][-2], sb[-1][-1]]
                    else:
                        segs[-1] = [sb[-1][-2], sb[-1][-1]]
            g = LineString(bezier_points(segs, 20))
            ends_ab = [Point(sa[0][-2:]), Point(sb[-1][-2:])]
            others = [LineString(bezier_points(o.segments(), 20)) for o in walls if o is not a and o is not b]
            if not g.is_simple or any(min(e.distance(x) for e in ends_ab) > 1e-3
                                      for o in others if g.intersects(o)
                                      for x in getattr(g.intersection(o), 'geoms', [g.intersection(o)])):
                failed.add(key)
                continue
            a.set_segments(segs)
            b.kind = 'drop'
            new = _outline_score(objs)
            if new <= score:
                score = new
                joined += 1
                done = True
                failed.clear()      # what failed may work now
                break
            a.rows, b.kind = old_a, old_kind
            failed.add(key)
        if not done:
            break
    objs[:] = [o for o in objs if o.kind != 'drop']
    return dropped, bordered, joined


def outline_sound_now(objs):
    """How many of the scrap's outlines (as Therion will join them) are
    simple and turn once (MetaPost's turning number 1)."""
    out = [o for o in objs if o.kind == 'line' and len(o.segments()) > 1 and '-close on' not in o.head
           and o.head.startswith('line wall') and '-outline none' not in o.head and '-subtype invisible' not in o.head]
    ol = [bezier_points(o.segments(), 20) for o in out]
    good = 0
    for ring in therion_rings(ol):
        pts = [p for i, r in ring for p in (ol[i][::-1] if r else ol[i])]
        segs = [reverse_segments(out[i].segments()) if r else out[i].segments() for i, r in ring]
        good += 1 if ring_ok(pts)[0] and abs(mp_turning(segs)) == 1 else 0
    return good


def _wall_tol(header, objs, K, path):
    """How closely each wall of a scrap is refitted (metres): for a
    cross section, in proportion to its size; otherwise, with [convert]
    wall_tol_rel, in proportion to the legs nearby (scale.py); else TOL."""
    from .settings import SETTINGS
    from . import scale
    if '-projection none' in header and SETTINGS['section_tol_rel']:
        pts = [p for o in objs if o.kind == 'line' for p in bezier_points(o.segments(), 4)]
        if pts:
            size = max(max(x for x, _ in pts) - min(x for x, _ in pts), max(y for _, y in pts) - min(y for _, y in pts)) / K
            t = min(TOL, SETTINGS['section_tol_rel'] * size)
            return lambda o: t
        return None
    if not SETTINGS['wall_tol_rel']:
        return None
    from .survey import survey_of
    survey = survey_of(path)
    if not survey:                      # a copy outside the survey's folder: the scrap's name says
        from .. import project
        m = re.match(r'scrap (\S+)', header)
        prefix = project.load().names['scrap_prefix'].replace('{survey}', '(\\w+?)')
        mm = re.match(prefix + r'[PE]\d', m.group(1)) if m else None
        survey = mm.group(1) if mm else ''
    legs = scale.legs_of_scrap(objs, path, survey)
    if not legs:
        return None
    scale.use(legs, K)

    def tol(o):
        pts = bezier_points(o.segments(), 4)
        return scale.tol(pts[len(pts) // 2], SETTINGS['wall_tol_rel'], TOL)
    return tol


def _areas_to_outline(objs, K, over, simplify):
    """Areas (not water) kept to the outline the walls make, run `over` m over
    it at most: the fill they were made in can reach past the walls, and the
    bit outside only makes odd shapes. Returns how many changed."""
    from .walls import bezier_closed
    out = [o for o in objs if o.kind == 'line' and len(o.segments()) > 1 and '-close on' not in o.head
           and o.head.startswith('line wall') and '-outline none' not in o.head and '-subtype invisible' not in o.head]
    ol = [bezier_points(o.segments(), 12) for o in out]
    polys = []
    for ring in therion_rings(ol):
        pts = [p for i, r in ring for p in (ol[i][::-1] if r else ol[i])]
        if len(pts) > 3:
            polys.append(Polygon(pts).buffer(0))
    if not polys:
        return 0
    from shapely.ops import unary_union
    room = unary_union(polys).buffer(over * K, join_style=1)
    n = 0
    for o in objs:
        if o.kind != 'line' or '-id' not in o.head or '-close on' not in o.head or '-water' in o.head:
            continue
        pts = bezier_points(o.segments(), 8)
        if len(pts) < 4:
            continue
        a = Polygon(pts).buffer(0)
        b = a.intersection(room).buffer(0)
        if b.is_empty:
            continue
        if b.area > 0.98 * a.area and a.difference(room).area < 0.01 * a.area:
            continue
        if b.geom_type == 'MultiPolygon':
            b = max(b.geoms, key=lambda q: q.area)
        r = 2 * simplify * K                 # notches closed, few nodes, a spline (as marks.py)
        b = b.buffer(r, join_style=1).buffer(-r, join_style=1).intersection(room).buffer(0)
        if b.geom_type == 'MultiPolygon':
            b = max(b.geoms, key=lambda q: q.area)
        if b.geom_type != 'Polygon' or b.is_empty:
            continue
        rows = None
        for f in (1.0, 0.5, 0.25, 0.12):     # a spline bulges between its points: more points until it fits
            ring = list(b.simplify(f * simplify * K).exterior.coords)[:-1]
            if len(ring) < 3:
                continue
            rows = bezier_closed(ring, lambda p: p)
            spline = Polygon(bezier_points(Obj('line', '', rows).segments(), 12)).buffer(0)
            if spline.difference(room.buffer(0.05 * K)).area < 0.01 * spline.area:
                break
        if rows is None:
            continue
        o.rows = rows
        n += 1
    return n


MIN_RUN = 0.5       # m: a shorter stretch of one wall subtype goes with its neighbour


SAND_STEEP = 0      # degrees: an elevation wall steeper than this is not sand (0: off; GoSouth's
                    # rift sides plain wall, but Connection's shaft below 1 sand: asked)


def wall_subtypes(objs, K, near=0.15):
    """Wall segments lying along a stroke recorded by convert.subtype_marks
    get that subtype: a wall whose kind changes along it is cut into one
    line per kind, each `line wall -subtype X` (plain `line wall` for rock),
    never a `subtype` on a point. Returns how many walls were cut or typed."""
    from .settings import SETTINGS
    marks = []
    for o in objs:
        if o.kind != 'text':
            continue
        for line in o.raw.split('\n'):
            m = re.match(r'\s*# wall-subtype (\w+)(?: ([\d.]+))?: (.*)', line)
            if m:
                v = [float(x) for x in m.group(3).split()]
                reach = float(m.group(2)) if m.group(2) else near
                if len(v) >= 4:
                    marks.append((m.group(1), LineString(list(zip(v[0::2], v[1::2]))).buffer(reach * K)))
    if not marks:
        return 0
    n = 0
    out = []
    for o in objs:
        if o.kind != 'line' or not o.head.startswith('line wall') or '-subtype' in o.head or len(o.segments()) < 2:
            out.append(o)
            continue
        segs = o.segments()
        kinds, lens = [], []
        for i in range(1, len(segs)):
            pts = bezier_points([segs[i - 1][-2:], segs[i]], 4)
            mid = pts[len(pts) // 2] if len(pts) > 2 else \
                ((pts[0][0] + pts[-1][0]) / 2, (pts[0][1] + pts[-1][1]) / 2)
            kd = next((kd for kd, zone in marks if zone.contains(Point(mid))), 'bedrock')
            a, b = segs[i - 1][-2:], segs[i][-2:]
            if kd == 'sand' and SETTINGS.get('_elevation') and SAND_STEEP and \
                    abs(b[1] - a[1]) > math.tan(math.radians(SAND_STEEP)) * abs(b[0] - a[0]):
                kd = 'bedrock'                 # sand lies on floors, not up a steep wall (GoSouth's rift)
            kinds.append(kd)
            lens.append(math.dist(segs[i - 1][-2:], segs[i][-2:]))
        if all(k == 'bedrock' for k in kinds):
            out.append(o)
            continue
        # runs of one kind; a run shorter than MIN_RUN takes the kind before it (or after, at the start)
        runs = []
        for k, L in zip(kinds, lens):
            if runs and runs[-1][0] == k:
                runs[-1][1] += 1
                runs[-1][2] += L
            else:
                runs.append([k, 1, L])
        changed = True
        while changed and len(runs) > 1:
            changed = False
            for j, r in enumerate(runs):
                if r[2] < MIN_RUN * K:
                    into = runs[j - 1] if j else runs[j + 1]
                    into[1] += r[1]
                    into[2] += r[2]
                    runs.pop(j)
                    for a in range(len(runs) - 1, 0, -1):        # neighbours now of one kind
                        if runs[a][0] == runs[a - 1][0]:
                            runs[a - 1][1] += runs[a][1]
                            runs[a - 1][2] += runs[a][2]
                            runs.pop(a)
                    changed = True
                    break
        # one line per run, the subtype on the line (never on a point: hard to follow when editing)
        opts = o.head[len('line wall'):]
        start = 0
        for k, cnt, _ in runs:
            piece = Obj('line', 'line wall' + ('' if k == 'bedrock' else f' -subtype {k}') + opts, [])
            piece.set_segments([list(segs[start][-2:])] + [list(sg) for sg in segs[start + 1:start + cnt + 1]])
            out.append(piece)
            start += cnt
        n += 1
    objs[:] = out
    return n


def survey_shots(objs, K, path, survey, elevation):
    """The survey round a scrap, in its units: ({station: (x, y)}, [(a, b)]
    legs, {station: [splay end (x, y)]}), from the drawing's sketch. In an
    elevation the splay ends are those straight up and down. None where
    there is no survey data."""
    from .roofs import Splays
    splays = Splays.from_drawing(path, survey)
    if not splays.legs:
        return None
    st = {}
    for o in objs:
        m = re.match(r'point (\S+) (\S+) station\b.*-name (\S+)', o.head) if o.kind == 'point' else None
        if m:
            n = m.group(3)
            st[n if '@' in n else f'{n}@{survey}'] = (float(m.group(1)), float(m.group(2)))
    legs = sorted({tuple(sorted((a, b))) for a in st for b in splays.legs.get(a, ()) if b in st})
    ends = {}
    for n, (x, y) in st.items():
        if elevation:
            ends[n] = ([(x, y + K * splays.up[n])] if n in splays.up else []) + \
                ([(x, y - K * splays.down[n])] if n in splays.down else [])
        else:
            ends[n] = [(x + K * dx, y + K * dy) for dx, dy in splays.ends.get(n, ())]
    return st, legs, ends


LEG_REACH = 6.0     # m: the legs a line belongs to are within this of it
LEG_BAND = 1.5      # m: legs this much further from a line than the nearest are another passage's
ON_LINE = 0.6       # m: a station this close to a line doesn't say which side the passage is
BEYOND = 0.5        # m: a splay reaching further than this past a line shows passage beyond it
SPLAY_MEASURED = 0.3  # m: a vertical splay ending this near a line was measured to it (elevations)


SIDE_RUN = 1.0      # m: a line is split where its nearest leg changes side for at least this far


def split_by_side(objs, K, st, legs):
    """A border, or a wall with -outline none, that is the roof of one
    passage and then the floor of the next (Trident: the roof from 8 to 10
    drawn on as the floor of the ramp to 12) is split where its nearest leg
    goes from one side of it to the other, so each piece is judged alone."""
    if not legs:
        return
    segs = [((a, b), LineString([st[a], st[b]])) for a, b in legs if st[a] != st[b]]
    new = []
    for o in objs:
        if o.kind != 'line' or len(o.segments()) < 3 or not (
                o.head.strip() in ('line border', 'line border -clip off')
                or (o.head.startswith('line wall') and '-outline none' in o.head)):
            new.append(o)
            continue
        rows = o.segments()
        nodes = [tuple(r[-2:]) for r in rows]
        sides = []
        for i, p in enumerate(nodes):
            a, b = nodes[max(0, i - 1)], nodes[min(len(nodes) - 1, i + 1)]
            q = min(segs, key=lambda sg: sg[1].distance(Point(p)))[1]
            far = max((Point(q.coords[0]), Point(q.coords[-1])), key=lambda e: e.distance(Point(p)))
            sides.append(1 if (b[0] - a[0]) * (far.y - a[1]) - (b[1] - a[1]) * (far.x - a[0]) > 0 else -1)
        cuts = [0]
        for i in range(1, len(nodes)):
            if sides[i] != sides[cuts[-1]]:
                # a change that lasts: the next SIDE_RUN of the line keeps the new side
                j = i
                while j < len(nodes) and sides[j] == sides[i]:
                    j += 1
                run = sum(math.dist(nodes[k], nodes[k + 1]) for k in range(i, min(j, len(nodes) - 1)))
                if run >= SIDE_RUN * K and i - cuts[-1] >= 2:
                    cuts.append(i)
        if len(cuts) == 1:
            new.append(o)
            continue
        cuts.append(len(rows) - 1)
        for a, b in zip(cuts, cuts[1:]):
            piece = [list(rows[a][-2:])] + [list(r) for r in rows[a + 1:b + 1]]
            if len(piece) > 1:
                x = Obj('line', o.head, [])
                x.set_segments(piece)
                new.append(x)
    objs[:] = new


LINK_REACH = 0.15   # m: a piece off the outline with each end this near an outline wall's end links them
SPLAY_ON = 0.2      # m: splays from a station this near a line don't show passage beyond it
END_JOIN = 0.3      # m: wall ends nearer than this are made one point (after smoothing)
END_MARGIN = 1.0    # m: a station whose nearest point on a line is this near its end doesn't vote (TridentLeft 9: 0.8 m)


def _passage(objs):
    """The passage as the outline walls make it now (Polygon), or None."""
    outline = [bezier_points(o.segments(), 20) for o in objs if o.kind == 'line' and len(o.segments()) > 1
               and '-close on' not in o.head and o.head.startswith('line wall')
               and '-outline none' not in o.head and '-subtype invisible' not in o.head]
    out = None
    for ring in therion_rings(outline):
        pts = [p for i, rev in ring for p in (outline[i][::-1] if rev else outline[i])]
        if len(pts) > 3:
            g = Polygon(pts).buffer(0)
            out = g if out is None else out.union(g)
    return out


def judge(o, objs, K, survey):
    """A line by the legs it belongs to (see outer_lines): None if it has
    none, 'inner' if they lie on both sides of it or their splays reach past
    it, else the side (+1 left, -1 right) its passage is on."""
    st, legs, ends = survey
    pts = bezier_points(o.segments())
    g = LineString(pts)
    if g.length < 0.05 * K:
        return None
    from shapely.ops import nearest_points, unary_union
    others = unary_union([LineString(bezier_points(x.segments())) for x in objs
                          if x is not o and x.kind == 'line' and len(x.segments()) > 1
                          and x.head.split()[1] in ('wall', 'border') and '-subtype invisible' not in x.head])

    def sees(a, b):                              # no other wall or border between the leg and the line
        p, q = nearest_points(LineString([st[a], st[b]]), g)
        if p.distance(q) < 0.05 * K:
            return True
        gap = LineString([p, q])
        cut = gap.intersection(others)
        return cut.is_empty or all(c.distance(q) < 0.1 * K for c in getattr(cut, 'geoms', [cut]))
    dist = {(a, b): LineString([st[a], st[b]]).distance(g) for a, b in legs}
    mine = [(a, b) for a, b in legs if dist[(a, b)] < LEG_REACH * K and sees(a, b)]
    if not mine:
        return None
    nearest = min(dist[l] for l in mine)
    from .settings import SETTINGS
    if not SETTINGS.get('_elevation'):
        mine = [l for l in mine if dist[l] <= nearest + LEG_BAND * K]     # its own passage, not one beyond
    # (in an elevation a passage seen across the line with nothing between is the passage below
    # or above: the line is inner, the floor of one and the roof of the other, Connection 21-23)

    def side(q):                                 # +1 left of the line, -1 right, at its nearest part
        d = g.project(Point(q))
        a, b = g.interpolate(max(0, d - 0.05 * K)), g.interpolate(min(g.length, d + 0.05 * K))
        c = (b.x - a.x) * (q[1] - a.y) - (b.y - a.y) * (q[0] - a.x)
        return 1 if c > 0 else -1

    def foot_on(q):                              # q lies across the line, not off its ends
        d = g.project(Point(q))                  # (nor by an end, where it meets the next wall: TridentLeft 9)
        m = max(0.02 * g.length, min(END_MARGIN * K, 0.2 * g.length))
        return m < d < g.length - m
    # stations clearly to one side (a station the line was sketched just over doesn't count)
    near = {x for a, b in mine for x in (a, b)}
    votes = [side(st[x]) for x in near if foot_on(st[x]) and g.distance(Point(st[x])) > ON_LINE * K]
    by_legs = not votes
    if by_legs:
        votes = [side(LineString([st[a], st[b]]).interpolate(0.5, normalized=True).coords[0]) for a, b in mine]
    left, right = votes.count(1), votes.count(-1)
    if by_legs and min(left, right) >= max(1, 0.3 * len(votes)):
        # legs either side, no station to say: the leg along the line decides (TridentLeft 38:
        # 35 to 38 down the passage, 34 to 35 across the rock beyond, hand edit)
        a, b = min(mine, key=lambda l: dist[l])
        left, right = (1, 0) if side(LineString([st[a], st[b]]).interpolate(0.5, normalized=True).coords[0]) > 0 \
            else (0, 1)
    if SETTINGS.get('_elevation'):
        # the floor or roof the splays straight up or down were measured to, from one side only
        # (none from the other side reaching it): that side's wall (BoldStep 1 and 4, the floor
        # of 0 to 4 over the passage at 5 and 6, user)
        reach = {x for a, b in mine for x in (a, b)} | {x for x in st if g.distance(Point(st[x])) < LEG_REACH * K}
        on = [x for x in reach for e in ends.get(x, ()) if g.distance(Point(e)) < SPLAY_MEASURED * K
              and 0.02 * g.length < g.project(Point(e)) < 0.98 * g.length
              and g.distance(Point(st[x])) > SPLAY_ON * K]
        sides = {side(st[x]) for x in on}
        if len(set(on)) >= 2 and len(sides) == 1:
            s1 = sides.pop()
            short = [x for x in reach if side(st[x]) == -s1 and any(
                LineString([st[x], e]).distance(g) < SPLAY_MEASURED * K for e in ends.get(x, ()))]
            if not short:
                return s1
    if min(left, right) >= max(1, 0.3 * len(votes)):
        return 'inner'
    here = 1 if left >= right else -1
    # a splay reaching past the line: the shot crosses it (a splay ending on the far side of a
    # winding or short line without crossing it doesn't count: TridentLeft 9, 26, 35, hand edit)
    beyond = [e for a, b in mine for x in (a, b) for e in ends.get(x, ())
              if g.distance(Point(e)) > BEYOND * K and LineString([st[x], e]).crosses(g)
              and g.distance(Point(st[x])) > SPLAY_ON * K]      # (from a station on the line: TridentLeft 35)
    if beyond:
        # ending in the drawn passage: a splay into passage not drawn (up an aven) doesn't make
        # the line inner (Connection 15, the wall up to 16, user)
        drawn = _passage(objs)
        beyond = [e for e in beyond if drawn is None or drawn.buffer(0.3 * K).contains(Point(e))]
    if beyond:
        return 'inner'
    # a station on the line: its splays reaching well out on both sides, into the drawn passage,
    # show passage both sides (Connection 15, hand edit: inner; TridentLeft 35, the wall through it)
    drawn = None
    for x in near:
        if g.distance(Point(st[x])) > SPLAY_ON * K:
            continue
        if drawn is None:
            drawn = _passage(objs) or Polygon()
        # (a splay into passage not drawn yet doesn't count: TridentLeft 35, 36 and 37 beyond)
        # across the line's own length (not off its ends: TridentLeft 35, the passage south of it
        # is beyond the line's end)
        across = lambda e: 0.02 * g.length < g.project(Point(e)) < 0.98 * g.length
        far = [side(e) for e in ends.get(x, ()) if g.distance(Point(e)) > BEYOND * K and across(e)
               and drawn.buffer(0.3 * K).contains(Point(e))]
        if far.count(1) >= 1 and far.count(-1) >= 1:
            return 'inner'
    return here


def join_pieces(objs, K):
    """Wall pieces off the outline (`-outline none`) that end within
    LINK_REACH of each other, with no third line ending there, are one wall
    turning a corner: joined into one line at the meeting point (Style.md,
    Walls; TridentLeft 9, hand edit: the U round 9 and the wall from 5;
    a floor step or overhang ending there too ends on the joined node).
    Returns how many were joined."""
    n = 0
    while True:
        pieces = [o for o in objs if o.kind == 'line' and o.head.startswith('line wall') and '-outline none' in o.head
                  and '-close on' not in o.head and len(o.segments()) > 1]
        ends = [(o, k, tuple(o.segments()[k][-2:])) for o in objs if o.kind == 'line' and len(o.segments()) > 1
                and '-close on' not in o.head and o.head.split()[1] == 'wall'      # (steps end on the wall's node)
                for k in (0, -1)]
        found = None
        for i, a in enumerate(pieces):
            for b in pieces[i + 1:]:
                for ka in (0, -1):
                    for kb in (0, -1):
                        pa, pb = tuple(a.segments()[ka][-2:]), tuple(b.segments()[kb][-2:])
                        if math.dist(pa, pb) >= LINK_REACH * K:
                            continue
                        crowd = [e for e in ends if e[0] not in (a, b) and
                                 min(math.dist(e[2], pa), math.dist(e[2], pb)) < LINK_REACH * K]
                        if not crowd:
                            found = (a, ka, b, kb)
                            break
                    if found:
                        break
                if found:
                    break
            if found:
                break
        if not found:
            return n
        a, ka, b, kb = found
        sa = a.segments() if ka == -1 else reverse_segments(a.segments())
        sb = b.segments() if kb == 0 else reverse_segments(b.segments())
        m = ((sa[-1][-2] + sb[0][-2]) / 2, (sa[-1][-1] + sb[0][-1]) / 2)
        sa[-1] = list(sa[-1][:-2]) + [m[0], m[1]]
        rest = [list(r) for r in sb[1:]]
        a.set_segments(sa + rest)
        b.kind = 'drop'
        objs[:] = [o for o in objs if o.kind != 'drop']
        n += 1


GAP_JOIN = 1.0      # m: two free wall ends nearer than this, each the other's nearest, meet ...
GAP_TURN = 20.0     # degrees: ... if each wall heads this near the line to the other end (a gap in a
                    # wall: the walls run along it; at a continuation they are nearer square to it)
WALL_TURN = 90.0    # degrees: a wall of 3 or 4 nodes merges into the one it meets if the join turns less


def _wall_lines(objs):
    return [o for o in objs if o.kind == 'line' and o.head.startswith('line wall') and len(o.segments()) > 1
            and '-close on' not in o.head and '-outline none' not in o.head]


def _set_end(o, k, p):
    segs = [list(x) for x in o.segments()]
    segs[k][-2:] = [p[0], p[1]]
    o.set_segments(segs)


def _heads_to(e, q, K):
    """True if the wall at end e = (line, 0 or -1, point) heads, over its
    last 0.3 m, within GAP_TURN of the point q."""
    o, k, p = e
    pts = bezier_points(o.segments(), 8)
    pts = pts if k == -1 else pts[::-1]
    back = next((x for x in reversed(pts[:-1]) if math.dist(x, p) >= 0.3 * K), pts[0])
    u = (p[0] - back[0], p[1] - back[1])
    v = (q[0] - p[0], q[1] - p[1])
    if u == (0.0, 0.0) or v == (0.0, 0.0):
        return False
    return abs(_red(_arg(v) - _arg(u))) <= GAP_TURN


def close_gaps(objs, K):
    """Small gaps between walls closed (Style.md, Walls; Connection, user):
    two free wall ends (no other wall end at them) nearer than GAP_JOIN,
    each the other's nearest and each wall heading within GAP_TURN of the
    other end, meet at their midpoint, where the outline is no worse for
    it. Returns how many."""
    n = 0
    walls = _wall_lines(objs)
    ends = [(o, k, tuple(o.segments()[k][-2:])) for o in walls for k in (0, -1)]
    free = [e for e in ends if not any(f[0] is not e[0] and math.dist(f[2], e[2]) < 0.01 * K for f in ends)]
    used = set()
    for a in free:
        if id(a) in used:
            continue
        cand = [b for b in free if b is not a and b[0] is not a[0] and id(b) not in used]
        if not cand:
            continue
        b = min(cand, key=lambda b: math.dist(a[2], b[2]))
        d = math.dist(a[2], b[2])
        if d >= GAP_JOIN * K:
            continue
        back = min((c for c in free if c is not b and c[0] is not b[0]), key=lambda c: math.dist(b[2], c[2]))
        if back is not a:
            continue                                  # not each other's nearest
        if not (_heads_to(a, b[2], K) and _heads_to(b, a[2], K)):
            continue                                  # not running along the gap: a continuation
        before = _outline_score(objs)
        rows = (a[0].rows, b[0].rows)
        m = ((a[2][0] + b[2][0]) / 2, (a[2][1] + b[2][1]) / 2)
        _set_end(a[0], a[1], m)
        _set_end(b[0], b[1], m)
        if _outline_score(objs) > before:
            a[0].rows, b[0].rows = rows
            continue
        used |= {id(a), id(b)}
        n += 1
    return n


SLIVER = 0.05       # m: a wall piece shorter than this on another's end goes


def merge_walls(objs, K):
    """Walls of one kind meeting end to end merged into one line (Style.md,
    merge_short; Connection, user): always one of 2 nodes, one of 3 or 4
    if the join turns less than WALL_TURN, where the outline is no worse.
    Returns how many were merged."""
    n = 0
    changed = True
    while changed:
        changed = False
        walls = sorted(_wall_lines(objs), key=lambda o: len(o.segments()))
        for o in walls:
            so = o.segments()
            if len(so) > 4:
                break
            for w in walls:
                if w is o or w.head != o.head:
                    continue
                sw = w.segments()
                hit = next(((we, oe) for we in (0, -1) for oe in (0, -1)
                            if math.dist(sw[we][-2:], so[oe][-2:]) < 0.01 * K), None)
                if hit is None:
                    continue
                # a third wall ending there too: a junction, not a run on
                p = sw[hit[0]][-2:]
                if any(x not in (o, w) and any(math.dist(x.segments()[k][-2:], p) < 0.01 * K for k in (0, -1))
                       for x in _wall_lines(objs)):
                    continue
                first = sw if hit[0] == -1 else reverse_segments(sw)
                second = so if hit[1] == 0 else reverse_segments(so)
                pts = bezier_points(so, 8)
                if sum(math.dist(a, b) for a, b in zip(pts, pts[1:])) < SLIVER * K:
                    o.kind = 'drop'                  # a sliver on the end of a wall: not drawn (TritonNorth)
                    objs[:] = [x for x in objs if x.kind != 'drop']
                    n += 1
                    changed = True
                    break
                if len(so) > 2:
                    a = bezier_points(first, 8)
                    b = bezier_points(second, 8)
                    u = (a[-1][0] - a[-3][0], a[-1][1] - a[-3][1])
                    v = (b[2][0] - b[0][0], b[2][1] - b[0][1])
                    if abs(_red(_arg(v) - _arg(u))) >= WALL_TURN:
                        continue
                before = _outline_score(objs)
                rows, wrows = o.rows, w.rows
                # keep the direction of the longer (its passage on the left)
                w.set_segments(list(first) + [list(r) for r in second[1:]])
                if hit[0] == 0:
                    w.set_segments(reverse_segments(w.segments()))
                o.kind = 'drop'
                if _outline_score(objs) > before:
                    o.kind, w.rows = 'line', wrows
                    continue
                objs[:] = [x for x in objs if x.kind != 'drop']
                n += 1
                changed = True
                break
            if changed:
                break
    return n


STRAY = 0.5         # m: a wall shorter than this touching no other wall is a stray mark


def stray_walls(objs, K):
    """Walls under STRAY long joined end to end with no other wall (free, or
    a spur off another's middle): a stray mark, which Therion would make an outline of its own (one that can't
    turn: MetaPost warns it crosses itself; TritonNorth 14). Dropped.
    Returns how many."""
    walls = [o for o in objs if o.kind == 'line' and o.head.startswith('line wall') and len(o.segments()) > 1
             and '-close on' not in o.head]
    lines = {id(o): LineString(bezier_points(o.segments())) for o in walls}
    n = 0
    for o in walls:
        g = lines[id(o)]
        if g.length >= STRAY * K:
            continue
        ends = [Point(g.coords[0]), Point(g.coords[-1])]
        # joined end to end with another wall: part of a wall, kept (a spur off a wall's middle is not)
        if any(min(e.distance(Point(lines[id(w)].coords[k])) for k in (0, -1)) < 0.1 * K
               for w in walls if w is not o for e in ends):
            continue
        o.kind = 'drop'
        n += 1
    objs[:] = [o for o in objs if o.kind != 'drop']
    return n


def same_way_round(objs):
    """Walls round each outline all run the same way, the passage on their
    left: a wall Therion has to take backwards to make the outline (most of
    it, by length, going the other way) is reversed (Style.md, Walls;
    TridentLeft 27: a short piece by the junction, start to start with the
    wall beside it). Not walls with -reverse on (hand edits). Returns how
    many were reversed."""
    outline = [o for o in objs if o.kind == 'line' and len(o.segments()) > 1 and '-close on' not in o.head
               and o.head.startswith('line wall') and '-outline none' not in o.head
               and '-subtype invisible' not in o.head]
    pts = [bezier_points(o.segments(), 20) for o in outline]
    n = 0
    for ring in therion_rings(pts):
        if len(ring) < 2:
            continue
        L = lambda i: LineString(pts[i]).length
        back = sum(L(i) for i, rev in ring if rev)
        fwd = sum(L(i) for i, rev in ring if not rev)
        if back == fwd:
            continue
        for i, rev in ring:
            if rev == (back < fwd) and '-reverse on' not in outline[i].head:
                outline[i].set_segments(reverse_segments(outline[i].segments()))
                n += 1
    return n


def outer_lines(objs, K, survey):
    """Style.md: every outer line is a wall. A line the converter made a
    border, or a wall with `-outline none`, is judged by the legs it
    belongs to (within LEG_REACH): it is inner (a border) only where legs
    lie on both sides of it, or splays from those legs' stations reach
    more than BEYOND past it; otherwise it is the edge of that passage, a
    wall, drawn with the passage (the legs) on its left (its points
    reversed, not -reverse on). Passages drawn over one another in one
    scrap don't count as passage beyond each other. Returns how many
    became walls."""
    if survey is None:
        return 0
    st, legs, ends = survey
    n = 0
    from .settings import SETTINGS
    if SETTINGS.get('_elevation'):              # (the roof of one passage drawn on as the floor of the next)
        split_by_side(objs, K, st, legs)
    for o in list(objs):                            # (tee_joins may split walls in objs)
        if o.kind != 'line' or len(o.segments()) < 2 or not any(x is o for x in objs):
            continue
        if not (o.head.strip() in ('line border', 'line border -clip off')
                or (o.head.startswith('line wall') and '-outline none' in o.head)):
            continue
        verdict = judge(o, objs, K, survey)
        if verdict is None:
            continue
        if verdict == 'inner':
            if o.head.startswith('line wall'):
                o.head = 'line border'
            continue
        here = verdict
        rows, before = o.rows, _outline_score(objs)
        o.head = 'line wall'
        if here < 0:                                 # the passage on its right: drawn the other way
            o.set_segments(reverse_segments(o.segments()))
        if _outline_score(objs) > before:            # the other way round, the passage on the other side?
            o.set_segments(reverse_segments(o.segments()))
            if _outline_score(objs) > before:
                o.set_segments(reverse_segments(o.segments()))      # back to the passage on its left
                # never made a border to mend the outline (Style.md, Walls): the crossing is mended
                # (a loop at a sharp turn, walls run on past a corner, a T), else reported
                if not (untangle(objs, K, before) or tee_joins(objs, o, K, before, survey)):
                    OUTER_KEPT.append(tuple(round(v) for v in o.segments()[0][-2:]))
        n += 1
    return n


LOOP_MAX = 2.0      # m (x K): a loop of a line shorter than this, where it crosses itself, is cut out
CORNER_TAIL = 1.5   # m (x K): two walls crossing this near an end of each meet at the crossing


def _cum(pts):
    out = [0.0]
    for p, q in zip(pts, pts[1:]):
        out.append(out[-1] + math.dist(p, q))
    return out


def _piece(o, t0, t1):
    """Rows of line o from distance t0 to t1 along it."""
    from .tidy import dense, wall_piece
    segs = o.segments()
    pts, idx = dense(segs)
    return wall_piece({'segs': segs, 'pts': pts, 'idx': idx, 'cum': _cum(pts)}, t0, t1)


def _self_loop(o, K):
    """(distance in, distance out) of the shortest loop where line o crosses
    itself, under LOOP_MAX; None if none."""
    from .tidy import dense, _cross
    pts, _ = dense(o.segments())
    cum = _cum(pts)
    best = None
    for i in range(len(pts) - 1):
        for j in range(i + 2, len(pts) - 1):
            if cum[j] - cum[i + 1] > LOOP_MAX * K:
                break
            q = _cross(pts[i], pts[i + 1], pts[j], pts[j + 1])
            if q is not None:
                a = cum[i] + math.dist(pts[i], q)
                b = cum[j] + math.dist(pts[j], q)
                if b - a > 1e-6 and (best is None or b - a < best[1] - best[0]):
                    best = (a, b)
    return best


def untangle(objs, K, before):
    """Mend an outline that crosses itself without changing what any line
    is (Style.md, Walls: no wall made a border to mend it): a small loop of
    a wall where it crosses itself (a sharp turn drawn as a curve) is cut
    out, and two walls crossing near an end of each (run on past a corner)
    are cut back to the crossing. Kept if the outline is then no worse than
    `before` and sound; else all put back. Returns True if mended."""
    walls = [x for x in objs if x.kind == 'line' and x.head.startswith('line wall')
             and '-outline none' not in x.head and '-close on' not in x.head and len(x.segments()) > 1]
    saved = [(x, x.rows) for x in walls]
    changed = False
    for w in walls:                                  # loops within a wall
        for _ in range(5):
            lp = _self_loop(w, K)
            if lp is None:
                break
            L = _cum(bezier_points(w.segments()))[-1]
            a = _piece(w, 0.0, lp[0])
            b = _piece(w, lp[1], L)
            w.set_segments(a + b[1:])
            changed = True
    for w in walls:                                  # a wall round the whole outline, its two ends run on past each other
        g = LineString(bezier_points(w.segments()))
        if g.length < 4 * CORNER_TAIL * K:
            continue
        head = LineString([g.interpolate(d) for d in [CORNER_TAIL * K * k / 20 for k in range(21)]])
        tail = LineString([g.interpolate(g.length - d) for d in [CORNER_TAIL * K * k / 20 for k in range(21)]])
        x = head.intersection(tail)
        if x.is_empty or x.geom_type != 'Point':
            continue
        t0, t1 = g.project(x), g.length - tail.project(x)
        if t1 - t0 > 2 * CORNER_TAIL * K:
            w.set_segments(_piece(w, t0, t1))
            changed = True
    for i, w in enumerate(walls):                    # walls run on past a corner
        for v in walls[i + 1:]:
            gw, gv = LineString(bezier_points(w.segments())), LineString(bezier_points(v.segments()))
            x = gw.intersection(gv)
            if x.is_empty or x.geom_type != 'Point':
                continue
            tw, tv = gw.project(x), gv.project(x)
            ew = 0 if tw < CORNER_TAIL * K else (-1 if gw.length - tw < CORNER_TAIL * K else None)
            ev = 0 if tv < CORNER_TAIL * K else (-1 if gv.length - tv < CORNER_TAIL * K else None)
            if ew is None or ev is None:
                continue
            cw = tw if ew == 0 else gw.length - tw
            cv = tv if ev == 0 else gv.length - tv
            if min(cw, cv) < 0.01 * K or gw.length < 2 * cw or gv.length < 2 * cv:
                continue
            w.set_segments(_piece(w, tw, gw.length) if ew == 0 else _piece(w, 0.0, tw))
            v.set_segments(_piece(v, tv, gv.length) if ev == 0 else _piece(v, 0.0, tv))
            changed = True
    if changed:
        now = _outline_score(objs)
        if (now <= before and now[:2] == (0, 0)) or now[:2] < before[:2]:
            return True
    for x, r in saved:
        x.rows = r
    return False


TEE_ON = 0.05       # m (x K): a line's end this near the middle of a wall meets it there
TEE_TAIL = 1.0      # m (x K): a line's end crossing a wall this near it is cut back to the wall


def _split_obj(w, at, K):
    """Two copies of line w split at its point nearest `at`, cut exactly out
    of its curves; None if that is at or near an end of it."""
    from .tidy import dense, wall_piece
    segs = w.segments()
    pts, idx = dense(segs)
    line = LineString(pts)
    t = line.project(Point(at))
    if t < 0.1 * K or t > line.length - 0.1 * K:
        return None
    cum = [0.0]
    for p, q in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.dist(p, q))
    d = {'segs': segs, 'pts': pts, 'idx': idx, 'cum': cum}
    a, b = Obj('line', w.head, raw=''), Obj('line', w.head, raw='')
    a.set_segments(wall_piece(d, 0.0, t))
    b.set_segments(wall_piece(d, t, cum[-1]))
    return a, b


def _cut_end(o, end, keep):
    """o's rows with the part past distance `keep` from its other end gone."""
    from .tidy import dense, wall_piece
    segs = o.segments()
    pp, idx = dense(segs)
    cum = [0.0]
    for p, q in zip(pp, pp[1:]):
        cum.append(cum[-1] + math.dist(p, q))
    d = {'segs': segs, 'pts': pp, 'idx': idx, 'cum': cum}
    o.set_segments(wall_piece(d, keep, cum[-1]) if end == 0 else wall_piece(d, 0.0, keep))


def _tee(objs, o, end, K):
    """(wall, point) where o's end meets a wall at a T, its end cut back to
    the wall if it crosses it just short of the end; None if it doesn't."""
    if len(o.segments()) < 2:
        return None
    g = LineString(bezier_points(o.segments()))
    e = Point(g.coords[end])
    for w in objs:
        if w is o or w.kind != 'line' or not w.head.startswith('line wall') or '-outline none' in w.head \
                or '-close on' in w.head or len(w.segments()) < 2:
            continue
        wl = LineString(bezier_points(w.segments()))
        if min(Point(wl.coords[0]).distance(e), Point(wl.coords[-1]).distance(e)) < 0.1 * K:
            continue                                      # end to end: Therion joins those itself
        if wl.distance(e) < TEE_ON * K:
            return w, wl.interpolate(wl.project(e))
        x = g.intersection(wl)
        pts = [q for q in getattr(x, 'geoms', [x]) if q.geom_type == 'Point']
        near = [q for q in pts if (g.project(q) if end == 0 else g.length - g.project(q)) < min(TEE_TAIL * K, g.length / 3)]
        if near:
            at = min(near, key=lambda q: q.distance(e))
            rows = o.rows
            _cut_end(o, end, g.project(at))
            if len(o.segments()) < 2:
                o.rows = rows
                continue
            return w, at
    return None


def tee_joins(objs, o, K, before, survey=None):
    """An outer line meeting a wall at a T (its end on the middle of the wall,
    or crossing it just short of its end) is made a wall there as a hand
    edit does it (Style.md, Walls: every outer line a wall; log row 139):
    its end cut back to the wall, the wall split at that point, and the
    piece of the wall then inside the passage a border (or both pieces
    walls, a T of three). Kept if the outline is then no worse than
    `before`, with o either way round; else all is put back. Returns True
    if kept."""
    saved = (list(objs), o.rows, [(x, x.head, x.rows) for x in objs])

    def restore():
        objs[:] = saved[0]
        o.rows = saved[1]
        for x, h, r in saved[2]:
            x.head, x.rows = h, r
    options = [[None]]
    for end in (0, -1):
        t = _tee(objs, o, end, K)
        if t is None:
            continue
        w, at = t
        parts = _split_obj(w, (at.x, at.y), K)
        if parts is None:
            continue
        a, b = parts
        k = objs.index(w)
        objs[k:k + 1] = [a, b]
        options.append([None])                            # both pieces stay walls (never made borders)
    if len(options) == 1:
        restore()
        return False
    import itertools
    for pick in itertools.product(*options[1:]):
        for x in pick:
            if x:
                x[0].head = 'line border'
        for rev in (False, True):
            now = _outline_score(objs)
            if now <= before and now[:2] == (0, 0):       # and sound: no outline crossing itself
                return True
            o.set_segments(reverse_segments(o.segments()))
        for x in pick:
            if x:
                x[0].head = x[1]
    restore()
    return False


OUTER_KEPT = []     # first points of outer walls where the outline still crosses itself (reported)


def no_outline_none(objs, K=1.0):
    """No wall with `-outline none` (Style.md): every outer line is a wall,
    and an inner line is drawn as what it is. Each left inside the passage
    becomes a `line border`; one that isn't becomes an outline wall where
    Therion still makes the outline as well as before, and a border where
    not. Returns the number changed."""
    n = 0
    rings = _rings_now(objs)
    outline = [bezier_points(o.segments(), 20) for o in objs if o.kind == 'line' and len(o.segments()) > 1
               and '-close on' not in o.head and o.head.startswith('line wall')
               and '-outline none' not in o.head and '-subtype invisible' not in o.head]
    passage = None
    for ring in rings:
        pts = [p for i, rev in ring for p in (outline[i][::-1] if rev else outline[i])]
        if len(pts) > 3:
            g = Polygon(pts).buffer(0)
            passage = g if passage is None else passage.union(g)
    for o in objs:
        if o.kind != 'line' or not o.head.startswith('line wall') or '-outline none' not in o.head:
            continue
        n += 1
        if len(o.segments()) < 2:
            o.kind = 'drop'
            continue
        # a short piece running on from the end of another line is that line's kind (it merges
        # into it: Style.md, merge_short; Connection 13 to 15, hand edit: a 2-node piece of a border)
        from .settings import SETTINGS
        so = o.segments()
        if SETTINGS['merge_short'] and len(so) <= SETTINGS['merge_short']:
            nb = next((x for x in objs if x is not o and x.kind == 'line' and len(x.segments()) > 1
                       and '-close on' not in x.head and '-outline none' not in x.head
                       and x.head.split()[1] in ('wall', 'border')
                       and any(math.dist(so[a][-2:], x.segments()[b][-2:]) < 0.05 * K
                               for a in (0, -1) for b in (0, -1))), None)
            if nb is not None and nb.head.split()[1] == 'border':
                o.head = nb.head
                continue
        g = LineString(bezier_points(o.segments()))
        inside = passage is not None and sum(passage.buffer(-0.05 * K).contains(g.interpolate(i / 10, normalized=True))
                                             for i in range(11)) >= 9
        if inside:
            o.head = 'line border'
            continue
        before = _outline_score(objs)
        o.head = o.head.replace(' -outline none', '')
        if _outline_score(objs) > before and not untangle(objs, K, before):
            OUTER_KEPT.append(tuple(round(v) for v in o.segments()[0][-2:]))   # a wall still: reported
    objs[:] = [o for o in objs if o.kind != 'drop']
    return n


SECTION_SPIKE = 0.03   # a section's spike: shorter than this share of its walls' length (with section_shape)
SHAPE_KEPT = 0.9       # a node removed (despike) or handle moved (fix_handles) keeps this share of the area
MIN_RING = 4           # ... and a closed wall at least this many distinct nodes


def _walls_of(objs):
    return [o for o in objs if o.kind == 'line' and o.head.startswith('line wall')
            and '-subtype invisible' not in o.head and len(o.segments()) > 1]


def _shape(objs, section):
    """Areas to keep: each closed wall's, and in a section the outline its
    walls enclose together (TridentLeft PX1: a section despiked to a sliver)."""
    from shapely.ops import polygonize, unary_union
    out, nodes = {}, {}
    for o in _walls_of(objs):
        if '-close on' in o.head:
            pts = bezier_points(o.segments(), 4)
            out[id(o)] = Polygon(pts).buffer(0).area if len(pts) > 3 else 0.0
            nodes[id(o)] = len({(round(s[-2], 1), round(s[-1], 1)) for s in o.segments()})
    if section:
        lines = [LineString(bezier_points(o.segments(), 4)) for o in _walls_of(objs)]
        out['outline'] = sum(p.area for p in polygonize(unary_union(lines))) if lines else 0.0
    return out, nodes


def _shape_kept(objs, section, before):
    """No closed wall (or section outline) losing more than 1 - SHAPE_KEPT of
    its area, nor a closed wall left with under MIN_RING distinct nodes."""
    (a0, n0), (a1, n1) = before, _shape(objs, section)
    if any(n1.get(k, 0) < min(MIN_RING, n) for k, n in n0.items()):
        return False
    return all(a1.get(k, 0.0) >= SHAPE_KEPT * a for k, a in a0.items())


def _redo_scrap(header, body, path):
    """One scrap through the wall refit and the steps after it.
    Returns (objs, tidy report, points before, after, ends moved)."""
    objs = parse_scrap(body)
    K = scale_of(header)
    from .settings import SETTINGS
    SETTINGS['_elevation'] = '-projection extended' in header
    joined = join_pieces(objs, K) if SETTINGS['outer_walls'] else 0
    tidy = one_line_per_wall(objs, K)
    stepped = joined
    if SETTINGS['outer_walls'] and '-projection none' not in header:
        from .survey import survey_of
        sv = survey_of(path) or (re.match(r'scrap (\S+?)S[PE]\d', header) or [None, ''])[1]
        OUTER_KEPT.clear()
        stepped += outer_lines(objs, K, survey_shots(objs, K, path, sv, SETTINGS['_elevation']))
    stepped += no_outline_none(objs, K)
    if SETTINGS['outer_walls']:
        before = _outline_score(objs)
        rows = [(o, o.rows) for o in objs if o.kind == 'line']
        if same_way_round(objs) and _outline_score(objs) > before:
            for o, r in rows:                        # (Therion would link the walls differently)
                o.rows = r
        stray = stray_walls(objs, K)
        if stray:
            import sys
            print(f"  {header.split()[1]}: {stray} stray wall mark(s) under {STRAY} m, touching no other wall, "
                  f"dropped", file=sys.stderr)
        score = _outline_score(objs)
        if score[:2] != (0, 0):                      # an outline still crossing: mended where it can be
            untangle(objs, K, score)
        stepped += close_gaps(objs, K)
        stepped += merge_walls(objs, K)
    if SETTINGS['drawn_rocks']:                  # rocks in every scrap, sections and elevations too
        from .details import pleasing_rocks
        pleasing_rocks(objs, K)
    if OUTER_KEPT and _outline_score(objs)[:2] != (0, 0):      # (mended since: not reported)
        import sys
        print(f"  {header.split()[1]}: {len(OUTER_KEPT)} outer wall(s) where the outline still crosses itself, "
              f"to check (passages over one another: separate scraps?) at "
              + ", ".join("%d %d" % p for p in OUTER_KEPT), file=sys.stderr)
        OUTER_KEPT.clear()
    if SETTINGS['wall_jog_max'] > 0:        # walls joined through the sketcher's steps (jogs.py),
        from .jogs import join_scrap        # before the refit so the join is smoothed too
        stepped = join_scrap(objs, K, SETTINGS['wall_jog_max'])
    b, a = smooth_scrap(objs, K, _wall_tol(header, objs, K, path))
    if SETTINGS['wall_jog_max'] > 0:        # borders broken where the sketcher missed (jogs.py)
        from .jogs import join_borders
        stepped += join_borders(objs, K)
    from . import scale
    from .survey import survey_of
    survey = survey_of(path) or (re.match(r'scrap (\S+?)S[PE]\d', header) or [None, ''])[1]
    legs = scale.legs_of_scrap(objs, path, survey)
    scale.use(legs, K)

    def at_line(o):                         # metres: the local scale at a line's middle, or None
        pts = bezier_points(o.segments(), 2)
        return scale.at(pts[len(pts) // 2]) if pts else None

    def rel_abs(rel, absolute, s):          # the larger of an absolute and a relative distance (metres)
        return max(absolute, rel * s) if rel and s else absolute
    gap = None
    if SETTINGS['node_gap'] or SETTINGS['node_gap_rel']:
        # no two nodes so close that they cannot be told apart and picked when editing (nodes.thin)
        from .nodes import thin_scrap
        gap = lambda o: rel_abs(SETTINGS['node_gap_rel'], SETTINGS['node_gap'], at_line(o))
        # a line may move no more than its own tolerance in losing a node: a sweep loses
        # its close nodes, a tight S bend keeps them (nodes.thin)
        wall = lambda o: o.head.startswith('line wall')
        err = lambda o: scale.tol(bezier_points(o.segments(), 2)[0],
                                  SETTINGS['wall_tol_rel'] if wall(o) else SETTINGS['line_tol_rel'],
                                  TOL if wall(o) else 0.04)
        stepped += thin_scrap(objs, K, gap, err, SETTINGS['node_gap'])
    if SETTINGS['wall_ends_meet'] or SETTINGS['wall_ends_meet_rel']:
        # walls the sketcher did not quite join (nodes.walls_meet)
        from .nodes import walls_meet
        sound0 = outline_sound_now(objs)
        near = lambda p: rel_abs(SETTINGS['wall_ends_meet_rel'], SETTINGS['wall_ends_meet'], scale.at(p))
        stepped += walls_meet(objs, K, near, legs, ok=lambda: outline_sound_now(objs) >= sound0)
    if SETTINGS['end_on_node']:             # lines ending at walls end on a wall node (nodes.py)
        from .nodes import snap_scrap, SNAP
        snap = (lambda o: max(SNAP, gap(o))) if gap else None
        stepped += snap_scrap(objs, K, snap)
    if gap:                                     # joins and snaps can leave nodes close again
        stepped += thin_scrap(objs, K, gap, err, SETTINGS['node_gap'])
    if SETTINGS['area_over_walls'] and SETTINGS['area_splines']:
        stepped += _areas_to_outline(objs, K, SETTINGS['area_over_walls'], SETTINGS['area_splines'])
    if SETTINGS['merge_short']:                 # short lines run into the line of their kind they meet
        from .nodes import merge_short
        reach = lambda p: rel_abs(SETTINGS['wall_ends_meet_rel'], max(SETTINGS['wall_ends_meet'], 0.05), scale.at(p))
        stepped += merge_short(objs, K, reach, 2, SETTINGS['merge_short'])
    if SETTINGS['ends_meet']:                   # lines of different kinds ending close together share the end
        from .nodes import ends_meet
        reach2 = lambda p: rel_abs(SETTINGS['wall_ends_meet_rel'], max(SETTINGS['wall_ends_meet'], 0.05), scale.at(p))
        stepped += ends_meet(objs, K, reach2)
    if SETTINGS['despike']:
        # no curve doubling back within a segment (a hook), and no wall turning right
        # back over a short way (an overshoot where strokes overlap): each fix can show
        # the next, so until nothing changes. Judged on the outline not crossing itself.
        from .nodes import fix_handles, despike
        short = SETTINGS['despike']
        section = SETTINGS['section_shape'] and '-projection none' in header
        if section:     # a section's spikes are short for its size, not for a passage's (TridentLeft PX1, PX10)
            short = min(short, SECTION_SPIKE * sum(LineString(bezier_points(o.segments(), 4)).length
                                                   for o in _walls_of(objs)) / K)
        for _ in range(5):
            q0 = _quality(objs)
            saved = [(o, o.rows) for o in objs if o.kind == 'line']
            shape0 = _shape(objs, section)
            k = fix_handles(objs, 0.02 * K)
            if _quality(objs)[0] < q0[0] or not _shape_kept(objs, section, shape0):
                for o, rows in saved:
                    o.rows = rows
                k = 0
            q1 = _quality(objs)[0]
            shape1 = _shape(objs, section)
            k += despike(objs, K, short,
                         ok=lambda: _quality(objs)[0] >= q1 and _shape_kept(objs, section, shape1))
            stepped += k
            if not k:
                break
    if SETTINGS['smooth_nodes']:                # control points either side of a node in line with it
        from .nodes import align_scrap
        stepped += align_scrap(objs, SETTINGS['smooth_nodes'])
    if SETTINGS['wall_subtypes']:               # walls drawn as mud or sand (brown in the sketch)
        stepped += wall_subtypes(objs, K)
    # every line has at least two points (Style.md, lint line-points): a step above may leave one
    short = [o for o in objs if o.kind == 'line' and len(o.segments()) < 2]
    objs[:] = [o for o in objs if not any(o is x for x in short)]
    stepped += len(short)
    return objs, tidy, b, a, stepped


def redo_file(path, scraps=None):
    """Refit the walls of the file's scraps (or those named in `scraps`)."""
    raw = open(path, 'rb').read()
    t = raw.decode('utf-8').replace('\r\n', '\n')
    out, pos, report = [], 0, []
    for m in re.finditer(r'^(scrap (\S+)[^\n]*)\n(.*?)^endscrap', t, re.S | re.M):
        header, name, body = m.group(1), m.group(2), m.group(3)
        if scraps and name not in scraps:
            continue
        objs, tidy, b, a, stepped = _redo_scrap(header, body, path)
        if LINKS_MADE and _quality(objs) < (len(_rings_now(objs)),) * 2:
            # a wall link (one_line_per_wall) may have spoilt the outline once refitted:
            # leave out any link whose absence gives a sounder outline
            made = list(LINKS_MADE)
            best = _quality(objs)
            for key in made:
                SKIP_LINKS.add(key)
                trial = _redo_scrap(header, body, path)
                if _quality(trial[0]) > best:
                    objs, tidy, b, a, stepped = trial
                    best = _quality(objs)
                else:
                    SKIP_LINKS.discard(key)
            SKIP_LINKS.clear()
        if a == b and not any(tidy) and not stepped:
            report.append((name, b, a) + tidy + (0,))
            continue
        out.append(t[pos:m.start(3)] + '\n'.join(o.text() for o in objs).rstrip('\n') + '\n')
        pos = m.end(3)
        report.append((name, b, a) + tidy + (stepped,))
    out.append(t[pos:])
    t = ''.join(out)
    # the converter's fill line, left where a scrap had no wall to refit: never written (lint wall-invisible)
    t = re.sub(r'(?m)^line wall -subtype invisible -close on\n(?:(?!endline).*\n)*?endline\n\n?', '', t)
    from .settings import SETTINGS
    if SETTINGS['outer_walls'] and out:     # wall ends that nearly meet, in a scrap or across a join: one point
        from .scraps import meet_ends
        k = scale_of(re.search(r'(?m)^scrap [^\n]*', t).group(0)) if re.search(r'(?m)^scrap ', t) else 0
        if k:
            t = meet_ends(t, END_JOIN * k, within=True)
            from .scraps import meet_on_walls     # a wall ending on another scrap's wall: at a node of it
            t = meet_on_walls(t, END_JOIN * k)
            from .scraps import drop_slivers
            t = drop_slivers(t, SLIVER * k)
    if b'\r\n' in raw:
        t = t.replace('\n', '\r\n')
    open(path, 'wb').write(t.encode('utf-8'))
    return report
