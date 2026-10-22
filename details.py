# Ported from caves-mendip-swildons, tools/sketch2therion (commit 198bf46,
# https://github.com/paperclipmonkey/caves-mendip-swildons). GPLv3: see tools/LICENSE.
"""Plan details that read as sketching: ledge lines and boulders.

- Lines inside the passage (the converter's borders, from brown and grey
  sketch strokes, or walls left inside the passage) are mostly the edge
  of a step down: a shelf, with the stream in the lowest part. Each open
  border over a metre long becomes a `line floor-step`, drawn so its
  ticks (which Therion puts on the line's left) are on the lower side:
  the side the water is on (flow arrows and pools, the stream being in
  the lowest part), or failing that the side the survey is on. A step
  that just doubles a longer one goes, steps are cut out of the pools,
  and scribbles (short, very wiggly strokes) go.
- Boulders (`line rock-border -close on`) are straightened into clean
  polygons, and the bigger ones get facet edges from a ridge point to a
  few of their corners instead of one line straight across.

    python3 -m tools.sketch2therion details FILE.th2 [...]
"""
import math
import re

from shapely.geometry import LineString, Point, Polygon

from .roofs import Splays
from .survey import survey_of as _survey_of
from .tidy import Obj, bezier_points, parse_scrap, scale_of

MIN_STEP = 1.0      # m: shorter interior lines stay borders


def _legs(objs, splays, survey):
    st = {}
    for o in objs:
        m = re.match(r'point (\S+) (\S+) station\b.*-name (\S+)', o.head) if o.kind == 'point' else None
        if m:
            n = m.group(3)
            st[n if '@' in n else f'{n}@{survey}'] = (float(m.group(1)), float(m.group(2)))
    return [LineString([st[a], st[b]]) for a in st for b in splays.legs.get(a, ()) if b in st and a < b]


def _side(pts, legs):
    """+1 if the legs are mostly on the line's left, -1 if on its right."""
    vote = 0.0
    for a, b in zip(pts, pts[1:]):
        d = math.dist(a, b)
        if d < 1e-9:
            continue
        m = Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        near = min(legs, key=lambda l: l.distance(m))
        q = near.interpolate(near.project(m))
        cross = (b[0] - a[0]) * (q.y - a[1]) - (b[1] - a[1]) * (q.x - a[0])
        vote += d * (1 if cross > 0 else -1)
    return 1 if vote >= 0 else -1


def _water(objs):
    """Where the water is: (points of flow arrows, pool polygons)."""
    flows = [Point(float(o.head.split()[1]), float(o.head.split()[2])) for o in objs
             if o.kind == 'point' and ' water-flow' in o.head]
    pools = []
    for o in objs:
        if o.kind == 'line' and o.head.startswith('line border') and '-id' in o.head and '-close on' in o.head:
            g = Polygon([(s[-2], s[-1]) for s in o.segments()]).buffer(0)
            if not g.is_empty:
                pools.append(g)
    return flows, pools


def _water_side(pts, flows, pools, K):
    """+1 if the water is mostly on the line's left, -1 on its right, 0 if
    there is none within 2.5 m. Each stretch of the line looks at the
    water nearest to it, so a curving step is judged where it is."""
    things = list(flows) + [p.boundary for p in pools]
    if not things:
        return 0
    vote = 0.0
    for a, b in zip(pts, pts[1:]):
        d = math.dist(a, b)
        if d < 1e-9:
            continue
        m = Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        g = min(things, key=lambda t: t.distance(m))
        dist = g.distance(m)
        if dist > 2.5 * K or dist < 1e-6:
            continue
        q = g if g.geom_type == 'Point' else g.interpolate(g.project(m))
        cross = (b[0] - a[0]) * (q.y - a[1]) - (b[1] - a[1]) * (q.x - a[0])
        vote += d / (0.3 * K + dist) * (1 if cross > 0 else -1)
    return 0 if vote == 0 else (1 if vote > 0 else -1)


def floor_steps(objs, K, legs):
    from shapely.ops import unary_union
    from .tidy import reverse_segments
    walls = [LineString(bezier_points(o.segments())) for o in objs
             if o.kind == 'line' and o.head.startswith('line wall') and '-subtype invisible' not in o.head
             and len(o.segments()) > 1]
    wall_all = unary_union(walls) if walls else None
    flows, pools = _water(objs)
    pool_all = unary_union(pools).buffer(0.1 * K) if pools else None
    n = 0

    def interior(o):
        return o.kind == 'line' and o.head.split()[:2] in (['line', 'border'], ['line', 'floor-step']) \
            and '-close on' not in o.head and '-id' not in o.head

    for o in objs:
        if not interior(o):
            continue
        pts = bezier_points(o.segments())
        if len(pts) < 2:
            continue
        line = LineString(pts)
        # scribbles: short and very wiggly
        chord = math.dist(pts[0], pts[-1])
        if line.length < 2 * K and line.length > 2.5 * max(chord, 1e-6):
            o.kind = 'drop'
            continue
        # a wall stroked twice: the second stroke runs alongside the wall
        if wall_all is not None:
            samples = [line.interpolate(i / 10, normalized=True) for i in range(11)]
            if sum(wall_all.distance(q) < 0.5 * K for q in samples) >= 8:
                o.kind = 'drop'
                continue
        # steps are the edge of the low part, not across the water
        if pool_all is not None and line.intersects(pool_all):
            rest = line.difference(pool_all)
            parts = [g for g in getattr(rest, 'geoms', [rest]) if g.length >= MIN_STEP * K]
            if not parts:
                o.kind = 'drop'
                continue
            o.set_segments([[x, y] for x, y in max(parts, key=lambda g: g.length).coords])
            line = max(parts, key=lambda g: g.length)
            pts = list(line.coords)
        if line.length < MIN_STEP * K:
            continue
        o.head = 'line floor-step'
    # a step that mostly doubles a longer one goes
    steps = sorted([o for o in objs if o.kind == 'line' and o.head == 'line floor-step'],
                   key=lambda o: -LineString(bezier_points(o.segments())).length)
    kept = []
    for o in steps:
        line = LineString(bezier_points(o.segments()))
        samples = [line.interpolate(i / 10, normalized=True) for i in range(11)]
        if any(sum(k.distance(q) < 0.6 * K for q in samples) >= 8 for k in kept):
            o.kind = 'drop'
            continue
        kept.append(line)
    # the low side: the water's side, else the survey's
    for o in objs:
        if o.kind != 'line' or o.head != 'line floor-step':
            continue
        pts = bezier_points(o.segments())
        side = _water_side(pts, flows, pools, K)
        if side == 0 and legs:
            side = _side(pts, legs)
        # Therion draws the ticks on the line's left: the low side
        if side < 0:
            o.set_segments(reverse_segments(o.segments()))
        n += 1
    return n


ROCK_EDGE_MIN = 0.5   # m (square root of the area): a rock this big or bigger gets rock edges
ROCK_BIG = 1.6        # m: and a third edge from this size (as before, round 3)
RIDGE_TURN = 140.0    # degrees: the edge through the ridge bends about this much (a ridge, not a crease)


def _corners(pts, n):
    """The n points of a closed ring (no repeat) that keep most of its
    shape: the point whose triangle with its neighbours is smallest goes,
    one at a time (Visvalingam)."""
    pts = list(pts)
    area = lambda a, b, c: abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2
    while len(pts) > n:
        k = min(range(len(pts)), key=lambda i: area(pts[i - 1], pts[i], pts[(i + 1) % len(pts)]))
        del pts[k]
    return pts


TOP_FACE = 0.55      # the top face: the outline shrunk to this share round its middle ...
TOP_SHIFT = 0.15     # ... and moved this share of the rock's radius towards the light (top left)
LIGHT = (-0.7071, 0.7071)
NODE_MIN = 0.06     # m: nodes of a rock edge at least this far apart
FACE_BEND = 30.0     # degrees: a corner of the face edge bending less than this goes


def rock(pp, K):
    """A rock as a line drawing of a block seen from above, from a sketched
    loop: (corners, [edge lines]). The outline is the hull of the loop cut
    to 5 to 8 corners by size (angular, with flat faces). The top face is
    the outline shrunk round its middle and moved towards the light (top
    left); its edges on the shadow side (bottom right) are drawn, with the
    creases from the ends of that run, and from its middle on bigger rocks,
    out to the outline's corners: the faces dropping to the floor, as a
    simplified drawing of a boulder shows them (Style.md, rocks; the user:
    rock edges to make them look like rock)."""
    g = Polygon(pp).buffer(0)
    if g.is_empty:
        return None, []
    if g.geom_type != 'Polygon':
        g = max(g.geoms, key=lambda q: q.area)
    hull = g.convex_hull
    size = math.sqrt(hull.area) / K
    ring = list(hull.exterior.coords)[:-1]
    if not hull.exterior.is_ccw:
        ring = ring[::-1]
    n = 5 if size < 0.5 else 6 if size < 1.0 else 7 if size < 2.0 else 8
    corners = _corners(ring, min(n, len(ring)))
    while len(corners) > 3 and min(math.dist(corners[i - 1], corners[i]) for i in range(len(corners))) < NODE_MIN * K:
        corners = _corners(corners, len(corners) - 1)          # (a small rock: corners not too close)
    if len(corners) < 3:
        return None, []
    poly = Polygon(corners)
    c = poly.centroid
    r = math.sqrt(poly.area / math.pi)
    # each rock its own: a number from where it is (the same every run) picks its style
    rnd = _seeded((round(c.x / K, 1), round(c.y / K, 1)))
    long_, wide = _axes(corners)
    style = rnd()
    if wide / long_ <= 0.55:                       # a long rock: a wedge or a line across more often
        style = 1 - (1 - style) * (RIDGE_SHARE + ACROSS_SHARE) * 1.3 if style > 0.3 else style
    if style >= 1 - RIDGE_SHARE:
        edges = _ridge(corners, c, r, rnd)
    elif style >= 1 - RIDGE_SHARE - ACROSS_SHARE:
        edges = _across(corners, size, rnd)
    elif style >= 1 - RIDGE_SHARE - ACROSS_SHARE - PEAK_SHARE:
        edges = _peak(corners, c, r, size, rnd)
    else:
        edges = _block(corners, c, r, size, rnd, K)
    return corners, _three_ways(_spaced(edges, K), corners, K)


def _three_ways(edges, corners, K):
    """Every point inside the rock where edges meet has at least three lines
    meeting there, as at a corner of a solid: one with fewer gets lines out
    to corners of the outline, each into the widest gap between the lines
    it has, not crossing the others (the user: three edges at every corner,
    usually to the outline's corners)."""
    from shapely.geometry import LineString as LS
    key = lambda p: (round(p[0], 1), round(p[1], 1))
    on_outline = lambda p: min(math.dist(p, q) for q in corners) < NODE_MIN * K
    adj = {}
    for e in edges:
        for a, b in zip(e, e[1:]):
            adj.setdefault(key(a), [tuple(a), set()])[1].add(key(b))
            adj.setdefault(key(b), [tuple(b), set()])[1].add(key(a))
    segs = [LS([a, b]) for e in edges for a, b in zip(e, e[1:])]
    out = [list(e) for e in edges]
    for k, (p, nbrs) in list(adj.items()):
        if on_outline(p):
            continue
        while len(nbrs) < 3:
            dirs = sorted(math.atan2(adj[n][0][1] - p[1], adj[n][0][0] - p[0]) for n in nbrs)

            def gap(q):                                   # how far round from the nearest line it has
                a = math.atan2(q[1] - p[1], q[0] - p[0])
                return min(abs((a - d + math.pi) % (2 * math.pi) - math.pi) for d in dirs) if dirs else math.pi
            cand = [q for q in corners if key(q) not in nbrs and math.dist(q, p) >= NODE_MIN * K
                    and not any(LS([p, q]).crosses(sg) for sg in segs)]
            if not cand:
                break
            q = max(cand, key=gap)
            out.append([list(p), list(q)])
            segs.append(LS([p, q]))
            nbrs.add(key(q))
            adj.setdefault(key(q), [tuple(q), set()])[1].add(k)
    return out


RIDGE_SHARE = 0.20   # of rocks drawn with a ridge (a wedge; long rocks more often)
ACROSS_SHARE = 0.35  # with a line across from one side to the other (split in two faces)
PEAK_SHARE = 0.25    # with a peak (pointed); the rest (about 20%) blocks with a top face


def _across(corners, size, rnd):
    """A line across the rock from a corner to one about opposite (two
    faces), and on some rocks of ROCK_EDGE_MIN or more a second line from
    another corner meeting it part-way along (three lines meet there)."""
    m = len(corners)
    i = int(rnd() * m) % m
    j = (i + m // 2 + (1 if rnd() < 0.5 and m > 4 else 0)) % m
    a, b = corners[i], corners[j]
    if size >= ROCK_EDGE_MIN and rnd() < 0.55:
        t = 0.35 + 0.3 * rnd()
        q = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        side = [k for k in range(m) if k not in (i, j)]
        k = side[int(rnd() * len(side)) % len(side)]
        return [[a, q, b], [q, corners[k]]]
    return [[a, b]]


def _seeded(key):
    """A repeatable random number source for one rock."""
    import random
    return random.Random(hash(key) & 0xffffffff).random


def _axes(corners):
    """(length, width) of a ring of corners along its longest and across."""
    best = max(((a, b) for i, a in enumerate(corners) for b in corners[i + 1:]), key=lambda ab: math.dist(*ab))
    (ax, ay), (bx, by) = best
    L = math.dist(best[0], best[1]) or 1.0
    ux, uy = (bx - ax) / L, (by - ay) / L
    across = [(-uy) * (x - ax) + ux * (y - ay) for x, y in corners]
    return L, max(across) - min(across)


def _spaced(edges, K):
    """Edges with no two nodes closer than NODE_MIN; one left with one node goes."""
    out = []
    for e in edges:
        pts = [list(e[0])]
        for q in e[1:]:
            if math.dist(q, pts[-1]) >= NODE_MIN * K:
                pts.append(list(q))
        if len(pts) >= 2:
            out.append(pts)
    return out


def _peak(corners, c, r, size, rnd):
    """A pointed rock: a peak towards the light, creases down to corners well
    round from each other (two as one line through the peak, a third from
    0.5 m)."""
    s = 0.15 + 0.2 * rnd()
    peak = (c.x + LIGHT[0] * s * r, c.y + LIGHT[1] * s * r)
    ang = lambda p: math.atan2(p[1] - peak[1], p[0] - peak[0])
    by = sorted(corners, key=ang)
    # the corner straight down the shadow side, and two well round from it either way
    shadow = max(corners, key=lambda p: -((p[0] - peak[0]) * LIGHT[0] + (p[1] - peak[1]) * LIGHT[1]))
    rest = [p for p in by if p != shadow]
    if len(rest) < 2:
        return [[shadow, peak]]
    a = min(rest, key=lambda p: abs(_turn(peak, p, shadow) - 125))
    b = min((p for p in rest if p != a), key=lambda p: abs(_turn(peak, p, a) - 120) + abs(_turn(peak, p, shadow) - 115))
    edges = [[a, peak, shadow]]
    if size >= ROCK_EDGE_MIN:
        edges.append([peak, b])
    return edges


def _ridge(corners, c, r, rnd):
    """A wedge: a ridge along the rock's length, nearer the light side,
    forking at each end to two corners."""
    (ax, ay), (bx, by) = max(((p, q) for i, p in enumerate(corners) for q in corners[i + 1:]),
                             key=lambda pq: math.dist(*pq))
    t0, t1 = 0.22 + 0.1 * rnd(), 0.72 + 0.1 * rnd()
    sh = (0.1 + 0.15 * rnd()) * r
    e0 = (ax + (bx - ax) * t0 + LIGHT[0] * sh, ay + (by - ay) * t0 + LIGHT[1] * sh)
    e1 = (ax + (bx - ax) * t1 + LIGHT[0] * sh, ay + (by - ay) * t1 + LIGHT[1] * sh)
    near0 = sorted(corners, key=lambda p: math.dist(p, e0))
    near1 = sorted(corners, key=lambda p: math.dist(p, e1))
    side = lambda p: (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax)
    # each end forks to the nearest corner either side of the ridge
    f0 = [next((p for p in near0 if side(p) > 0), None), next((p for p in near0 if side(p) < 0), None)]
    f1 = [next((p for p in near1 if side(p) > 0), None), next((p for p in near1 if side(p) < 0), None)]
    edges = []
    if f0[1] and f1[1]:
        edges.append([f0[1], e0, e1, f1[1]])            # the shadow side: one line along the ridge
    else:
        edges.append([e0, e1])
    for f, e in ((f0[0], e0), (f1[0], e1)):
        if f:
            edges.append([e, f])
    return edges


def _block(corners, c, r, size, rnd, K):
    """A block: its top face's shadow side and the creases to its corners."""
    face_k = TOP_FACE - 0.1 + 0.2 * rnd()
    shift = TOP_SHIFT * (0.6 + 0.8 * rnd())
    top = [(c.x + (x - c.x) * face_k + LIGHT[0] * shift * r,
            c.y + (y - c.y) * face_k + LIGHT[1] * shift * r) for x, y in corners]
    m = len(top)
    # the top face's edges facing away from the light (outward normal of a ccw ring: (dy, -dx))
    shadow = []
    for i in range(m):
        (x0, y0), (x1, y1) = top[i], top[(i + 1) % m]
        nx, ny = (y1 - y0), -(x1 - x0)
        shadow.append(nx * LIGHT[0] + ny * LIGHT[1] < 0)
    if all(shadow) or not any(shadow):
        return []
    # the run of shadow edges, as one line from its first corner to its last
    start = next(i for i in range(m) if shadow[i] and not shadow[i - 1])
    run = [start]
    i = start
    while shadow[i % m]:
        i += 1
        run.append(i % m)
    # the face edge kept simple: corners of it that hardly bend, or close together, go
    keep = [run[0]]
    for j in range(1, len(run) - 1):
        a, b, d = top[keep[-1]], top[run[j]], top[run[j + 1]]
        bend = 180 - _turn(b, a, d)
        if bend >= FACE_BEND and math.dist(a, b) >= 0.15 * r and math.dist(b, d) >= 0.15 * r:
            keep.append(run[j])
    keep.append(run[-1])
    face = [list(top[k]) for k in keep]
    edges = [[list(corners[keep[0]])] + face + [list(corners[keep[-1]])]]   # crease, face edge, crease
    if size >= ROCK_EDGE_MIN and len(keep) >= 3:
        k = keep[len(keep) // 2]
        edges.append([list(top[k]), list(corners[k])])                     # the crease from its middle
    return edges


def _turn(o, a, b):
    """The angle at o between the directions to a and to b, in degrees (0 to 180)."""
    u = math.atan2(a[1] - o[1], a[0] - o[0])
    v = math.atan2(b[1] - o[1], b[0] - o[0])
    d = abs(math.degrees(u - v)) % 360
    return 360 - d if d > 180 else d


def boulders(objs, K):
    """Clean polygons with facet edges. Returns how many were redrawn."""
    from .settings import SETTINGS
    if SETTINGS['drawn_rocks']:
        return pleasing_rocks(objs, K)
    out, n = [], 0
    for o in objs:
        if o.kind == 'drop':
            continue
        if o.kind == 'line' and o.head.startswith('line rock-edge'):
            continue                    # redrawn below
        out.append(o)
        if not (o.kind == 'line' and o.head.startswith('line rock-border')):
            continue
        pts = bezier_points(o.segments())
        if len(pts) < 4:
            continue
        g = Polygon(pts).buffer(0)
        if g.is_empty or g.geom_type != 'Polygon':
            continue
        size = math.sqrt(g.area) / K
        corners = list(g.exterior.simplify(max(0.06, 0.12 * size) * K).coords)[:-1]
        if len(corners) < 3:
            continue
        o.set_segments([[x, y] for x, y in corners + [corners[0]]])
        n += 1
        if g.area < (0.9 * K) ** 2:
            continue
        from .settings import SETTINGS
        if SETTINGS['one_rock_edge']:
            # one edge, corner to corner through a ridge near the middle,
            # ending on the corners (lines end on a node of what they meet)
            # Edges meet at a ridge near the middle and end on corners: as few
            # lines as possible, the first two corners as one line through it.
            c = g.centroid
            far = max(corners, key=lambda p: math.dist(p, (c.x, c.y)))
            ridge = (c.x + (far[0] - c.x) * 0.2, c.y + (far[1] - c.y) * 0.2)
            by_angle = sorted(corners, key=lambda p: math.atan2(p[1] - ridge[1], p[0] - ridge[0]))
            k = 3 if len(corners) >= 5 and size > 1.6 else 2
            step = len(by_angle) / k
            chosen = [by_angle[int(i * step)] for i in range(k)]
            e = Obj('line', 'line rock-edge', [])
            e.set_segments([[chosen[0][0], chosen[0][1]], [ridge[0], ridge[1]], [chosen[1][0], chosen[1][1]]])
            out.append(e)
            for p in chosen[2:]:
                e = Obj('line', 'line rock-edge', [])
                e.set_segments([[ridge[0], ridge[1]], [p[0], p[1]]])
                out.append(e)
            continue
        # a ridge point a little off the middle, joined to the corners
        # furthest round from each other
        c = g.centroid
        far = max(corners, key=lambda p: math.dist(p, (c.x, c.y)))
        rx = c.x + (far[0] - c.x) * 0.25
        ry = c.y + (far[1] - c.y) * 0.25
        by_angle = sorted(corners, key=lambda p: math.atan2(p[1] - ry, p[0] - rx))
        k = 3 if len(corners) >= 5 and size > 1.6 else 2
        step = len(by_angle) / k
        chosen = [by_angle[int(i * step)] for i in range(k)]
        for p in chosen:
            e = Obj('line', 'line rock-edge', [])
            # stop just short of the corner, as hand-drawn edges do
            e.set_segments([[rx, ry], [p[0] + (rx - p[0]) * 0.08, p[1] + (ry - p[1]) * 0.08]])
            out.append(e)
    objs[:] = out
    return n


def pleasing_rocks(objs, K):
    """Each rock redrawn by `rock`, its edges after it, the rocks lower on
    the page after (in front of) those above (rocks drawn later clip those
    before). Returns how many."""
    rocks, rest = [], []
    for o in objs:
        if o.kind == 'drop' or (o.kind == 'line' and o.head.startswith('line rock-edge')):
            continue                                  # edges redrawn
        if o.kind == 'line' and o.head.startswith('line rock-border') and len(o.segments()) > 3:
            corners, edges = rock(bezier_points(o.segments()), K)
            if corners:
                o.set_segments([[x, y] for x, y in corners + [corners[0]]])
                rocks.append((o, edges))
                continue
        rest.append(o)
    rocks.sort(key=lambda r: -min(p[-1] for p in r[0].segments()))
    out = []
    for o, edges in rocks:
        out.append(o)
        for e in edges:
            x = Obj('line', 'line rock-edge', [])
            x.set_segments(e)
            out.append(x)
    # the rocks where the first of them was (areas and borders before, other symbols after)
    first = next((i for i, o in enumerate(objs) if o.kind == 'line' and o.head.startswith('line rock-border')), None)
    k = len([o for o in objs[:first] if o in rest]) if first is not None else len(rest)
    objs[:] = rest[:k] + out + rest[k:]
    return len(rocks)


def redo_file(path, splays=None, only=None):
    raw = open(path, 'rb').read()
    t = raw.decode('utf-8').replace('\r\n', '\n')
    survey = _survey_of(path)
    splays = splays or Splays.from_drawing(path, survey)
    out, pos, report = [], 0, []
    for m in re.finditer(r'^(scrap (\S+)[^\n]*)\n(.*?)^endscrap', t, re.S | re.M):
        header, name, body = m.group(1), m.group(2), m.group(3)
        if '-projection plan' not in header or name.endswith('XS') or name.endswith('XSTop'):
            continue
        if only and name not in only:
            continue
        K = scale_of(header)
        objs = parse_scrap(body)
        legs = _legs(objs, splays, survey)
        from .settings import SETTINGS
        # interior_borders: lines inside the passage stay borders; a step is
        # recognised by its symbol in the sketch, not guessed from its length.
        steps = 0 if SETTINGS['interior_borders'] else floor_steps(objs, K, legs)
        blocks = boulders(objs, K)
        out.append(t[pos:m.start(3)] + '\n'.join(o.text() for o in objs).rstrip('\n') + '\n')
        pos = m.end(3)
        report.append((name, steps, blocks))
    out.append(t[pos:])
    t = ''.join(out)
    if b'\r\n' in raw:
        t = t.replace('\n', '\r\n')
    open(path, 'wb').write(t.encode('utf-8'))
    return report
