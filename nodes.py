# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""Lines that end at a wall end on a node of it (tools/sketch2therion/Style.md).

A border, step, pitch, overhang or gour that stops at a wall should end
exactly on one of the wall's points, so the two meet in Therion and in
xTherion. Each such end within `REACH` of a wall is moved onto the
wall's nearest node if one is within `SNAP`, else a node is inserted in
the wall there (a Bezier segment is split, so the wall keeps its shape)
and the end moved onto it.

Applied by `smooth` when tools/project.toml sets [convert] end_on_node.
"""
import math
import re

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


def walls_meet(objs, K, near, legs=(), body=REACH, ok=None, corner=75.0):
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

    def heading(o, w):
        # which way the wall runs out of this end (away from the rest of it)
        sg = o.segments()
        e = (sg[w][-2], sg[w][-1])
        if w == 0:
            h = (sg[1][0], sg[1][1]) if len(sg[1]) == 6 else (sg[1][-2], sg[1][-1])
        else:
            h = (sg[-1][2], sg[-1][3]) if len(sg[-1]) == 6 else (sg[-2][-2], sg[-2][-1])
        return _unit(h, e)

    def sharp(o, w, o2, w2):
        # the two walls meet at a sharp corner: Therion's straight closing is
        # better there than moving both ends (that bends their curves into a loop)
        a, b = heading(o, w), heading(o2, w2)
        if a is None or b is None:
            return False
        # carrying on: one runs out of its end the way the other runs in
        cos = -(a[0] * b[0] + a[1] * b[1])
        return math.degrees(math.acos(max(-1.0, min(1.0, cos)))) > corner

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
        if best and not across(p, end(best[1], best[2])) and not sharp(o, w, best[1], best[2]):
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


def align_handles(segs, corner=60.0):
    """Segments with the control points either side of each node in line
    with it (a smooth node), unless the line turns there by more than
    `corner` degrees (a sharp corner the line needs). A straight segment's
    direction is kept and the other handle turned to match; otherwise both
    turn to the mean direction, keeping their lengths. Returns (segments,
    how many nodes changed)."""
    segs = [list(s) for s in segs]
    n = 0
    for i in range(1, len(segs) - 1):
        a, b = segs[i], segs[i + 1]
        p = (a[-2], a[-1])
        hin = (a[2], a[3]) if len(a) == 6 else (segs[i - 1][-2], segs[i - 1][-1])
        hout = (b[0], b[1]) if len(b) == 6 else (b[-2], b[-1])
        u_in = _unit(hin, p)                 # arriving direction
        u_out = _unit(p, hout)               # leaving direction
        if u_in is None or u_out is None:
            continue
        cos = max(-1.0, min(1.0, u_in[0] * u_out[0] + u_in[1] * u_out[1]))
        turn = math.degrees(math.acos(cos))
        # a corner is where the line itself turns (by its nodes), not just its handles:
        # handles at odd angles on a line running smoothly through are a kink to remove
        if turn < 0.5:
            continue                         # already in line
        pa, pb = _unit((segs[i - 1][-2], segs[i - 1][-1]), p), _unit(p, (b[-2], b[-1]))
        sharp = turn
        if pa is not None and pb is not None:
            line_turn = math.degrees(math.acos(max(-1.0, min(1.0, pa[0] * pb[0] + pa[1] * pb[1]))))
            if line_turn < corner / 2:
                sharp = min(turn, line_turn)
        if sharp > corner:
            continue
        if len(a) == 6 and len(b) == 6:
            d = (u_in[0] + u_out[0], u_in[1] + u_out[1])
        elif len(a) == 6:                    # the segment after is straight: follow it
            d = u_out
        elif len(b) == 6:
            d = u_in
        else:
            continue                         # two straight segments: a corner of a polyline
        m = math.hypot(*d) or 1.0
        d = (d[0] / m, d[1] / m)
        na, nb = list(a), list(b)
        if len(a) == 6:
            L = math.dist(hin, p)
            na[2], na[3] = p[0] - d[0] * L, p[1] - d[1] * L
        if len(b) == 6:
            L = math.dist(p, hout)
            nb[0], nb[1] = p[0] + d[0] * L, p[1] + d[1] * L

        def forward(p0, sg):
            # both handles of a segment within its span along the chord (no hook)
            if len(sg) != 6:
                return True
            ch = (sg[4] - p0[0], sg[5] - p0[1])
            L2 = ch[0] ** 2 + ch[1] ** 2 or 1e-9
            t1 = ((sg[0] - p0[0]) * ch[0] + (sg[1] - p0[1]) * ch[1]) / L2
            t2 = ((sg[2] - p0[0]) * ch[0] + (sg[3] - p0[1]) * ch[1]) / L2
            return 0 <= t1 <= 1 and 0 <= t2 <= 1
        if not (forward(tuple(segs[i - 1][-2:]), na) and forward(p, nb)):
            continue                         # lining up here would make a hook
        segs[i], segs[i + 1] = na, nb
        a, b = na, nb
        n += 1
    return segs, n


def align_scrap(objs, corner=60.0):
    """align_handles on every line of a scrap except boulders (straight-sided).
    Returns how many nodes changed."""
    n = 0
    for o in objs:
        if o.kind != 'line' or len(o.segments()) < 3:
            continue
        if o.head.split()[1] in ('rock-border', 'rock-edge') or '-subtype invisible' in o.head and '-id' not in o.head:
            continue
        segs, k = align_handles(o.segments(), corner)
        if k:
            o.set_segments(segs)
            n += k
    return n


RUN_GAP = 0.3       # m: ends this far apart join if the line carries on ...
RUN_TURN = 60.0     # degrees: ... turning no more than this across the gap
TICKED = ('wall', 'floor-step', 'pit', 'overhang', 'ceiling-step', 'chimney')   # never turned round


def _end_unit(segs, at_end):
    """The unit direction a line leaves its end (at_end) or starts from its start."""
    pts = [(s[-2], s[-1]) for s in segs]
    if at_end:
        a = (segs[-1][2], segs[-1][3]) if len(segs[-1]) == 6 else pts[-2]
        return _unit(a, pts[-1])
    b = (segs[1][0], segs[1][1]) if len(segs[1]) == 6 else pts[1]
    return _unit(pts[0], b)


def join_runs(objs, K, touch=0.05, gap=RUN_GAP, turn=RUN_TURN, walls=False, ok=None, named=()):
    """Lines of one kind that run on into each other joined into one line
    (Style.md, Walls and the outline): ends closer than `touch` (m, a number
    or a function of the point) always, whatever the angle (the join keeps
    its corner); ends up to `gap` m apart if the line turns no more than
    `turn` degrees across it. A wall, step, pitch or overhang is never
    turned round to fit (its passage side or ticks would move); a border
    may be. Not joined: a line whose -id a join names (`named`), where a third
    line of the kind ends at the meeting point (a junction), gours, closed
    lines, sections. `walls`: join the walls only (else every other kind);
    `ok()`: a join is undone unless it says so (the outline no worse).
    Returns how many joins."""
    from .tidy import reverse_segments

    def kind(o):
        return o.head.split()[1] if len(o.head.split()) > 1 else ''

    def same(o):                                  # its type and options, the id aside
        return re.sub(r'\s-id\s+\S+', '', o.head)

    def eligible(o):
        m = re.search(r'-id\s+(\S+)', o.head)
        if o.kind != 'line' or len(o.segments()) < 2 or '-close on' in o.head or (m and m.group(1) in named):
            return False
        if kind(o) == 'wall':
            return walls and '-outline none' not in o.head
        return not walls and kind(o) not in ('rock-border', 'rock-edge', 'rimstone-dam', 'section') \
            and '-subtype invisible' not in o.head

    n = 0
    tried = set()
    while True:
        lines = [o for o in objs if eligible(o)]
        best = None
        for o in lines:
            so = o.segments()
            for w in lines:
                if w is o or same(w) != same(o) or (id(o), id(w)) in tried:
                    continue
                sw = w.segments()
                for we in (0, -1):
                    for oe in (0, -1):
                        if kind(o) in TICKED and we == oe:        # would turn one round
                            continue
                        p, q = sw[we][-2:], so[oe][-2:]
                        d = math.dist(p, q)
                        if d > gap * K or (best is not None and d >= best[0]):
                            continue
                        best = (d, o, w, we, oe)
        if best is None:
            return n
        d, o, w, we, oe = best
        tried.add((id(o), id(w)))
        if we == 0 and oe == -1:                                  # o runs into w: join w onto o
            o, w, we, oe = w, o, -1, 0
        sw, so = w.segments(), o.segments()
        a = sw if we == -1 else reverse_segments(sw)
        b = so if oe == 0 else reverse_segments(so)
        p, q = a[-1][-2:], b[0][-2:]
        reach = (touch(p) if callable(touch) else touch) * K
        if d > reach:
            ua, ub = _end_unit(a, True), _end_unit(b, False)
            if ua is None or ub is None or \
                    math.degrees(math.acos(max(-1.0, min(1.0, ua[0] * ub[0] + ua[1] * ub[1])))) > turn:
                continue
        # a third line of the kind ending there: a junction, not a run on
        if any(x is not w and x is not o and x.head.split()[:2] == w.head.split()[:2] and len(x.segments()) > 1
               and any(math.dist(x.segments()[k][-2:], p) <= max(d, reach) or math.dist(x.segments()[k][-2:], q) <= max(d, reach)
                       for k in (0, -1))
               for x in objs if x.kind == 'line'):
            continue
        rows = w.rows
        # o's first point stays (the join) when apart: w's end runs on to it
        w.set_segments([list(s) for s in a] + ([list(b[0])] if d > reach else []) + [list(s) for s in b[1:]])
        o.kind = 'drop'
        if ok is not None and not ok():
            o.kind, w.rows = 'line', rows
            continue
        objs[:] = [x for x in objs if x.kind != 'drop']
        n += 1
        tried.clear()


def ends_meet(objs, K, near):
    """Lines of different kinds that end close together share that end
    (a border running on as a floor step, then a pitch: the drop changing
    along the edge). `near` in m, a number or a function of the point. An
    end already on a wall stays where it is and the other comes to it;
    otherwise they meet halfway. Walls, boulders and closed lines are not
    moved. Returns how many ends moved."""
    def movable(o):
        return o.kind == 'line' and len(o.segments()) > 1 and not o.head.startswith('line wall') \
            and o.head.split()[1] not in ('rock-border', 'rock-edge', 'section') \
            and '-close on' not in o.head and '-subtype invisible' not in o.head
    walls = [o for o in objs if o.kind == 'line' and o.head.startswith('line wall') and len(o.segments()) > 1]
    wall_nodes = [tuple(s[-2:]) for w in walls for s in w.segments()]
    lines = [o for o in objs if movable(o)]
    ends = [(o, k) for o in lines for k in (0, -1)]
    done, n = set(), 0
    for i, (o, k) in enumerate(ends):
        if (id(o), k) in done:
            continue
        p = tuple(o.segments()[k][-2:])
        reach = (near(p) if callable(near) else near) * K
        best = None
        for o2, k2 in ends[i + 1:]:
            if o2 is o or (id(o2), k2) in done:
                continue
            q = tuple(o2.segments()[k2][-2:])
            d = math.dist(p, q)
            if 1e-6 < d <= reach and (best is None or d < best[0]):
                best = (d, o2, k2, q)
        if best is None:
            continue
        _, o2, k2, q = best
        on_p = any(math.dist(p, w) < 1e-3 for w in wall_nodes)
        on_q = any(math.dist(q, w) < 1e-3 for w in wall_nodes)
        if on_p and on_q:
            continue
        m = p if on_p else q if on_q else ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        if math.dist(p, m) > 1e-6:
            _set_end(o, k, m)
        if math.dist(q, m) > 1e-6:
            _set_end(o2, k2, m)
        done |= {(id(o), k), (id(o2), k2)}
        n += 1
    return n


def despike(objs, K, short=0.3, turn=110.0, ok=None):
    """Walls without spikes: a node where the wall turns right back (more
    than `turn` degrees) beside a segment shorter than `short` m is the
    sketcher's stroke overshooting, not a corner; it goes and its two
    segments become one (merge). With ok(), a removal that spoils the
    outline is undone. Returns how many nodes went."""
    n = 0
    for o in objs:
        if o.kind != 'line' or not o.head.startswith('line wall') or '-subtype invisible' in o.head:
            continue
        changed = True
        while changed:
            changed = False
            s = o.segments()
            for i in range(1, len(s) - 1):
                p = tuple(s[i][-2:])
                a = tuple(s[i][2:4]) if len(s[i]) == 6 else tuple(s[i - 1][-2:])
                b = tuple(s[i + 1][0:2]) if len(s[i + 1]) == 6 else tuple(s[i + 1][-2:])
                u, v = _unit(a, p), _unit(p, b)
                if u is None or v is None:
                    continue
                ang = math.degrees(math.acos(max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1]))))
                # and as the nodes themselves turn (a step can hide behind smooth handles)
                u2, v2 = _unit(tuple(s[i - 1][-2:]), p), _unit(p, tuple(s[i + 1][-2:]))
                if u2 is not None and v2 is not None:
                    ang = max(ang, math.degrees(math.acos(max(-1.0, min(1.0, u2[0] * v2[0] + u2[1] * v2[1])))))
                near = min(math.dist(s[i - 1][-2:], p), math.dist(p, s[i + 1][-2:]))
                # turning right back over a short way, or a sharp step over a very short way
                # (strokes overlapping side by side): not a corner the wall needs
                if not ((ang > turn and near < short * K) or (ang > 70.0 and near < short * K / 3)):
                    continue
                joined = merge(tuple(s[i - 1][-2:]), s[i], s[i + 1])
                if joined is None:
                    joined = [s[i + 1][-2], s[i + 1][-1]]
                rows = o.rows
                o.set_segments([list(x) for x in s[:i]] + [joined] + [list(x) for x in s[i + 2:]])
                if ok is not None and not ok():
                    o.rows = rows
                    continue
                n += 1
                changed = True
                break
    return n


def fix_handles(objs, back=1.5):
    """No curve doubling back on itself within a segment: a control point
    that points backwards along its segment (or reaches past its far end)
    makes the curve overshoot and come back, a hook in the line. Such a
    handle is put back to a third of the way along the segment, but only
    where the curve really runs back along its chord by more than `back`
    (drawing units). Returns how many were fixed."""
    n = 0
    for o in objs:
        if o.kind != 'line' or len(o.segments()) < 2 or o.head.split()[1] in ('rock-border', 'rock-edge') \
                or '-subtype invisible' in o.head and '-id' not in o.head:
            continue
        segs = [list(x) for x in o.segments()]
        hit = False
        for i in range(1, len(segs)):
            sg = segs[i]
            if len(sg) != 6:
                continue
            p0, p3 = tuple(segs[i - 1][-2:]), (sg[4], sg[5])
            ch = (p3[0] - p0[0], p3[1] - p0[1])
            L2 = ch[0] ** 2 + ch[1] ** 2
            if L2 < 1e-9:
                continue
            c1, c2 = (sg[0], sg[1]), (sg[2], sg[3])
            # only where the curve really runs back along its chord (more than `back`)
            pts = [_bezier(p0, c1, c2, p3, k / 24) for k in range(25)]
            along = [((q[0] - p0[0]) * ch[0] + (q[1] - p0[1]) * ch[1]) / math.sqrt(L2) for q in pts]
            peak, worst = along[0], 0.0
            for a_ in along:
                peak = max(peak, a_)
                worst = max(worst, peak - a_)
            low = min(along)
            if worst <= back and low >= -back and max(along) <= math.sqrt(L2) + back:
                continue
            # how far along the chord each handle reaches (0 at p0, 1 at p3)
            t1 = ((c1[0] - p0[0]) * ch[0] + (c1[1] - p0[1]) * ch[1]) / L2
            t2 = ((c2[0] - p0[0]) * ch[0] + (c2[1] - p0[1]) * ch[1]) / L2
            if t1 < 0 or t1 > 1:
                sg[0], sg[1] = p0[0] + ch[0] / 3, p0[1] + ch[1] / 3
                hit = True
            if t2 < 0 or t2 > 1:
                sg[2], sg[3] = p3[0] - ch[0] / 3, p3[1] - ch[1] / 3
                hit = True
        if hit:
            o.set_segments(segs)
            n += 1
    return n
