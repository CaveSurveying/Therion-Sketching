# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see tools/LICENSE.
"""Lines that end at a wall end on a node of it (tools/Style.md).

A border, step, pitch, overhang or gour that stops at a wall should end
exactly on one of the wall's points, so the two meet in Therion and in
xTherion. Each such end within `REACH` of a wall is moved onto the
wall's nearest node if one is within `SNAP`, else a node is inserted in
the wall there (a Bezier segment is split, so the wall keeps its shape)
and the end moved onto it.

Applied by `smooth` when tools/project.toml sets [convert] end_on_node.
"""
import math

REACH = 0.2        # m: an end this close to a wall is meant to meet it
SNAP = 0.05        # m: use an existing node this close rather than add one
TYPES = ('border', 'floor-step', 'pit', 'overhang', 'rimstone-dam', 'ceiling-step')


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _bezier(p0, c1, c2, p3, t):
    a, b, c = _lerp(p0, c1, t), _lerp(c1, c2, t), _lerp(c2, p3, t)
    d, e = _lerp(a, b, t), _lerp(b, c, t)
    return _lerp(d, e, t)


def split_segment(p0, seg, t):
    """Segment `seg` (from p0) split at t: two segments in th2 form."""
    p3 = (seg[-2], seg[-1])
    if len(seg) == 2:
        m = _lerp(p0, p3, t)
        return [m[0], m[1]], [p3[0], p3[1]]
    c1, c2 = (seg[0], seg[1]), (seg[2], seg[3])
    a, b, c = _lerp(p0, c1, t), _lerp(c1, c2, t), _lerp(c2, p3, t)
    d, e = _lerp(a, b, t), _lerp(b, c, t)
    m = _lerp(d, e, t)
    return [a[0], a[1], d[0], d[1], m[0], m[1]], [e[0], e[1], c[0], c[1], p3[0], p3[1]]


def nearest_on(segs, p, samples=24, step=2.0):
    """(distance, segment index, t, point) of the nearest point to p on a line.
    Each segment is sampled at least `samples` times and every `step`
    drawing units along its control polygon, so a long segment is measured
    as closely as a short one."""
    best = None
    prev = (segs[0][-2], segs[0][-1])
    for i, seg in enumerate(segs[1:], 1):
        poly = [prev] + ([(seg[0], seg[1]), (seg[2], seg[3])] if len(seg) == 6 else []) + [(seg[-2], seg[-1])]
        n = max(samples, int(sum(math.dist(a, b) for a, b in zip(poly, poly[1:])) / step))
        for k in range(n + 1):
            t = k / n
            q = _lerp(prev, (seg[-2], seg[-1]), t) if len(seg) == 2 else \
                _bezier(prev, (seg[0], seg[1]), (seg[2], seg[3]), (seg[-2], seg[-1]), t)
            d = math.dist(p, q)
            if best is None or d < best[0]:
                best = (d, i, t, q)
        prev = (seg[-2], seg[-1])
    return best


def _set_end(o, which, p):
    segs = [list(s) for s in o.segments()]
    if which == 0:
        dx, dy = p[0] - segs[0][-2], p[1] - segs[0][-1]
        segs[0][-2:] = [p[0], p[1]]
        if len(segs) > 1 and len(segs[1]) == 6:          # carry the first control point with it
            segs[1][0] += dx
            segs[1][1] += dy
    else:
        dx, dy = p[0] - segs[-1][-2], p[1] - segs[-1][-1]
        segs[-1][-2:] = [p[0], p[1]]
        if len(segs[-1]) == 6:
            segs[-1][2] += dx
            segs[-1][3] += dy
    o.set_segments(segs)


def snap_scrap(objs, K, snap=None):
    """Move line ends at walls onto wall nodes; returns how many. snap(wall),
    if given, is how near (metres) an existing node is used rather than a
    new one inserted (default SNAP)."""
    walls = [o for o in objs if o.kind == 'line' and o.head.split()[:2] == ['line', 'wall']
             and '-subtype invisible' not in o.head and len(o.segments()) > 1]
    n = 0
    for o in objs:
        words = o.head.split() if o.kind == 'line' else []
        if len(words) < 2 or words[1] not in TYPES or '-close on' in o.head or '-subtype invisible' in o.head:
            continue
        for which in (0, -1):
            segs = o.segments()
            if len(segs) < 2:
                break
            end = (segs[which][-2], segs[which][-1])
            hits = [(nearest_on(w.segments(), end), w) for w in walls]
            hits = [(h, w) for h, w in hits if h and h[0] <= REACH * K]
            if not hits:
                continue
            (d, i, t, q), w = min(hits, key=lambda hw: hw[0][0])
            nodes = [(s[-2], s[-1]) for s in w.segments()]
            node = min(nodes, key=lambda v: math.dist(v, q))
            if math.dist(node, q) <= (snap(w) if snap else SNAP) * K:
                target = node
            else:
                ws = [list(s) for s in w.segments()]
                a, b = split_segment((ws[i - 1][-2], ws[i - 1][-1]), ws[i], t)
                ws[i:i + 1] = [a, b]
                w.set_segments(ws)
                target = (a[-2], a[-1])
            if math.dist(target, end) > 1e-6:
                _set_end(o, which, target)
                n += 1
    return n


def walls_meet(objs, K, near, legs=(), body=REACH, ok=None):
    """Walls the sketcher did not quite join, joined: two wall ends within
    `near` m of each other (a number, or a function of the end's
    position) meet at their midpoint, and a wall end within
    `body` m of another wall's side ends on it (on a node, inserted if
    need be). A gap that crosses a survey leg runs across the passage
    (a squeeze) and is left alone. Only a wall that is not part of the
    outline (-outline none) is ended on another's side. `legs`: [(p, q)]
    in drawing units. `ok()`, if given, says whether the scrap's outline
    is still sound: a join that makes it unsound is undone.
    Returns how many ends moved."""
    from shapely.geometry import LineString
    legs = [LineString(l) for l in legs]
    walls = [o for o in objs if o.kind == 'line' and o.head.startswith('line wall')
             and '-subtype invisible' not in o.head and '-close on' not in o.head and len(o.segments()) > 1]

    def end(o, which):
        s = o.segments()[which]
        return (s[-2], s[-1])

    def across(a, b):
        g = LineString([a, b])
        return any(g.intersects(l) for l in legs)

    n = 0
    ends = [(o, w) for o in walls for w in (0, -1)]
    done = set()
    for i, (o, w) in enumerate(ends):
        if (id(o), w) in done:
            continue
        p = end(o, w)
        best = None
        reach = (near(p) if callable(near) else near) * K
        for o2, w2 in ends:
            if o2 is o or (id(o2), w2) in done:
                continue
            d = math.dist(p, end(o2, w2))
            if 1e-6 < d <= reach and (best is None or d < best[0]):
                best = (d, o2, w2)
        if best and not across(p, end(best[1], best[2])):
            _, o2, w2 = best
            q = end(o2, w2)
            m = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
            rows = (o.rows, o2.rows)
            _set_end(o, w, m)
            _set_end(o2, w2, m)
            if ok is not None and not ok():
                o.rows, o2.rows = rows
                continue
            done |= {(id(o), w), (id(o2), w2)}
            n += 2
    # ends left close to another wall's side (not an outline wall: ending
    # on another's side would make a T in the outline, which Therion
    # cannot follow)
    free = [(o, w) for o, w in ends if (id(o), w) not in done and '-outline none' in o.head]
    for o, w in free:
        p = end(o, w)
        if any(math.dist(p, end(o2, w2)) < 1e-6 for o2, w2 in ends if o2 is not o):
            continue                      # already meets a wall end
        hits = [(nearest_on(o2.segments(), p), o2) for o2 in walls if o2 is not o]
        hits = [(h, o2) for h, o2 in hits if h and 1e-6 < h[0] <= body * K]
        if not hits:
            continue
        (d, i, t, q), o2 = min(hits, key=lambda h: h[0][0])
        if across(p, q):
            continue
        nodes = [(s[-2], s[-1]) for s in o2.segments()]
        node = min(nodes, key=lambda v: math.dist(v, q))
        if math.dist(node, q) <= SNAP * K:
            target = node
        else:
            ws = [list(s) for s in o2.segments()]
            a, b = split_segment((ws[i - 1][-2], ws[i - 1][-1]), ws[i], t)
            ws[i:i + 1] = [a, b]
            o2.set_segments(ws)
            target = (a[-2], a[-1])
        rows = (o.rows, o2.rows)
        _set_end(o, w, target)
        if ok is not None and not ok():
            o.rows, o2.rows = rows
            continue
        n += 1
    return n


def _points(p0, seg, n=12):
    """Points along one segment (from p0), including both ends."""
    p3 = (seg[-2], seg[-1])
    if len(seg) == 2:
        return [_lerp(p0, p3, k / n) for k in range(n + 1)]
    return [_bezier(p0, (seg[0], seg[1]), (seg[2], seg[3]), p3, k / n) for k in range(n + 1)]


def _unit(a, b):
    d = math.dist(a, b)
    return ((b[0] - a[0]) / d, (b[1] - a[1]) / d) if d > 1e-9 else None


def merge(p0, a, b, maxerr=None):
    """Segments a (from p0) and b (from a's end) as one Bezier segment, fitted
    (least squares) to the shape of both, leaving and arriving as they did:
    a single cubic can follow a sweep or a gentle S. None if it strays more
    than maxerr (drawing units) from them."""
    from .smooth import _generate, _chord_params, _max_error, _reparam
    m = (a[-2], a[-1])
    d = _points(p0, a) + _points(m, b)[1:]
    p3 = d[-1]
    chord = math.dist(d[0], p3) or 1.0
    far = lambda pts: next((q for q in pts if math.dist(q, pts[0]) > 0.02 * chord), pts[-1])
    t1 = _unit(p0, (a[0], a[1])) if len(a) == 6 and math.dist(p0, (a[0], a[1])) > 0.02 * chord else None
    t1 = t1 or _unit(p0, far(d))
    t2 = _unit(p3, (b[2], b[3])) if len(b) == 6 and math.dist(p3, (b[2], b[3])) > 0.02 * chord else None
    t2 = t2 or _unit(p3, far(d[::-1]))
    if t1 is None or t2 is None:
        return None
    u = _chord_params(d)
    bz = _generate(d, u, t1, t2)
    for _ in range(3):                       # a few refinements of where each point falls on the curve
        u = _reparam(d, bz, u)
        bz = _generate(d, u, t1, t2)
    if maxerr is not None and _max_error(d, bz, u)[0] > maxerr:
        return None
    return [bz[1][0], bz[1][1], bz[2][0], bz[2][1], p3[0], p3[1]]


def thin(segs, gap, maxerr=None, keep=(), hard=0.0):
    """A line's segments with no node within `gap` (drawing units) of the
    node kept before it, so each can be seen and picked when editing. The
    ends stay; a dropped node's two segments become one, refitted to their
    shape (merge). With maxerr, a node is kept, however close, where one
    segment cannot follow the shape that closely (a tight S bend needs its
    nodes; a sweep does not), unless it is within `hard` (no shape needs
    nodes that close). Nodes in `keep` (points another line ends on) stay.
    Returns the new segments."""
    if len(segs) < 3:
        return segs
    out = [list(segs[0])]
    k = 1
    cur = None                               # the segment from out[-1], growing as nodes are dropped
    while k < len(segs):
        seg = list(segs[k]) if cur is None else cur
        last = k == len(segs) - 1
        p0 = out[-1][-2:]
        held = any(math.dist(seg[-2:], q) < 1e-3 for q in keep)
        if not last and not held and math.dist(p0, seg[-2:]) < gap:
            joined = merge(p0, seg, segs[k + 1], None if math.dist(p0, seg[-2:]) < hard else maxerr)
            if joined is not None:           # this node goes; carry on from the joined segment
                cur = joined
                k += 1
                continue
        if last and len(out) > 1 and math.dist(p0, seg[-2:]) < gap and \
                not any(math.dist(p0, q) < 1e-3 for q in keep):
            # the end stays: drop the node before it instead, if the shape allows
            prev = out[-1]
            joined = merge(out[-2][-2:], prev, seg, None if math.dist(p0, seg[-2:]) < hard else maxerr)
            if joined is not None:
                out[-1] = joined
                break
        out.append(seg)
        cur = None
        k += 1
    return out


def thin_scrap(objs, K, gap_of, err_of=None, hard=0.0):
    """Thin every line of a scrap (thin). gap_of(o) gives the gap in metres,
    err_of(o) how far (metres) the line may move. Returns how many nodes went."""
    n = 0
    ends = [tuple(o.segments()[k][-2:]) for o in objs if o.kind == 'line' and len(o.segments()) > 1 for k in (0, -1)]
    for o in objs:
        if o.kind != 'line' or '-subtype invisible' in o.head and '-id' not in o.head:
            continue
        if o.head.split()[1] in ('rock-border', 'rock-edge'):
            # rocks stay straight-sided: a point too close to the one before just goes
            segs = o.segments()
            if any(len(sg) == 6 for sg in segs) or len(segs) < 4:
                continue
            closed = math.dist(segs[0][-2:], segs[-1][-2:]) < 1e-6
            pts = [segs[0]]
            for sg in segs[1:-1]:
                if math.dist(pts[-1][-2:], sg[-2:]) >= hard * K:
                    pts.append(sg)
            if closed and len(pts) > 1 and math.dist(pts[-1][-2:], segs[-1][-2:]) < hard * K:
                pts.pop()                    # (the end is the first point again)
            pts.append(segs[-1])
            if len(pts) < len(segs) and len(pts) >= (4 if closed else 2):
                n += len(segs) - len(pts)
                o.set_segments(pts)
            continue
        segs = o.segments()
        if len(segs) < 3:
            continue
        new = thin(segs, gap_of(o) * K, err_of(o) * K if err_of else None, ends, hard * K)
        if len(new) < len(segs):
            closed = '-close on' in o.head and math.dist(segs[0][-2:], segs[-1][-2:]) < 1e-6
            if closed and math.dist(new[0][-2:], new[-1][-2:]) > 1e-6:
                continue
            o.set_segments(new)
            n += len(segs) - len(new)
    return n
