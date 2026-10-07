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

    python3 -m tools.sketch2therion details FILE.th2 [...]   (after a build)
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


def boulders(objs, K):
    """Clean polygons with facet edges. Returns how many were redrawn."""
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


def redo_file(path, splays=None, only=None):
    splays = splays or Splays()
    raw = open(path, 'rb').read()
    t = raw.decode('utf-8').replace('\r\n', '\n')
    survey = _survey_of(path)
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
        steps = floor_steps(objs, K, legs)
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
