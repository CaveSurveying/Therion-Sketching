# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see tools/LICENSE.
"""Steps in walls: a short cross-piece where a wall jogs sideways.

Where the sketcher's wall strokes do not quite meet (drawn underground in
difficult conditions), the converted wall jogs: a short piece across the
wall's direction joins two runs that carry on roughly parallel. It is
not a feature of the cave, so the wall is joined through it: the two
corners become one point midway, and the wall runs on. A short piece at
the very start or end of a wall, turned across it, is dropped.

Applied by `smooth` when tools/project.toml sets [convert] wall_jog_max.
"""
import math

from .tidy import Obj

MIN_TURN = 50.0       # degrees: the piece crosses the wall's direction at least this much
MAX_SKEW = 40.0       # degrees: the runs either side carry on within this of each other


def _anchors(o):
    return [(s[-2], s[-1]) for s in o.segments()]


def _dir(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def _diff(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _axis_diff(a, b):
    """Angle between two directions, ignoring which way along: 0 to 90."""
    d = _diff(a, b)
    return min(d, 180 - d)


def jogs(points, max_len):
    """Indices i where points[i] -> points[i+1] is a wall step."""
    out = []
    n = len(points)
    for i in range(n - 1):
        a, b = points[i], points[i + 1]
        d = math.dist(a, b)
        if d == 0 or d > max_len:
            continue
        piece = _dir(a, b)
        before = _dir(points[i - 1], a) if i > 0 else None
        after = _dir(b, points[i + 2]) if i + 2 < n else None
        if before is None and after is None:
            continue
        runs = [r for r in (before, after) if r is not None]
        if any(_axis_diff(piece, r) < MIN_TURN for r in runs):
            continue
        if before is not None and after is not None and _diff(before, after) > MAX_SKEW:
            continue
        out.append(i)
    return out


def _row(seg):
    return '  ' + ' '.join('%.2f' % v for v in seg)


def _moved_end(seg, p):
    """A segment ending at p instead (its control points kept)."""
    return list(seg[:-2]) + [p[0], p[1]]


def doubles_back(p0, seg, slack=0.05):
    """True if a Bezier segment's control points lie before its start or
    past its end along it (by more than `slack` of its length): the curve
    turns back on itself, a zigzag where two strokes overlapped."""
    if len(seg) != 6:
        return False
    p3 = (seg[4], seg[5])
    dx, dy = p3[0] - p0[0], p3[1] - p0[1]
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return False
    for c in ((seg[0], seg[1]), (seg[2], seg[3])):
        t = ((c[0] - p0[0]) * dx + (c[1] - p0[1]) * dy) / L2
        if t < -slack or t > 1 + slack:
            return True
    return False


def unzigzag(segs):
    """Segments that double back made straight; returns how many."""
    n = 0
    for k in range(1, len(segs)):
        p0 = (segs[k - 1][-2], segs[k - 1][-1])
        if doubles_back(p0, segs[k]):
            segs[k] = [segs[k][4], segs[k][5]]
            n += 1
    return n


def join(o, max_len):
    """Wall `o` with its steps joined through, and any segment doubling
    back made straight; returns how many."""
    segs = [list(s) for s in o.segments()]
    zz = unzigzag(segs)
    if zz:
        o.rows = [_row(s) for s in segs]
    pts = [(s[-2], s[-1]) for s in segs]
    cut = jogs(pts, max_len)
    if not cut:
        return zz
    drop = set()
    for i in cut:
        if i == 0:                                   # turned piece at the start
            drop.add(0)
            segs[1] = [segs[1][-2], segs[1][-1]]
        elif i + 1 == len(segs) - 1:                 # turned piece at the end
            drop.add(i + 1)
        else:
            m = ((pts[i][0] + pts[i + 1][0]) / 2, (pts[i][1] + pts[i + 1][1]) / 2)
            segs[i] = _moved_end(segs[i], m)
            drop.add(i + 1)
    kept = [s for k, s in enumerate(segs) if k not in drop]
    kept[0] = kept[0][-2:]
    o.rows = [_row(s) for s in kept]
    return len(cut) + zz


def join_scrap(objs, K, max_len_m):
    """Join every outline wall through its steps; returns how many."""
    n = 0
    for o in objs:
        if o.kind == 'line' and o.head.split()[:2] == ['line', 'wall'] and '-subtype invisible' not in o.head \
                and '-close on' not in o.head and '-outline none' not in o.head and len(o.segments()) > 2:
            n += join(o, max_len_m * K)
    return n


# -- borders broken where the sketcher missed the end of a line ------------

BORDER_GAP = 0.3       # m: border pieces with ends this close, carrying on, are one line
BORDER_TURN = 60.0     # degrees: and the direction changes no more than this across the gap


def _is_border(o):
    w = o.head.split() if o.kind == 'line' else []
    return w[:2] == ['line', 'border'] and '-subtype invisible' not in o.head and '-close on' not in o.head \
        and len(o.segments()) > 1


def _end_dir(segs, at_end):
    """Direction leaving the line at its end (or at its start, pointing out of it)."""
    pts = [(s[-2], s[-1]) for s in segs]
    if at_end:
        a, b = pts[-2], pts[-1]
    else:
        a, b = pts[1], pts[0]
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def join_borders(objs, K, gap_m=BORDER_GAP):
    """Join border pieces that carry on across a small gap; returns how many joins."""
    from .tidy import reverse_segments
    n = 0
    merged = True
    while merged:
        merged = False
        borders = [o for o in objs if _is_border(o)]
        for a in borders:
            for b in borders:
                if a is b:
                    continue
                sa, sb = a.segments(), b.segments()
                for rev in (False, True):
                    segs_b = reverse_segments(sb) if rev else sb
                    end_a = (sa[-1][-2], sa[-1][-1])
                    start_b = (segs_b[0][-2], segs_b[0][-1])
                    d = math.dist(end_a, start_b)
                    if d > gap_m * K:
                        continue
                    out_a = _end_dir(sa, True)
                    into_b = _end_dir(segs_b, False) + 180.0
                    if _diff(out_a, into_b) > BORDER_TURN:
                        continue
                    joined = [list(s) for s in sa] + ([[start_b[0], start_b[1]]] if d > 1e-6 else []) + \
                             [list(s) for s in segs_b[1:]]
                    a.set_segments(joined)
                    objs.remove(b)
                    n += 1
                    merged = True
                    break
                if merged:
                    break
            if merged:
                break
    return n
