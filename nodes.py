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


def nearest_on(segs, p, samples=24):
    """(distance, segment index, t, point) of the nearest point to p on a line."""
    best = None
    prev = (segs[0][-2], segs[0][-1])
    for i, seg in enumerate(segs[1:], 1):
        for k in range(samples + 1):
            t = k / samples
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


def snap_scrap(objs, K):
    """Move line ends at walls onto wall nodes; returns how many."""
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
            if math.dist(node, q) <= SNAP * K:
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
