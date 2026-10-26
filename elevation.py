# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""What an extended-elevation sketch shows besides walls, read by shape
(colour is only a hint):

- a straight, level blue stroke is a pool's surface: an `area water`
  below it, its surface kept level with `adjust horizontal`, and a bowl
  drawn under it where the sketch shows no floor;
- other blue strokes are water flow: a `water-flow` point under the floor
  (in an elevation the stream runs below what is drawn), pointing
  downhill along it;
- a steep green stroke hanging from the roof is a curtain (a point);
- green drawn as boulders (closed loops, or a gentle, humpy line) is
  rock on the floor: a wall `subtype blocks`, a cluster of loops making
  one wall along their top;
- a closed black loop holding no station is a rock: `rock-border`;
- short brown curls along the floor are rubble: dropped, and the floor
  next to them `subtype debris`.

    feats = features(lines, stations)       # lines: [(colour, points)] in metres
    feats.lines                             # what is left for walls and marks
    th2(feats, poly, walls, px, name)       # th2 lines for one scrap
"""
import math

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from .marks import span, length
from .walls import bezier_closed, bezier_lines

CURL_RATIO = 1.5        # brown: path over span at least this ...
CURL_SPAN = 1.5         # ... and spanning under this (m) is a curl of rubble
DEBRIS_REACH = 0.5      # m: floor within this of a curl is debris
FLOW_BELOW = 0.3        # m: a water-flow point this far under the floor (as drawn by hand)
POOL_SLOPE = 0.15       # a pool surface rises at most this per metre
POOL_DEPTH = 0.15       # a bowl drawn under a pool: this times its width deep
LOOP_GAP = 0.15         # m: ends this close make a closed loop (or 15% of its length)


def _closed(pp):
    return len(pp) > 3 and math.dist(pp[0], pp[-1]) < max(LOOP_GAP, 0.15 * length(pp))


def _straightness(pp):
    L = LineString([pp[0], pp[-1]])
    if L.length < 1e-6:
        return 0.0
    return max(L.distance(Point(p)) for p in pp)


def is_curl(pp):
    """A short brown squiggle or small loop: rubble, not a floor."""
    s = span(pp)
    return s < CURL_SPAN and length(pp) >= CURL_RATIO * max(s, 1e-6)


def is_curtain(pp):
    """A steep, open green stroke at least a metre long: a curtain hanging
    from the roof (the strokes of a stalactite's "Y" are shorter)."""
    if _closed(pp) or length(pp) < 1.0:
        return False
    dx = max(p[0] for p in pp) - min(p[0] for p in pp)
    dy = max(p[1] for p in pp) - min(p[1] for p in pp)
    return dy >= 1.5 * max(dx, 1e-6)


def is_blocks(pp):
    """Green drawn as boulders: a closed loop, much longer than its outline
    smoothed at 15 cm, or a gentle line with humps (flowstone is smooth, or
    steep where it runs down a step)."""
    if _closed(pp):
        return True
    L = LineString(pp)
    if L.length > 1.3 * max(L.simplify(0.15).length, 1e-6):
        return True
    a, b = pp[0], pp[-1]
    gentle = abs(b[1] - a[1]) <= math.tan(math.radians(35)) * abs(b[0] - a[0])
    return gentle and _straightness(pp) > 0.2 * L.length


def is_pool_surface(pp):
    """A straight, level blue stroke."""
    dx = abs(pp[-1][0] - pp[0][0])
    return (length(pp) >= 0.4 and _straightness(pp) < 0.08
            and abs(pp[-1][1] - pp[0][1]) <= POOL_SLOPE * dx)


def _top(pps, step=0.1):
    """The upper outline of a group of strokes, sampled every `step` m."""
    pts = [p for pp in pps for p in pp]
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    n = max(2, int((x1 - x0) / step) + 1)
    g = unary_union([LineString(pp) if len(pp) > 1 else Point(pp[0]) for pp in pps]).buffer(0.02)
    out = []
    for i in range(n):
        x = x0 + (x1 - x0) * i / (n - 1)
        cut = g.intersection(LineString([(x, -1e5), (x, 1e5)]))
        if not cut.is_empty:
            out.append((x, cut.bounds[3] - 0.02))
    return LineString(out).simplify(0.05).coords[:] if len(out) > 1 else []


def _bottom(pps, step=0.1):
    """The lower outline of a group of strokes, sampled every `step` m."""
    flip = lambda pp: [(x, -y) for x, y in pp]
    return [(x, -y) for x, y in _top([flip(pp) for pp in pps], step)]


BOULDER_MAX = 1.5       # m: a closed stroke up to this long is a boulder
FLOOR_GAP = 1.0         # m: boulders this close are one row
FLOOR_ROW = 4           # boulders in a row along the floor make a floor
FLOOR_COVER = 1.0       # m: a floor line drawn within this under the row is the floor already
FLOOR_SMOOTH = 1.0      # m: a floor over a row of rocks follows their tops, averaged over this
ROW_LINE = 0.5          # m: or through the row or this far above it (rocks drawn along a floor line)


def _curled(pp):
    """A mark that bends back on itself (a curl or a loop), not a straight dash."""
    return _closed(pp) or (len(pp) > 2 and length(pp) > 1.3 * math.dist(pp[0], pp[-1]))


def boulder_floor(lines):
    """A floor drawn only as a row of marks (boulders, small closed loops,
    or short brown curls and dashes; no line under or through them) is a floor: a line
    through the tops of the rocks, smoothed (user: BoldStep 12 to 11, rocks are only
    drawn: imagine a line through their tops), where no line is drawn under it. Returns
    [(points, 'debris')]: only where most marks are curled (straight dashes
    are mud marked on a floor drawn elsewhere)."""
    loops = [pp for c, pp in lines if len(pp) > 1 and length(pp) <= BOULDER_MAX and (
             (c in ('BROWN', 'BLACK', 'GREEN') and len(pp) > 3 and _closed(pp)) or c == 'BROWN')]
    rows = []
    for pp in loops:
        L = LineString(pp)
        hit = [r for r in rows if any(L.distance(LineString(q)) < FLOOR_GAP for q in r)]
        for r in hit:
            rows.remove(r)
        rows.append(sum(hit, []) + [pp])
    marks = {id(pp) for pp in loops}
    drawn = [LineString(pp) for c, pp in lines if len(pp) > 1 and not _closed(pp) and length(pp) >= 0.5
             and id(pp) not in marks]
    out = []
    for r in rows:
        xs = [p[0] for pp in r for p in pp]
        if len(r) < FLOOR_ROW or max(xs) - min(xs) < 2.0:
            continue
        if sum(_curled(pp) for pp in r) * 2 < len(r):
            continue                    # straight dashes: mud marked on a floor, not a floor
        kind = 'debris'
        run = []
        top = LineString(_top(r)) if len(_top(r)) > 1 else None
        for q in _bottom(r):
            # a line drawn under the row, through it or just over it (debris drawn as small
            # rocks along a floor line: FairyChimneys 25 to 28), is the floor already
            up = top.intersection(LineString([(q[0], -1e5), (q[0], 1e5)])).bounds[3] if top else q[1]
            below = LineString([(q[0], max(up, q[1]) + ROW_LINE), (q[0], q[1] - FLOOR_COVER)])
            if any(d.intersects(below) or d.distance(Point(q)) < 0.1 for d in drawn):
                if length(run) >= 1.0:
                    out.append((run, kind))
                run = []
            else:
                run.append(q)
        if length(run) >= 1.0:
            out.append((run, kind))
    return [(_over_tops(run, top), kind) if top else (run, kind) for run, kind in out]


def _over_tops(run, top, half=FLOOR_SMOOTH / 2):
    """The floor over a run of the row: the tops of its rocks (joined across the
    gaps between them), as a running mean over FLOOR_SMOOTH m."""
    def y_at(x):
        cut = top.intersection(LineString([(x, -1e5), (x, 1e5)]))
        return cut.bounds[3] if not cut.is_empty else None
    xs = [q[0] for q in run]
    tops = [(x, y_at(x)) for x in xs]
    tops = [(x, y) for x, y in tops if y is not None]
    if len(tops) < 2:
        return run
    out = []
    for x, _ in tops:
        near = [y for x2, y in tops if abs(x2 - x) <= half]
        out.append((x, sum(near) / len(near)))
    return LineString(out).simplify(0.05).coords[:]


class Features:
    def __init__(self):
        self.lines = []         # [(colour, points)] left for walls and marks
        self.kinds = {}         # id(points) -> wall subtype it is drawn as
        self.debris = []        # curls: [points]
        self.rocks = []         # closed black loops: [points]
        self.pillars = []       # closed black loops the survey goes round (legs above and below)
        self.overhangs = []     # lines with ticks hanging from them: [points], ticks on the left
        self.curtains = []      # [(x, y)]
        self.flows = []         # clusters of blue strokes: [[points]]
        self.pools = []         # (x0, x1, level)
        self.bowls = []         # per pool: a bowl drawn under it (a wall stroke), or None


PILLAR = 0.5        # m across or more, with legs above and below it within PILLAR_REACH: a pillar
PILLAR_REACH = 3.0


def pillars_apart(f, legs):
    """Closed black loops with a leg above and one below them (the survey
    going round, a loop in the data) are pillars, not rocks (the user:
    TritonSouth 13 to 21, `equate 13 21`)."""
    segs = [LineString(l) for l in legs if l[0] != l[1]]
    keep = []
    for pp in f.rocks:
        g = Polygon(pp).buffer(0)
        if g.is_empty or math.sqrt(g.area) < PILLAR:
            keep.append(pp)
            continue
        c = g.centroid
        x0, y0, x1, y1 = g.bounds
        up = LineString([(c.x, y1), (c.x, y1 + PILLAR_REACH)])
        down = LineString([(c.x, y0), (c.x, y0 - PILLAR_REACH)])
        if any(s.intersects(up) for s in segs) and any(s.intersects(down) for s in segs):
            f.pillars.append(pp)
        else:
            keep.append(pp)
    f.rocks = keep


TICK = (0.08, 0.45)     # m: a tick's length
TICK_ON = 0.12          # m: a tick starts this near its line (TritonSouth by 6: 0.1)
TICKS = 3               # ticks on one side make a line an overhang


def _overhangs(lines):
    """(overhangs [points, ticks on the left], the lines left): a line
    (0.8 m or more) with TICKS or more short strokes of its colour starting
    on it and leaving it across, all to one side, is an overhang (the user:
    BoldStep by 4, TritonSouth by 6)."""
    used, out = set(), []
    for i, (c, pp) in enumerate(lines):
        if len(pp) < 2 or length(pp) < 0.8 or c == 'BROWN':     # (brown curls under a floor are its rubble)
            continue
        main = LineString(pp)
        sides = []
        ticks = []
        for j, (c2, qq) in enumerate(lines):
            if j == i or c2 != c or len(qq) < 2 or not TICK[0] <= length(qq) <= TICK[1] \
                    or math.dist(qq[0], qq[-1]) < 0.7 * length(qq):
                continue                           # (a tick is short and straight)
            a, b = (qq[0], qq[-1]) if main.distance(Point(qq[0])) <= main.distance(Point(qq[-1])) else (qq[-1], qq[0])
            if main.distance(Point(a)) > TICK_ON or main.distance(Point(b)) < 0.6 * math.dist(a, b):
                continue                       # not starting on it, or running along it
            d = main.project(Point(a))
            p0, p1 = main.interpolate(max(0.0, d - 0.05)), main.interpolate(min(main.length, d + 0.05))
            cross = (p1.x - p0.x) * (b[1] - p0.y) - (p1.y - p0.y) * (b[0] - p0.x)
            sides.append(1 if cross > 0 else -1)
            ticks.append(j)
        if len(ticks) >= TICKS and abs(sum(sides)) >= TICKS:
            out.append(list(pp) if sum(sides) > 0 else list(pp)[::-1])
            used |= {i, *ticks}
    return out, [l for k, l in enumerate(lines) if k not in used]


def features(lines, stations=()):
    f = Features()
    st = [Point(p) for p in stations]
    f.overhangs, lines = _overhangs(list(lines))
    green_small, hung = [], []
    for c, pp in lines:
        if not pp or len(pp) < 2:
            f.lines.append((c, pp))
            continue
        if c == 'BLUE':
            if is_pool_surface(pp):
                y = sum(p[1] for p in pp) / len(pp)
                f.pools.append((min(pp[0][0], pp[-1][0]), max(pp[0][0], pp[-1][0]), y))
            elif length(pp) >= 0.3:
                hit = [g for g in f.flows if any(LineString(q).distance(LineString(pp)) < 0.6 for q in g)]
                for g in hit:
                    f.flows.remove(g)
                f.flows.append(sum(hit, []) + [pp])
            continue
        if c == 'BLACK' and _closed(pp) and length(pp) >= 0.5:
            poly = Polygon(pp).buffer(0)
            if poly.area >= 0.05 and not any(poly.contains(s) for s in st):
                f.rocks.append(pp)
                continue
        if c == 'BROWN' and length(pp) >= 1.0 and is_curl(pp):
            f.debris.append(pp)
            continue
        if c == 'GREEN':
            if is_curtain(pp):
                xs = sorted(pp, key=lambda p: p[1])
                f.curtains.append(xs[len(xs) // 2])
                hung.append(LineString(pp))
                continue
            if _closed(pp) or length(pp) < 1.0 or is_blocks(pp):
                green_small.append(pp)
                continue
        f.lines.append((c, pp))
    # short green strokes at a curtain are part of it
    by_curtain = lambda pp: any(h.distance(LineString(pp)) < 0.3 for h in hung)
    f.lines = [(c, pp) for c, pp in f.lines if not (c == 'GREEN' and len(pp) > 1 and by_curtain(pp))]
    green_small = [pp for pp in green_small if not by_curtain(pp)]
    # green boulders: a cluster with a loop or a humpy stroke in it is one floor of blocks
    groups = []
    for pp in green_small:
        L = LineString(pp)
        hit = [g for g in groups if any(L.distance(LineString(q)) < 0.3 for q in g)]
        for g in hit:
            groups.remove(g)
        groups.append(sum(hit, []) + [pp])
    for g in groups:
        if not any(_closed(pp) or is_blocks(pp) for pp in g):
            f.lines += [('GREEN', pp) for pp in g]       # the "Y" of a stalactite and the like
            continue
        top = g[0] if len(g) == 1 and not _closed(g[0]) else _top(g)
        if len(top) > 1:
            top = list(top)
            f.lines.append(('GREEN', top))
            f.kinds[id(top)] = 'blocks'
    for pp, kind in boulder_floor(f.lines + [('BLACK', r) for r in f.rocks] + [('BROWN', d) for d in f.debris]):
        pp = list(pp)
        f.lines.append(('BROWN', pp))
        f.kinds[id(pp)] = kind
    return f


def _floor_below(walls, p, reach=2.0):
    """(point on the nearest wall straight below p, downhill bearing there)."""
    ray = LineString([p, (p[0], p[1] - reach)])
    best = None
    for w in walls:
        if len(w) < 2:
            continue
        L = LineString(w)
        cut = L.intersection(ray)
        for q in getattr(cut, 'geoms', [cut]):
            if q.is_empty or q.geom_type != 'Point':
                continue
            if best is None or q.y > best[0].y:
                best = (q, L)
    if best is None:
        return None
    q, L = best
    d = L.project(q)
    a, b = L.interpolate(max(0.0, d - 0.3)), L.interpolate(min(L.length, d + 0.3))
    if b.y > a.y:
        a, b = b, a
    return (q.x, q.y), math.degrees(math.atan2(b.x - a.x, b.y - a.y)) % 360


def bowls(f, walls, deep=1.0):
    """For each pool with no floor drawn under it (no wall within `deep` m
    below its surface), a bowl under it, as a wall stroke; None where the
    sketch shows the floor. Sets f.bowls."""
    f.bowls = []
    for x0, x1, y in f.pools:
        w = x1 - x0
        floor = 0
        for x in (x0 + w / 4, (x0 + x1) / 2, x1 - w / 4):
            ray = LineString([(x, y - 0.02), (x, y - deep)])
            floor += any(LineString(q).intersects(ray) for q in walls if len(q) > 1)
        if floor >= 2:
            f.bowls.append(None)
            continue
        d = min(0.5, max(0.1, POOL_DEPTH * w))
        f.bowls.append([(x0, y), (x0 + w / 4, y - d), (x1 - w / 4, y - d), (x1, y)])
    return [b for b in f.bowls if b]


def _water(x0, x1, y, bowl, poly):
    if bowl:
        return Polygon(bowl)
    under = poly.intersection(box(x0, y - 2.0, x1, y))
    if under.geom_type != 'Polygon':
        parts = [g for g in getattr(under, 'geoms', []) if g.geom_type == 'Polygon']
        under = max(parts, key=lambda g: g.area) if parts else Polygon()
    return under


def _under_surface(water, y):
    """The water polygon's boundary below its surface at y, from the x1 end
    back to the x0 end (to follow the surface drawn x0 to x1)."""
    from shapely.geometry.polygon import orient
    cs = list(orient(water, 1.0).exterior.coords[:-1])        # anticlockwise: the top runs right to left
    top = [i for i, p in enumerate(cs) if abs(p[1] - y) < 1e-6]
    if top:
        i0 = min(top, key=lambda i: cs[i][0])                  # the top's left end
        cs = cs[i0 + 1:] + cs[:i0 + 1]
    return [p for p in reversed(cs) if abs(p[1] - y) >= 1e-6]


def th2(f, poly, walls, px, name):
    """th2 lines for the features inside scrap polygon `poly`."""
    o = []
    near = poly.buffer(0.5)
    for k, (x0, x1, y) in enumerate(f.pools):
        if not near.intersects(LineString([(x0, y), (x1, y)])):
            continue
        bowl = f.bowls[k] if k < len(getattr(f, 'bowls', [])) else None
        water = _water(x0, x1, y, bowl, poly)
        if water.is_empty:
            continue
        lid = f"{name}-pool{k + 1}"
        ring = _under_surface(water, y)
        o += [f"line border -id {lid} -close on -subtype invisible",
              "  %.2f %.2f" % px((x0, y)), "  %.2f %.2f" % px((x1, y)), "  adjust horizontal"] + \
             ["  %.2f %.2f" % px(p) for p in ring] + ["endline", "",
              "area water", f"  {lid}", "endarea", ""]
    for pp in f.rocks:
        if near.contains(Point(pp[0])):
            o += ["line rock-border -close on"] + ["  %.2f %.2f" % px(p) for p in
                                                   LineString(pp).simplify(0.05).coords[:-1]] + ["endline", ""]
    for pp in f.overhangs:
        if near.intersects(LineString(pp)):
            q = list(LineString(pp).simplify(0.03).coords)
            o += ["line overhang"] + bezier_lines(q, px) + ["endline", ""]
    for pp in f.pillars:                 # rock the passage goes round: a wall of its own (TritonSouth 13)
        if near.contains(Point(pp[0])):
            q = list(LineString(pp).simplify(0.03).coords)
            if q[0] != q[-1]:
                q.append(q[0])
            o += ["line wall -outline in -close on"] + bezier_closed(q, px) + ["endline", ""]
    for c in f.curtains:
        if near.contains(Point(c)):
            o += ["point %.2f %.2f curtain" % px(c), ""]
    for g in f.flows:
        pts = [p for pp in g for p in pp]
        c = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        if not near.contains(Point(c)):
            continue
        hit = _floor_below(walls, c)
        if hit:
            (x, yf), ori = hit
            o += ["point %.2f %.2f water-flow -orientation %.1f" % (*px((x, yf - FLOW_BELOW)), ori), ""]
        else:
            o += ["point %.2f %.2f water-flow" % px(c), ""]
    return o


def debris_marks(f, px):
    """`# wall-subtype debris <reach>: ...` for smooth.wall_subtypes."""
    return [f"# wall-subtype debris {DEBRIS_REACH}: " + " ".join("%.1f %.1f" % px(p) for p in pp)
            for pp in f.debris]
