# Ported from caves-mendip-swildons, tools/sketch2therion (commit 198bf46,
# https://github.com/paperclipmonkey/caves-mendip-swildons). GPLv3: see LICENSE.
"""Sketch -> th2: plan scraps, extended-elevation scraps and cross sections.

What each colour becomes (the same in SexyTopo and PocketTopo):

    black          walls; small closed loops are boulders, thin tapering
                   triangles slope arrows
    brown, grey    walls too (other levels, overlapping passages); where
                   they run inside the passage they are drawn as borders
    blue           water: hatching and closed outlines become pools,
                   squiggles water-flow arrows
    green          formations (flowstone, stalagmites, stalactites)
    red, orange,   ignored: use them for notes, text and anything that
    purple         shouldn't be drawn

Lines along the edge of the passage are walls; lines inside it are thin
borders (ledges, channels, the edge of a level above). The passage fill
is an invisible outline around all of them, and in an extended elevation
also a band from the floor to the roof along the survey legs.
"""
import math
import os
import sys

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from . import register
from .features import classify, centroid
from .symbols import split_symbols, symbols_th2
from .walls import clean, bezier_lines, bezier_closed, chaikin, split_by_edge
from .settings import SETTINGS

WALLS = ('BLACK', 'BROWN', 'GRAY')


def is_outline(pp):
    """False for short marks and straight out-and-back strokes (a dive line
    or a leader to a note)."""
    path = sum(math.dist(a, b) for a, b in zip(pp, pp[1:]))
    if path < 1.0:
        return False
    s = pp[::3] + [pp[-1]]
    (x1, y1), (x2, y2) = max(((p, q) for p in s for q in s), key=lambda pq: math.dist(*pq))
    L = math.dist((x1, y1), (x2, y2)) or 1
    straight = max(abs((x2 - x1) * (y1 - y) - (x1 - x) * (y2 - y1)) / L for x, y in pp) < 0.15
    return not (straight and path > 1.5 * L)


LINK_MIN = 0.3      # m: a short stroke in a wall colour this long or more, joined to the wall at both ends, is wall
LINK_MEET = 0.3     # m: ends this close are joined


def wall_strokes(lines):
    """(wall strokes, boulders, slope arrows) from the sketch lines."""
    black = [pp for c, pp in lines if c == 'BLACK' and len(pp) > 1
             and sum(math.dist(a, b) for a, b in zip(pp, pp[1:])) >= 0.15]
    hooks = []
    if SETTINGS['wall_hooks']:
        # a small loop left open with an end at another black stroke is a hook
        # of the wall (a projection the wall goes round), not a boulder
        from .symbols import shape_of
        lines_ = [LineString(pp) for pp in black]
        for k, pp in enumerate(black):
            if shape_of(pp)[0] != 'boulder' or math.dist(pp[0], pp[-1]) < 0.05:
                continue
            others = [l for j, l in enumerate(lines_) if j != k]
            if any(l.distance(Point(e)) < 0.15 for e in (pp[0], pp[-1]) for l in others):
                hooks.append(pp)
        black = [pp for pp in black if not any(pp is h for h in hooks)]
    black, boulders, arrows = split_symbols(black)
    black += hooks
    cols = [c for c in SETTINGS['wall_colours'] if c != 'BLACK']
    other = [pp for c, pp in lines if c in cols and len(pp) > 1 and is_outline(pp)]
    # short pieces of a wall drawn in a wall colour, joined end to end at both ends to the
    # wall (FairyChimneys 9: the floor under it, brown then green flowstone in short strokes)
    walls = black + other
    if not SETTINGS.get('short_links'):
        return walls, boulders, arrows
    short = [pp for c, pp in lines if c in cols and len(pp) > 1 and not any(pp is q for q in other)
             and LINK_MIN <= sum(math.dist(a, b) for a, b in zip(pp, pp[1:])) and math.dist(pp[0], pp[-1]) >= LINK_MIN]
    meets = lambda e, qs: any(min(math.dist(e, q[0]), math.dist(e, q[-1])) < LINK_MEET for q in qs)
    changed = True
    while changed:
        changed = False
        for pp in list(short):
            rest = walls + [q for q in short if q is not pp]
            if not (meets(pp[0], rest) and meets(pp[-1], rest)):
                short = [q for q in short if q is not pp]
                changed = True
    return walls + short, boulders, arrows


def _lerp_pt(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _polygons(g, min_area=0.5):
    if g.is_empty:
        return []
    ps = [g] if g.geom_type == 'Polygon' else [p for p in getattr(g, 'geoms', []) if p.geom_type == 'Polygon']
    return [Polygon(p.exterior).simplify(0.03) for p in ps if p.area >= min_area]


def plan_fill(walls, legs, extra=()):
    """Passage polygons: walls, legs and water closed up by 1.8 m."""
    g = unary_union([LineString(w) for w in walls] + [LineString(l) for l in legs] +
                    [LineString(e) for e in extra if len(e) > 1])
    return _polygons(g.buffer(1.8, join_style=1).buffer(-1.72, join_style=1))


def elevation_fill(walls, legs, extra=(), below=3.0, above=5.0, stops=(), side=0.0):
    """As plan_fill, plus a band from floor to roof along each leg: the nearest
    sketch line below (within `below` m) and above (within `above` m), every
    20 cm. Where either is missing no band is drawn, so a gap in the sketch
    stays a gap instead of filling the space between passages. `stops`: walls
    of other scraps, where a band also stops (a passage above or below this
    one: its floor is this one's roof). Along a steep leg (a pitch) the band
    also goes sideways, to the nearest line on each side within `side` m."""
    segs = [(a, b) for w in list(walls) + list(stops) for a, b in zip(w, w[1:]) if abs(b[0] - a[0]) > 1e-6]
    across = [(a, b) for w in list(walls) + list(stops) for a, b in zip(w, w[1:]) if abs(b[1] - a[1]) > 1e-6]
    boxes = []
    for A, B in legs if side else ():
        if abs(B[1] - A[1]) <= abs(B[0] - A[0]):        # not steep
            continue
        n = max(1, int(abs(B[1] - A[1]) / 0.2))
        for i in range(n + 1):
            t = i / n
            x = A[0] + (B[0] - A[0]) * t
            y = A[1] + (B[1] - A[1]) * t
            xs = [a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1])
                  for a, b in across if min(a[1], b[1]) <= y <= max(a[1], b[1])]
            lo = [v for v in xs if x - side <= v <= x]
            hi = [v for v in xs if x <= v <= x + side]
            if lo and hi:
                boxes.append(box(max(lo), y - 0.15, min(hi), y + 0.15))
    for A, B in legs:
        if abs(B[0] - A[0]) < 0.05:
            continue
        n = max(1, int(abs(B[0] - A[0]) / 0.2))
        for i in range(n + 1):
            t = i / n
            x = A[0] + (B[0] - A[0]) * t
            y = A[1] + (B[1] - A[1]) * t
            ys = [a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0])
                  for a, b in segs if min(a[0], b[0]) <= x <= max(a[0], b[0])]
            lo = [v for v in ys if y - below <= v <= y]
            hi = [v for v in ys if y <= v <= y + above]
            if lo and hi:
                boxes.append(box(x - 0.15, max(lo), x + 0.15, min(hi)))
    g = unary_union([LineString(w) for w in list(walls) + list(extra) if len(w) > 1] +
                    [LineString(l) for l in legs]).buffer(1.8, join_style=1).buffer(-1.72, join_style=1)
    if boxes:
        g = unary_union([g, unary_union(boxes).buffer(0.3, join_style=1).buffer(-0.3, join_style=1)])
    return _polygons(g)


# -- th2 pieces ------------------------------------------------------------------

def splay_supported(run, splay_ends, near=0.25, need=2):
    """True if at least `need` splay ends lie within `near` m of the stroke:
    splays are measured to the walls, so it is a wall."""
    line = LineString(run)
    return sum(1 for e in splay_ends if line.distance(Point(e)) < near) >= need


def _leg_in_cone(p, d, legs, reach, cone):
    """True if the nearest point of the survey legs is within `reach` of p
    and within `cone` degrees of the direction d (a passage round a corner
    has its leg off to one side, not straight across from the wall)."""
    from shapely.ops import nearest_points
    q = nearest_points(p, legs)[1]
    vx, vy = q.x - p.x, q.y - p.y
    L = math.hypot(vx, vy)
    if L == 0 or L > reach:
        return False
    return (vx * d[0] + vy * d[1]) / L >= math.cos(math.radians(cone))


def traced_outer(run, poly, others, legs, samples=5, reach=20.0, leg_reach=8.0, cone=0.0):
    """(side, width) if, for most of the stroke, tracing out to one side
    (+1 left, -1 right) reaches the edge of the passage fill without
    crossing another wall stroke or a survey leg, while the other side has
    a survey leg (the passage); else None. width: how far the fill goes on
    beyond the stroke there (median). The fill's closing-up bridges a
    wall's inward bends, leaving the real wall inside it; a pillar's wall
    fails, as tracing through the pillar meets its far wall. With `cone`
    (degrees), the leg may also be off to one side within that angle of
    straight across, as at a corner ([convert] corner_cone)."""
    line = LineString(run)
    if line.length < 0.3:
        return None
    found = {1: [], -1: []}
    for k in range(samples):
        d = line.length * (k + 0.5) / samples
        p = line.interpolate(d)
        a, b = line.interpolate(max(0.0, d - 0.1)), line.interpolate(min(line.length, d + 0.1))
        n = math.hypot(b.x - a.x, b.y - a.y) or 1.0
        nx, ny = -(b.y - a.y) / n, (b.x - a.x) / n
        for s in (1, -1):
            # from 0.3 m out: a stroke drawn again just beside it is the same wall
            ray = LineString([(p.x + nx * 0.3 * s, p.y + ny * 0.3 * s), (p.x + nx * reach * s, p.y + ny * reach * s)])
            inside = ray.intersection(poly)
            parts = [g for g in getattr(inside, 'geoms', [inside]) if g.geom_type == 'LineString' and not g.is_empty]
            first = min(parts, key=lambda g: g.distance(p), default=None)
            if first is not None and (first.intersects(others) or first.intersects(legs)):
                continue
            back = LineString([(p.x - nx * 0.05 * s, p.y - ny * 0.05 * s),
                               (p.x - nx * leg_reach * s, p.y - ny * leg_reach * s)])
            if back.intersects(legs) or (cone and _leg_in_cone(p, (-nx * s, -ny * s), legs, leg_reach, cone)):
                found[s].append(0.0 if first is None else first.distance(p) + first.length)
    s = max(found, key=lambda k: len(found[k]))
    if len(found[s]) * 2 <= samples:
        return None
    w = sorted(found[s])[len(found[s]) // 2]
    return s, w


def side_away_from_legs(run, legs):
    """+1 if the survey legs are on the stroke's right (so its left is outside), else -1."""
    line = LineString(run)
    p = line.interpolate(0.5, normalized=True)
    a, b = line.interpolate(0.45, normalized=True), line.interpolate(0.55, normalized=True)
    n = math.hypot(b.x - a.x, b.y - a.y) or 1.0
    nx, ny = -(b.y - a.y) / n, (b.x - a.x) / n
    left = LineString([(p.x, p.y), (p.x + nx * 8, p.y + ny * 8)]).intersects(legs)
    return -1 if left else 1


def cut_back(poly, walls, legs, splay_ends):
    """The passage fill cut back to the outer walls it bridged: for each
    wall piece inside the fill that splays end on, or with nothing between
    it and the fill's edge on one side, the strip beyond it is removed (if
    no survey leg or other stroke is in it). Those pieces then lie on the
    fill's edge and are drawn as wall."""
    leg_lines = unary_union([LineString(l) for l in legs if len(l) > 1])
    if leg_lines.is_empty:
        return poly
    cuts = []
    for w in walls:
        if len(w) < 2 or not LineString(w).intersects(poly):
            continue
        others = unary_union([LineString(x) for x in walls if x is not w and len(x) > 1])
        for edge, run in split_by_edge(w, list(poly.exterior.coords)):
            if edge or len(run) < 2:
                continue
            t = traced_outer(run, poly, others, leg_lines, cone=SETTINGS['corner_cone'])
            if t is None and splay_supported(run, splay_ends):
                t = (side_away_from_legs(run, leg_lines), 1.0)
            if t is None:
                continue
            side, width = t
            strip = LineString(run).buffer(side * min(3.0, width + 0.1), single_sided=True, cap_style=2)
            cut = strip.intersection(poly)
            if cut.is_empty or cut.intersects(leg_lines) or cut.buffer(-0.02).intersects(others):
                continue
            cuts.append(cut)
    if not cuts:
        return poly
    g = poly.difference(unary_union(cuts)).buffer(0)
    if g.geom_type == 'MultiPolygon':
        g = max(g.geoms, key=lambda q: q.area)
    return g if g.geom_type == 'Polygon' and not g.is_empty else poly


def drop_rock_faces(poly, walls, legs, stations, seal=0.3, edge_seal=0.5, away=0.3, bridged_min=0.5, margin=0.02):
    """The passage fill without the rock its closing-up took in. The fill is
    cut into faces along the wall strokes (gaps the sketcher left, up to
    `seal` m between stroke ends, and up to `edge_seal` m from a stroke's
    end to the fill's edge, closed first); a face with no survey leg or
    station in it whose stretch along the fill's edge has at least `bridged_min` m more than
    `away` m from any stroke (the edge there was made by closing up, not
    sketched) is rock (the inside of a bend, a tongue between two
    branches, round a hook in the wall) and goes. A face wholly inside,
    such as a pillar, stays as before. A leg or station counts only more
    than `margin` m inside a face (a station at a passage's end may sit
    just outside its walls)."""
    from shapely.ops import polygonize
    from .tidy import overshoot
    strokes = [LineString(w) for w in walls if len(w) > 1]
    if not strokes:
        return poly
    ends = [Point(w[i]) for w in walls if len(w) > 1 for i in (0, -1)]
    seals = []
    edge = poly.exterior
    # each seal carried 1 cm on past where it lands, so that it crosses what it meets
    # (a point put on a line in floating point is not quite on it: the face stayed open)
    for e in ends:
        for st in strokes:
            d = st.distance(e)
            if 1e-9 < d <= seal:
                q = st.interpolate(st.project(e))
                seals.append(overshoot(e, q, 0.01))
        d = edge.distance(e)               # a stroke ending just short of the fill's edge reaches it
        if 1e-9 < d <= edge_seal:
            q = edge.interpolate(edge.project(e))
            seals.append(overshoot(e, q, 0.01))
    net = unary_union([poly.exterior] + [st.intersection(poly.buffer(0.01)) for st in strokes] + seals)
    faces = [f for f in polygonize(net) if f.area > 1e-6 and poly.buffer(0.01).contains(f.representative_point())]
    if len(faces) < 2:
        return poly
    # a leg that leaves through a sketched wall (to a station beyond the
    # drawing) does not make the rock it crosses passage; nor does a station
    # reached only by such legs
    allst = unary_union(strokes)
    inside_legs = [l for l in legs if len(l) > 1 and not LineString(l).crosses(allst)]
    out_legs = [l for l in legs if len(l) > 1 and LineString(l).crosses(allst)]
    reached = {tuple(p) for l in inside_legs for p in l}
    stations = [p for p in stations if tuple(p) in reached or not any(tuple(p) in map(tuple, l) for l in out_legs)]
    leg_lines = unary_union([LineString(l) for l in inside_legs])
    keep = []
    near_strokes = unary_union(strokes).buffer(away)
    for f in faces:
        has_leg = (not leg_lines.is_empty and f.buffer(-margin).intersects(leg_lines)) or \
            any(f.buffer(-margin).contains(Point(p)) for p in stations)
        along = f.boundary.intersection(edge.buffer(0.02))
        bridged = along.difference(near_strokes).length
        if has_leg or along.length < 0.05 or bridged < bridged_min:
            keep.append(f)
    g = unary_union(keep).buffer(0.01).buffer(-0.01)
    if g.geom_type == 'MultiPolygon':
        g = max(g.geoms, key=lambda q: q.area)
    if g.geom_type != 'Polygon' or g.is_empty or g.area < 0.5 * poly.area:
        return poly
    g = Polygon(g.exterior).buffer(0)
    if g.geom_type == 'MultiPolygon':
        g = max(g.geoms, key=lambda q: q.area)
    return g if g.geom_type == 'Polygon' and not g.is_empty else poly


def wall_runs(walls, poly):
    """[(is_wall, run)] for the wall strokes at this passage fill.

    A run along the fill's edge is wall, one inside it a border, except
    (with [convert] interior_borders) a run that is outside the fill, or
    is part of a stroke mostly drawn along the edge: one line, drawn on
    as the wall, is wall all along (the fill's closing-up can take in a
    stretch of it, such as a wall with a border drawn off it close by)."""
    ring = list(poly.exterior.coords)
    out = []
    for w in walls:
        if len(w) < 2 or not LineString(w).intersects(poly.buffer(0.3)):
            continue
        runs = [[edge, run] for edge, run in split_by_edge(w, ring) if len(run) > 1]
        if SETTINGS['interior_borders']:
            on_edge = sum(LineString(r).length for e, r in runs if e)
            if on_edge >= sum(LineString(r).length for e, r in runs if not e):
                runs = [[True, r] for _, r in runs]
            inner = poly.buffer(-0.05)
            for r in runs:
                if not r[0] and not inner.contains(LineString(r[1]).interpolate(0.5, normalized=True)):
                    r[0] = True          # an outer wall the fill missed
        out += [(e, r) for e, r in runs]
    return out


def walls_th2(walls, poly, px, legs=(), splay_ends=(), inner=None):
    """inner: what a wall inside the passage is drawn as (a border, or in an
    elevation `line wall -outline none`)."""
    ring = list(poly.exterior.coords)
    o = []
    for edge, run in wall_runs(walls, poly):
        if not edge and inner:
            o += [inner] + bezier_lines(run, px) + ["endline", ""]
            continue
        if not edge and SETTINGS['smooth_lines']:
            from .marks import smooth_rows
            o += ["line border -clip off"] + smooth_rows(run, px) + ["endline", ""]
            continue
        o += ["line wall -outline none" if edge else "line border -clip off"] + \
            bezier_lines(run, px) + ["endline", ""]
    o += ["line wall -subtype invisible -close on"] + ["  %.2f %.2f" % px(p) for p in ring[:-1]] + ["endline", ""]
    return o


def _bearing(a, b):
    return math.degrees(math.atan2(b[0] - a[0], b[1] - a[1])) % 360


def water_th2(lines, passage, px, idbase, legs=(), flow=True):
    """Pools, water-flow arrows and formations. Flow arrows point along the
    nearest leg in the direction it was surveyed: check them."""
    pools, flows, forms = classify(lines, passage)
    o = []
    for i, (_, g) in enumerate(pools):
        if g.geom_type != 'Polygon' or g.area < min(0.1, SETTINGS['pool_min_area']):
            continue
        lid = f"{idbase}-water{i + 1}"
        o += [f"line border -id {lid} -close on -clip off"] + \
             ["  %.2f %.2f" % px(p) for p in list(g.exterior.coords)[:-1]] + \
             ["endline", "", "area water -clip off", f"  {lid}", "endarea", ""]

    def along(p):
        best = None
        for a, b in legs:
            d = LineString([a, b]).distance(Point(p)) if a != b else 1e9
            if best is None or d < best[0]:
                best = (d, _bearing(a, b))
        return best[1] if best else 0.0

    if flow:
        for pp in flows:
            c = centroid(pp)
            if passage.buffer(0.3).contains(Point(c)):
                o += ["point %.2f %.2f water-flow -orientation %.1f" % (*px(c), along(c)), ""]
    for kind, c in forms:
        if not passage.buffer(0.3).contains(Point(c)):
            continue
        if kind == 'flowstone' and flow:
            o += ["point %.2f %.2f flowstone -orientation %.1f" % (*px(c), along(c)), ""]
        elif not flow and SETTINGS['elevation_features']:      # elevation: flowstone is a wall subtype
            if kind != 'flowstone':
                o += ["point %.2f %.2f %s" % (*px(c), 'stalactites' if kind == 'stalactite' else kind), ""]
        else:
            o += ["point %.2f %.2f %s" % (*px(c), kind), ""]
    return o


def header(xvi_path, out_path, anchor, anchor_xy, polys, px):
    xs = [px(p)[0] for g in polys for p in g.exterior.coords] or [0]
    ys = [px(p)[1] for g in polys for p in g.exterior.coords] or [0]
    o = ["encoding  utf-8",
         "##XTHERION## xth_me_area_adjust %.1f %.1f %.1f %.1f" % (min(xs) - 200, min(ys) - 200, max(xs) + 200, max(ys) + 200),
         "##XTHERION## xth_me_area_zoom_to 100"]
    if xvi_path:
        rel = os.path.relpath(xvi_path, os.path.dirname(os.path.abspath(out_path)) or '.').replace(os.sep, '/')
        o.append("##XTHERION## xth_me_image_insert {%.2f 1 1.0} {%.2f %s} {%s} 0 {}" % (anchor_xy[0], anchor_xy[1], anchor, rel))
    return o + ["", ""]


class Options:
    def __init__(self, name, survey=None, author=None, copyright=None, qualify=False, scraps=None):
        self.name = name
        self.scraps = scraps            # [scraps] in project.toml: station specs per plan scrap (scraps.py)
        self.survey = survey
        self.author = author            # (date, name)
        self.copyright = copyright      # (year, holder)
        self.qualify = qualify

    def attrs(self, K):
        a = ""
        if self.author:
            a += ' -author %s "%s"' % self.author
        if self.copyright:
            a += ' -copyright %s "%s"' % self.copyright
        r = 10 * K
        return a + f" -scale [0 0 {r:.2f} {r:.2f} 0.0 0.0 10 10 m]"

    def station(self, n):
        return f"{n}@{self.survey}" if self.qualify and self.survey else n


def _nearest(pos, p):
    return min(pos, key=lambda k: math.dist(pos[k], p))


# -- cross sections ----------------------------------------------------------------

def gather_section(centre, lines, used, stations, near=1.2, reach=6.0, avoid=()):
    """Indices of the sketch lines making up the cross section drawn around
    `centre`: lines within `near` of it or around it, then lines touching those,
    keeping only lines wholly within `reach` of the centre and clear of the
    survey stations (which are on the main drawing, not the section)."""
    C = Point(centre)
    stp = [Point(p) for p in stations]
    far = [Point(p) for p in avoid if math.dist(p, centre) <= reach + 1.0]     # the main drawing's shot ends

    def ok(pp):
        if any(math.dist(p, centre) > reach for p in pp):
            return False
        ls = LineString(pp)
        return all(ls.distance(q) > 0.3 for q in stp) and all(ls.distance(q) > 0.25 for q in far)

    cand = [i for i, (c, pp) in enumerate(lines) if i not in used and c in WALLS + ('BLUE', 'GREEN')
            and len(pp) > 1 and ok(pp)]
    picked = [i for i in cand if LineString(lines[i][1]).distance(C) < near or
              (len(lines[i][1]) > 3 and Polygon(lines[i][1]).buffer(0).contains(C))]
    grown = True
    while grown and picked:
        grown = False
        geo = unary_union([LineString(lines[i][1]) for i in picked])
        for i in cand:
            if i not in picked and LineString(lines[i][1]).distance(geo) < 0.15:
                picked.append(i)
                grown = True
    return picked


SECTION_CLOSE = (0.03, 0.06, 0.1, 0.17)   # a section's closing distances: shares of its size (with section_shape)
SECTION_MAIN = 0.7        # one stroke this share of the section's length (floor marks aside) is its outline ...
SECTION_OPEN = 0.7        # ... and if its ends are apart, by up to this share of its size, a floor closes it
FLOOR_MARK = 0.6          # m: a closed loop shorter than this is a mark on the floor (a pebble), not a wall
FLOOR_NEAR = 0.15         # m: floor marks this close to the closing floor make it debris


SECTION_MARK = 0.15       # an open stroke shorter than this share of the longest is a mark (a sand dash), not a wall
SECTION_MEET = (0.15, 0.1)  # m, share of size: two strokes' ends this close meet, closing the outline


def _floor_mark(pp):
    return len(pp) > 3 and math.dist(pp[0], pp[-1]) < 0.15 and LineString(pp).length < FLOOR_MARK


def _section_mark(pp, longest):
    """A pebble (a small closed loop) or a dash (a short open stroke): it
    shows what the floor is, it is not the outline (FairyChimneys PX5: the
    sand dashes under the floor taken for walls, the user)."""
    return _floor_mark(pp) or LineString(pp).length < SECTION_MARK * longest


def _smooth_open(pp):
    q = list(LineString(pp).simplify(0.025).coords)
    if len(q) >= 3:
        q = list(LineString(chaikin(q, 1)).simplify(0.015).coords)
    q[0], q[-1] = pp[0], pp[-1]
    return q


def drawn_outline(strokes, centre):
    """A section drawn as open strokes: (outline polygon, [(points, subtype)],
    strokes taken: the outline's and the marks), or None if it is not drawn so (then the strokes are closed up
    as before). Short strokes (pebbles, sand dashes) are marks, never the
    outline. The longest stroke and another meeting it at both ends make
    the outline, each line with its colour's subtype (brown: the floor,
    sand, or debris with pebbles on it; FairyChimneys PX5); one stroke open
    at the bottom is closed by a floor straight across its ends (TridentLeft
    PX1, PX10). Its station must be inside (Style.md, cross sections)."""
    strokes = [(c, list(s)) for c, s in strokes if len(s) > 1]
    if not strokes:
        return None
    longest = max(LineString(s).length for _, s in strokes)
    marks = [(c, s) for c, s in strokes if _section_mark(s, longest)]
    rest = [(c, s) for c, s in strokes if not _section_mark(s, longest)]
    if not rest:
        return None
    mc, main = max(rest, key=lambda cs: LineString(cs[1]).length)
    a, b = main[0], main[-1]
    x0, y0, x1, y1 = LineString(main).bounds
    size = math.hypot(x1 - x0, y1 - y0)
    if math.dist(a, b) < 0.05:
        return None                                    # closed already: as before
    meet = max(SECTION_MEET[0], SECTION_MEET[1] * size)

    def subtype(colour, line):
        if colour != 'BROWN':
            return None
        near = [s for _, s in marks if line.distance(LineString(s).centroid) < FLOOR_NEAR]
        pebbles = [s for s in near if _floor_mark(s)]
        return 'debris' if len(pebbles) >= 2 and len(pebbles) >= len(near) / 2 else 'sand'

    def floor_marks(line):
        near = [(c, s) for c, s in marks if line.distance(LineString(s).centroid) < FLOOR_NEAR]
        pebbles = [s for c, s in near if _floor_mark(s)]
        dashes = [s for c, s in near if c == 'BROWN' and not _floor_mark(s)]
        if len(pebbles) >= 2 and len(pebbles) >= len(dashes):
            return 'debris'
        return 'sand' if len(dashes) >= 2 else None

    out, used = None, [main]
    partners = []
    for c, s in rest:
        if s is main:
            continue
        if math.dist(s[0], b) < meet and math.dist(s[-1], a) < meet:
            partners.append((math.dist(s[0], b) + math.dist(s[-1], a), c, s))
        elif math.dist(s[-1], b) < meet and math.dist(s[0], a) < meet:
            partners.append((math.dist(s[-1], b) + math.dist(s[0], a), c, s[::-1]))
    if partners:
        _, c, s = min(partners, key=lambda x: x[0])
        used += [q for _, q in rest if q is s or q == s[::-1]]
        s = [b] + list(s[1:-1]) + [a]
        lines = [(_smooth_open(main), subtype(mc, LineString(main))),
                 (_smooth_open(s), subtype(c, LineString(s)) or floor_marks(LineString(s)))]
        out = Polygon(list(main) + s[1:]).buffer(0)
    elif LineString(main).length >= SECTION_MAIN * sum(LineString(s).length for _, s in rest) \
            and math.dist(a, b) <= SECTION_OPEN * size:
        chord = LineString([b, a])
        lines = [(_smooth_open(main), subtype(mc, LineString(main))), ([b, a], floor_marks(chord))]
        out = Polygon(list(main) + [a]).buffer(0)
    if out is None:
        return None
    if out.geom_type != 'Polygon':
        out = max(getattr(out, 'geoms', []), key=lambda p: p.area, default=Polygon())
    if out.is_empty or (centre is not None and not out.buffer(0.1).contains(Point(centre))):
        return None
    return out, lines, [s for _, s in marks] + used


def section_outline(strokes, centre=None):
    """One closed outline for a cross section, from its wall strokes.

    The strokes are thickened just enough to close the outline (up to
    0.6 m, so a gap left where the passage carries on is bridged), the
    inside filled, and the shape shrunk back by the same amount. That
    puts the outline on the strokes, merges strokes drawn twice into one
    line, and drops short flicks sticking out of it. Returns a smoothed
    polygon, or None."""
    from shapely import concave_hull
    from shapely.geometry import MultiPoint
    strokes = [s for s in strokes if len(s) > 1]
    if not strokes:
        return None
    U = unary_union([LineString(s) for s in strokes])
    out = None
    steps = (0.1, 0.2, 0.35, 0.6)
    if SETTINGS['section_shape']:           # closing distances scale with the section's size
        b = U.bounds
        diag = math.hypot(b[2] - b[0], b[3] - b[1])
        steps = tuple(min(d, f * diag) for d, f in zip(steps, SECTION_CLOSE))
    for d in steps:
        g = U.buffer(d, join_style=1)
        big = max(_polygons(g, 0.0) or [Polygon()], key=lambda p: p.area)
        if big.is_empty:
            continue
        filled = Polygon(big.exterior)
        if filled.area - g.area > 0.2 * filled.area:      # it encloses a passage
            o = filled.buffer(-d, join_style=1)
            ps = _polygons(o, 0.01)
            if ps:
                cand = max(ps, key=lambda p: p.area)
                if centre is not None and not cand.buffer(0.1).contains(Point(centre)):
                    continue                # a pocket, not the section: its station is outside
                out = cand
                break
    if out is None:     # never closes: wrap the strokes
        pts = MultiPoint([p for s in strokes for p in s])
        out = concave_hull(pts, ratio=0.3)
        if out.geom_type != 'Polygon' or out.area < 0.01:
            return None
    ring = list(out.simplify(0.025).exterior.coords)
    if len(ring) >= 4:
        ring = chaikin(ring, 1)
    p = Polygon(ring).simplify(0.015)
    return p if p.is_valid and not p.is_empty else out


def section_th2(name, attrs, lines, centre, K, comment):
    """A cross section scrap. lines: [(colour, pts)] gathered for it.
    Returns (th2 lines, width, height) or None if it has no walls."""
    # rocks in the section (closed brown loops on its floor) are drawn as rocks, not taken
    # for its outline (Style.md, rocks: the user, rocks in cross sections drawn)
    rocks = []
    if SETTINGS['drawn_rocks']:
        rocks = [pp for c, pp in lines if c == 'BROWN' and len(pp) > 3 and math.dist(pp[0], pp[-1]) < 0.15
                 and Polygon(pp).buffer(0).area > 0.005]
        lines = [(c, pp) for c, pp in lines if not any(pp is r for r in rocks)]
    wl = [pp for c, pp in lines if c in WALLS and len(pp) > 1]
    if not wl:
        return None
    drawn = drawn_outline([(c, pp) for c, pp in lines if c in WALLS] + [('BROWN', r) for r in rocks], centre) \
        if SETTINGS['section_shape'] else None
    if drawn:
        poly, outline, taken = drawn
        # the outline's strokes, and marks (pebbles, sand dashes) showing the floor's subtype; nor
        # are small rocks on it drawn (Style.md, rocks along a wall line)
        wl = [pp for pp in wl if not any(pp is m or pp == m for m in taken)]
        edge = LineString(list(poly.exterior.coords))
        rocks = [pp for pp in rocks if edge.distance(Polygon(pp).buffer(0).centroid) >= FLOOR_NEAR
                 or math.sqrt(Polygon(pp).buffer(0).convex_hull.area) >= 0.3]
    else:
        poly = section_outline(wl, centre if SETTINGS['section_shape'] else None)
    if poly is None:
        return None
    if SETTINGS['sections_in_place']:     # where it was sketched, by its section mark
        xpx = lambda p: (K * p[0], K * p[1])
    else:
        xpx = lambda p: (K * (p[0] - centre[0]) + 1000, K * (p[1] - centre[1]) + 1000)
    o = [f"scrap {name} -projection none{attrs}", "", comment, ""]
    if drawn:
        # the strokes as drawn, meeting end to end (a floor straight across an open one)
        for pp, sub in outline:
            body = bezier_lines(pp, xpx) if len(pp) > 2 else ["  %.2f %.2f" % xpx(q) for q in pp]
            o += [f"line wall{' -subtype ' + sub if sub else ''}"] + body + ["endline", ""]
    else:
        o += ["line wall -close on"] + bezier_closed(list(poly.exterior.coords), xpx) + ["endline", ""]
    # marks inside: boulders, and ledges or other lines as borders
    inner = []
    edge = poly.exterior
    for pp in wl:
        ls = LineString(pp)
        n = max(2, int(ls.length / 0.05))
        smp = [ls.interpolate(i / (n - 1), normalized=True) for i in range(n)]
        inside = sum(1 for q in smp if poly.contains(q) and edge.distance(q) > 0.12)
        if inside >= 0.7 * len(smp):
            inner.append(pp)
    rest, boulders, arrows = split_symbols(inner)
    o += symbols_th2([b for b in boulders if poly.contains(b.centroid)], [], xpx)
    for pp in rocks:                      # straight sides; details.boulders shapes them and adds the edges
        g = Polygon(pp).buffer(0)
        if g.geom_type == 'Polygon' and poly.buffer(0.3).contains(g.centroid):
            ring = list(g.simplify(0.02).exterior.coords)
            o += ["line rock-border -close on"] + ["  %.2f %.2f" % xpx(q) for q in ring] + ["endline", ""]
    for pp in clean(rest, min_len=0.3):
        o += ["line border -clip off"] + bezier_lines(pp, xpx) + ["endline", ""]
    o += water_th2(lines, poly, xpx, name, flow=False)
    o += ["endscrap", ""]
    b = poly.bounds
    return o, b[2] - b[0], b[3] - b[1], poly


SECTION_SPLAY_OUT = 0.5    # m: a section's splay end further outside its outline than this is reported


def section_scraps(sketch, opt, K, view='P'):
    """Cross section scraps for every connect line in the sketch, one scrap
    each, named survey + PX (plan) or EX (elevation) + station (Style.md:
    FairyChimneysPX5). A section's strokes are those around its own copy
    of the station and clear of the main drawing's shots (a stroke near
    one of them is the plan's, not the section's); its station and splay ends must be inside its outline
    (the leg and splay rule), and where they are not it is reported.
    Returns (th2 lines, [(station, scrap name, centre, width, height)], used line indices)."""
    pos = sketch.positions()
    used = set()
    o, made = [], []
    survey = opt.survey or opt.name.rstrip('S')
    for n, spos, centre in sketch.sections():
        ends = [b if math.dist(a, centre) < 0.01 else a for a, b in sketch.shots
                if math.dist(a, centre) < 0.01 or math.dist(b, centre) < 0.01]
        reach = 8.0
        main = [e for a, b in sketch.shots if math.dist(a, centre) >= 0.01 and math.dist(b, centre) >= 0.01
                for e in (a, b)]
        idx = gather_section(centre, sketch.lines, used, list(pos.values()), reach=reach, avoid=main)
        used |= set(idx)
        mine = [sketch.lines[i] for i in idx]
        name = (f"{survey}{view}X{n}" if SETTINGS['section_names'] else f"{opt.name}_xs_{n}").replace('.', '_')
        r = section_th2(name, opt.attrs(K), mine, centre, K, f"# Cross-section at station {n}.")
        if r is None:
            print(f"  cross section {name}: no walls drawn round station {n}", file=sys.stderr)
            continue
        o += r[0]
        W, H = r[1], r[2]
        poly = r[3]
        if poly is not None:
            if not poly.buffer(0.1).contains(Point(centre)):
                print(f"  cross section {name}: station {n} outside its outline: check", file=sys.stderr)
            far = [e for e in ends if poly.distance(Point(e)) > SECTION_SPLAY_OUT]
            if far:
                print(f"  cross section {name}: {len(far)} of {len(ends)} splay ends more than "
                      f"{SECTION_SPLAY_OUT} m outside: check", file=sys.stderr)
        made.append((n, name, centre, W, H))
    return o, made, used


class PlanGeometry:
    """Passage direction and width at a station, from legs and splays."""

    def __init__(self, pos, shots):
        self.pos = pos
        at = {(round(p[0], 2), round(p[1], 2)): n for n, p in pos.items()}
        self.legs, self.splays = [], {}
        for a, b in shots:
            na, nb = at.get((round(a[0], 2), round(a[1], 2))), at.get((round(b[0], 2), round(b[1], 2)))
            if na and nb and na != nb:
                self.legs.append((na, nb))
            elif na and not nb:
                self.splays.setdefault(na, []).append((b[0] - a[0], b[1] - a[1]))
            elif nb and not na:
                self.splays.setdefault(nb, []).append((a[0] - b[0], a[1] - b[1]))

    def direction(self, n):
        p = self.pos[n]
        vs = []
        for a, b in self.legs:
            if n in (a, b):
                q = self.pos[b if a == n else a]
                d = math.dist(p, q)
                if d > 0.3:
                    vs.append(((q[0] - p[0]) / d, (q[1] - p[1]) / d))
        if not vs:
            return (1.0, 0.0)
        if len(vs) == 1:
            return vs[0]
        i, j = min(((i, j) for i in range(len(vs)) for j in range(i + 1, len(vs))),
                   key=lambda ij: vs[ij[0]][0] * vs[ij[1]][0] + vs[ij[0]][1] * vs[ij[1]][1])
        v = (vs[i][0] - vs[j][0], vs[i][1] - vs[j][1])
        m = math.hypot(*v) or 1
        return (v[0] / m, v[1] / m)

    def half_width(self, n, perp):
        w = [0.5] + [abs(dx * perp[0] + dy * perp[1]) for dx, dy in self.splays.get(n, [])]
        return min(max(w), 4.0)

    def obstacles(self):
        return unary_union([LineString([self.pos[a], self.pos[b]]).buffer(2.0)
                            for a, b in self.legs if math.dist(self.pos[a], self.pos[b]) > 0.01])


SECTION_MARGIN = 0.5    # m: a section line goes this far past the passage, so its arrows are clear of it


def section_line(geo, n, px):
    """`line section -direction both` right across the passage at station n
    (Style.md, Cross sections). Therion draws the arrows on the line's left,
    so the line runs with the view direction, along the survey from n
    towards the next station, on its left. Returns (rows, perp, half width)."""
    P = geo.pos[n]
    u = geo.direction(n)
    if not SETTINGS['section_arrows']:          # upstream: no arrows, either way round
        perp = (-u[1], u[0])
        hw = geo.half_width(n, perp)
        a = (P[0] - perp[0] * hw, P[1] - perp[1] * hw)
        b = (P[0] + perp[0] * hw, P[1] + perp[1] * hw)
        return ["line section", "  %.2f %.2f" % px(a), "  %.2f %.2f" % px(b), "endline", ""], perp, hw
    ahead = [b for a, b in geo.legs if a == n and math.dist(P, geo.pos[b]) > 0.3]
    behind = [a for a, b in geo.legs if b == n and math.dist(P, geo.pos[a]) > 0.3]
    if ahead:
        v = (geo.pos[ahead[0]][0] - P[0], geo.pos[ahead[0]][1] - P[1])
    elif behind:
        v = (P[0] - geo.pos[behind[0]][0], P[1] - geo.pos[behind[0]][1])
    else:
        v = u
    if u[0] * v[0] + u[1] * v[1] < 0:
        u = (-u[0], -u[1])
    perp = (-u[1], u[0])                 # u's left
    hw = geo.half_width(n, perp)
    h = hw + SECTION_MARGIN
    a = (P[0] + perp[0] * h, P[1] + perp[1] * h)
    b = (P[0] - perp[0] * h, P[1] - perp[1] * h)    # from u's left to its right: u on the line's left
    return ["line section -direction both", "  %.2f %.2f" % px(a), "  %.2f %.2f" % px(b), "endline", ""], perp, hw


def place_sections(geo, made, px, placed):
    """Put cross sections drawn in a side view beside the passage on the plan,
    clear of other passages and of each other."""
    obst = geo.obstacles()
    o = []
    for n, name, _c, W, H in made:
        if n not in geo.pos:
            continue
        lines, perp, hw = section_line(geo, n, px)
        o += lines
        P = geo.pos[n]
        r = max(W, H) / 2
        spot = None
        for extra in (1.0, 2.5, 4.5, 7.0, 10.0, 14.0):
            for s in (1, -1):
                d = hw + r + extra
                c = (P[0] + perp[0] * s * d, P[1] + perp[1] * s * d)
                bb = box(c[0] - W / 2, c[1] - H / 2, c[0] + W / 2, c[1] + H / 2).buffer(0.4)
                if not bb.intersects(obst) and not any(bb.intersects(q) for q in placed):
                    spot = (c, extra)
                    break
            if spot:
                break
        if not spot:
            spot = ((P[0] + perp[0] * (hw + r + 1), P[1] + perp[1] * (hw + r + 1)), None)
        c, extra = spot
        placed.append(box(c[0] - W / 2, c[1] - H / 2, c[0] + W / 2, c[1] + H / 2))
        o += ["point %.2f %.2f section -scrap %s" % (*px(c), name), ""]
        if extra is None or extra > 2.5:
            # far from its cut: label both ends with the station so they can be matched
            b = (P[0] + perp[0] * (hw + 0.6), P[1] + perp[1] * (hw + 0.6))
            t = n.split('@')[0]
            o += ['point %.2f %.2f label -text "%s" -scale xs' % (*px(b), t), "",
                  'point %.2f %.2f label -text "%s" -scale xs' % (*px((c[0], c[1] + H / 2 + 0.8)), t), ""]
    return o


# -- whole scraps --------------------------------------------------------------------

def _split(sketch, layout, survey, tol):
    """Station groups that fit Therion's layout with one shift each.

    Not used for drawing (plan stage 5d): Therion morphs each scrap onto
    its stations, and stations move as other surveys join, so a drawing is
    never split or flipped to fit where Therion puts the stations today.
    The conversion passes no layout; `check` reports the disagreement."""
    pos = sketch.positions()
    if layout is None:
        return sketch, [list(pos)], False
    sk, offs, flipped = register.fit(sketch, layout, survey)
    gs = register.groups(offs, tol)
    # stations Therion doesn't place once go with the nearest grouped station
    pos = sk.positions()
    member = {n: i for i, g in enumerate(gs) for n in g}
    for n in pos:
        if n not in member and member:
            m = _nearest({k: pos[k] for k in member}, pos[n])
            gs[member[m]].append(n)
            member[n] = member[m]
    return sk, gs or [list(pos)], flipped


def plan(sketch, opt, out_path, layout=None, floor=None, tol=3.0):
    """th2 text for a plan sketch."""
    K = sketch.scale
    sketch, groups, flipped = _split(sketch, layout, opt.survey, tol)
    pos = sketch.positions()
    px = lambda p: (K * p[0], K * p[1])
    xs_text, made, used = section_scraps(sketch, opt, K, 'P')
    lines = [l for i, l in enumerate(sketch.lines) if i not in used]
    geo = PlanGeometry(pos, sketch.shots)
    from . import scale                   # the legs nearby set how closely lines follow the sketch
    scale.use([(pos[a], pos[b]) for a, b in geo.legs])
    if opt.scraps and SETTINGS['hand_scraps']:    # chosen by hand: strokes go with their nearest leg's scrap
        from . import scraps as by_hand
        names = sorted(pos, key=register.natural)
        groups = by_hand.complete(by_hand.parse(opt.scraps, names), names, geo.legs)
        pieces = by_hand.assign(lines, groups, pos, geo.legs)
    else:
        member = {n: i for i, g in enumerate(groups) for n in g}
        near = lambda p: member.get(_nearest(pos, p), 0) if pos else 0
        pieces = [(near(pp[len(pp) // 2]), c, pp) for c, pp in lines if pp]

    body, scraps, polys_all = [], [], []
    placed = []
    for gi, g in enumerate(groups):
        mine = [(c, pp) for k, c, pp in pieces if k == gi]
        notes = []
        if SETTINGS['notation']:          # steps and overhangs, by their notation
            from . import notation
            notes, used_n = notation.find(mine)
            mine = [l for k, l in enumerate(mine) if k not in used_n]
        mine, presumed = presumed_strokes(mine)
        gours = []
        if SETTINGS['gours']:             # solid green lines: gours
            from .marks import is_gour
            gours = [pp for c, pp in mine if c == 'GREEN' and len(pp) > 1 and is_gour(pp)]
            mine = [(c, pp) for c, pp in mine if not (c == 'GREEN' and any(pp is g for g in gours))]
        if SETTINGS['green_loops']:       # single green loops are boulders/debris, drawn like brown
            from .marks import green_loops
            loops = set(green_loops([(k, pp) for k, (c, pp) in enumerate(mine) if c == 'GREEN']))
            mine = [('BROWN', pp) if k in loops else (c, pp) for k, (c, pp) in enumerate(mine)]
        walls, boulders, arrows = wall_strokes(mine)
        walls = clean(walls)
        if SETTINGS['outer_walls']:
            walls = corners(walls)
        gset = set(g)
        legs = [[pos[a], pos[b]] for a, b in geo.legs if a in gset and b in gset]
        polys = plan_fill(walls, legs, [pp for c, pp in mine if c == 'BLUE'])
        if SETTINGS['interior_borders']:      # cut the fill back to the outer walls it bridged
            ends = [e for _, _, e in sketch.splays()]
            polys = [cut_back(p, walls, legs, ends) for p in polys]
        if SETTINGS['rock_faces']:            # and drop the rock it took in (bends, tongues, hooks)
            polys = [drop_rock_faces(p, walls, legs, [pos[n] for n in g]) for p in polys]
        for poly in polys:
            name = f"{opt.name}P{len(scraps) + 1}"
            inside = [n for n in g if poly.buffer(1.0).contains(Point(pos[n]))]
            if not inside:
                inside = [_nearest({n: pos[n] for n in g}, poly.representative_point().coords[0])]
            o = [f"scrap {name} -projection plan{opt.attrs(K)}", ""]
            o += presumed_marks(presumed, poly, px)
            o += walls_th2(walls, poly, px, legs, [e for _, _, e in sketch.splays()])
            o += symbols_th2([b for b in boulders if poly.contains(b.centroid)],
                             [a for a in arrows if poly.contains(Point(a[0]))], px)
            o += water_th2(mine, poly, px, name, [(pos[a], pos[b]) for a, b in geo.legs])
            if SETTINGS['brown'] == 'floor' or SETTINGS['interior_borders']:
                from . import marks
                inner = poly.buffer(-0.15)
                barriers = [LineString(w) for w in walls if len(w) > 1
                            and inner.contains(LineString(w).interpolate(0.5, normalized=True))]
                barriers += [LineString(p) for k, p, _ in notes]
                o += marks.th2(mine if SETTINGS['brown'] == 'floor' else
                               [(c, pp) for c, pp in mine if c != 'BROWN'],
                               poly, px, name, SETTINGS['wall_colours'], SETTINGS['boulder_min'], barriers)
            if notes:
                from . import notation
                climbs = [(_lerp_pt(pos[a], pos[b], fr), d) for a, b, fr, d in (floor or {}).get('climbs', [])
                          if a in pos and b in pos]
                o += notation.th2(notes, poly, px, climbs, SETTINGS['pitch_min'])
            for pp in gours:
                from .marks import smooth_rows
                if poly.buffer(0.3).intersects(LineString(pp)):
                    from .marks import gour_rows
                    o += ["line rimstone-dam"] + gour_rows(pp, px) + ["endline", ""]
            if floor and SETTINGS['elevation_data']:
                from .floor import th2 as floor_th2
                o += floor_th2(floor, {n: pos[n] for n in inside}, poly, px, placed,
                               [LineString(p) for k, p, _ in notes if k == 'step'])
            for n, sname, centre, W, H in made:
                if n in inside:
                    o += section_line(geo, n, px)[0]
                    o += ["point %.2f %.2f section -scrap %s" % (*px(centre), sname), ""]
            for n in inside:
                o += ["point %.2f %.2f station -name %s" % (*px(pos[n]), opt.station(n)), ""]
            o += ["endscrap", ""]
            body += o
            scraps.append(name)
            polys_all.append(poly)
    anchor = next(iter(pos)) if pos else ''
    head = header(sketch.path if sketch.path.lower().endswith('.xvi') and not flipped else None,
                  out_path, anchor, px(pos[anchor]) if anchor else (0, 0), polys_all, px)
    note = ["# Converted from %s by tools/sketch2therion (plan)." % os.path.basename(sketch.path or 'a sketch'),
            "# Not hand-finished: check flow arrows and anything the conversion missed.", ""]
    return "\n".join(head + note + body + xs_text), scraps, [m[1] for m in made]


def extended(sketch, opt, out_path, layout=None, plan_layout=None, tol=1.5, below=3.0, above=5.0):
    """th2 text for an extended-elevation sketch, plus a plan scrap placing
    its cross sections (if Therion's plan layout is given)."""
    if SETTINGS['elevation_wall_colours']:
        # in an elevation the floor is often drawn in another colour (brown) than the roof
        keep = SETTINGS['wall_colours']
        SETTINGS['wall_colours'] = SETTINGS['elevation_wall_colours']
        try:
            return _extended(sketch, opt, out_path, layout, plan_layout, tol, below, above)
        finally:
            SETTINGS['wall_colours'] = keep
    return _extended(sketch, opt, out_path, layout, plan_layout, tol, below, above)


def _lumpy(pp, simplify=0.15, ratio=1.3, closed=0.1):
    """A stroke drawn as boulders (a closed loop, or one much longer than its
    outline smoothed at `simplify` m) rather than a smooth drape."""
    L = LineString(pp)
    if Point(pp[0]).distance(Point(pp[-1])) < closed:
        return True
    return L.length > ratio * max(L.simplify(simplify).length, 1e-6)


def _plen(pp):
    return sum(math.dist(a, b) for a, b in zip(pp, pp[1:]))


def vertical_splays(sketch, survey):
    """{station: [(x, y) of its splay ends straight up and down]} in the
    sketch's metres, from the sketch's own splays (roofs.Splays)."""
    from .roofs import Splays
    sp = Splays.from_sketch(sketch, survey, True)
    pos = sketch.positions()
    out = {}
    for n, (x, y) in pos.items():
        key = n if '@' in n else f'{n}@{survey}'
        ends = ([(x, y + sp.up[key])] if key in sp.up else []) + ([(x, y - sp.down[key])] if key in sp.down else [])
        if ends:
            out[n] = ends
    return out


SPLAYED = 2         # vertical splay ends on a stroke not in a wall colour that make it a wall


def splayed_walls(lines, marks, near=0.3):
    """Strokes drawn grey (steps, mostly) that SPLAYED or more splay ends
    straight up or down end on: the floor or ceiling the splays were
    measured to, a wall (Connection 22 to 26: the roof of 18 to 23 is the
    floor of 24 to 27, drawn grey). [(colour, points)]."""
    ends = [Point(e) for es in marks.values() for e in es]
    out = []
    for c, pp in lines:
        if c == 'GRAY' and len(pp) > 1:
            g = LineString(pp)
            if sum(1 for e in ends if g.distance(e) < near) >= SPLAYED:
                c = 'BLACK'
        out.append((c, pp))
    return out


def drawn_on(pieces, lines, sizes=None, meet=0.3, keep=()):
    """Scraps by hand, in an elevation: a whole stroke drawn on from the end
    of another of the same colour, in a scrap with more stations (`sizes`:
    stations per scrap), goes into that scrap: the same wall, and a small
    scrap is a passage split off a main one. Not if one of its ends also
    meets a stroke in its own scrap. Decided on the scraps as assigned.
    Trident: the roof over 38 to 39, drawn on up past 37 to the peak."""
    key = lambda pp: frozenset([tuple(pp[0]), tuple(pp[-1])])
    whole_keys = {key(pp) for _, pp in lines if len(pp) > 1}
    is_whole = lambda pp: len(pp) > 1 and key(pp) in whole_keys     # not cut by assign
    out = [list(p) for p in pieces]
    ends = [(k, c, pp) for k, c, pp in pieces if is_whole(pp)]
    copies = {}
    for k, c, pp in pieces:
        copies[key(pp)] = copies.get(key(pp), 0) + 1
    for rec in out:
        k, c, pp = rec
        if not is_whole(pp) or copies[key(pp)] > 1:
            continue                                 # a wall shared by two scraps (scraps.shared_with) stays in both
        if (tuple(pp[0]), tuple(pp[-1])) in keep:
            continue                                 # a branch's wall, by its direction (scraps.by_direction)
        mine, theirs = False, set()
        for e in (pp[0], pp[-1]):
            for k2, c2, q in ends:
                if q is pp or c2 != c:
                    continue
                if min(math.dist(e, q[0]), math.dist(e, q[-1])) < meet:
                    if k2 == k:
                        mine = True
                    elif sizes is None or sizes[k2] > sizes[k]:
                        theirs.add(k2)
        if not mine and len(theirs) == 1:
            rec[0] = theirs.pop()
    return [tuple(r) for r in out]


JOIN_REACH = 3.0    # m: wall ends this near a join (a station of a leg between scraps) are at the join
TRIM_ALL = False    # (testing: trim at every join, as before)
IN_LINE = 0.3       # m: a wall end further out than the opposite wall's end by more than this is cut back


ELEVATION_SEAL = 0.5  # m: in an elevation, a gap this wide at a passage end closes off the rock beside it
                      # (Trident 4: the wall over 3 to 4 ends 0.46 m from the floor)
CORNER_TAIL = 1.5   # m: walls crossing this near an end of each meet at the crossing, the ends past it go


def corners(walls):
    """Two walls crossing near an end of each (a corner drawn with both
    strokes run on past it): each is cut at the crossing and the short ends
    beyond it go, so the outline turns the corner and doesn't cross itself
    (Trident 17, hand edit: the roof and the mud floor of the pocket)."""
    out = [list(w) for w in walls]
    for i in range(len(out)):
        for k in range(i + 1, len(out)):
            a, b = out[i], out[k]
            if len(a) < 2 or len(b) < 2:
                continue
            la, lb = LineString(a), LineString(b)
            x = la.intersection(lb)
            if x.is_empty or x.geom_type != 'Point':
                continue
            ta, tb = la.project(x), lb.project(x)
            ea = 0 if ta < CORNER_TAIL else (-1 if la.length - ta < CORNER_TAIL else None)
            eb = 0 if tb < CORNER_TAIL else (-1 if lb.length - tb < CORNER_TAIL else None)
            if ea is None or eb is None or min(ta, la.length - ta) < 0.05 or min(tb, lb.length - tb) < 0.05:
                continue
            ca = ta if ea == 0 else la.length - ta
            cb = tb if eb == 0 else lb.length - tb
            if la.length - ca < 2 * ca or lb.length - cb < 2 * cb:
                continue                              # the end past it not short: not a corner run on past
            c = (x.x, x.y)
            out[i] = _cut_at(a, ta, ea, c)
            out[k] = _cut_at(b, tb, eb, c)
    return out


def _cut_at(w, t, end, c):
    """w with the part from its `end` (0 or -1) to distance t along it
    replaced by the point c."""
    acc, keep = 0.0, []
    if end == -1:
        keep = [w[0]]
        for p, q in zip(w, w[1:]):
            acc += math.dist(p, q)
            if acc >= t:
                break
            keep.append(q)
        return keep + [c]
    rev = _cut_at(w[::-1], LineString(w).length - t, -1, c)
    return rev[::-1]


LINE_REACH = 1.5    # m: wall ends this near the line through a junction are taken to it
LINE_HEIGHT = 2.0   # m: only walls within this above or below the junction (the passage there)


def walls_to_line(walls, j, side):
    """The walls of a passage starting at a junction j, on its `side` (+1:
    larger x), end on the vertical line through j (Style.md, Scraps; Trident
    10 to 13): a wall running past the line is cut on it, a free end short
    of it by up to LINE_REACH is drawn on to it."""
    x = j[0]
    out = []
    for w in walls:
        if len(w) < 2:
            out.append(w)
            continue
        w = list(w)
        # cut where it crosses to the other side near the junction, keeping this side
        cross = [p[1] + (q[1] - p[1]) * (x - p[0]) / (q[0] - p[0]) for p, q in zip(w, w[1:])
                 if q[0] != p[0] and min(p[0], q[0]) <= x <= max(p[0], q[0])]
        if cross and all(abs(y - j[1]) > LINE_HEIGHT for y in cross):
            out.append(w)                            # it passes well above or below the junction
            continue
        if any((p[0] - x) * side < 0 for p in w) and any((p[0] - x) * side > 0 for p in w):
            keep, run = [], []
            for p, q in zip(w, w[1:]):
                if (p[0] - x) * side >= 0:
                    run.append(p)
                if ((p[0] - x) * side >= 0) != ((q[0] - x) * side >= 0) and q[0] != p[0]:
                    t = (x - p[0]) / (q[0] - p[0])
                    c = (x, p[1] + t * (q[1] - p[1]))
                    run.append(c)
                    if (q[0] - x) * side < 0:
                        keep.append(run)
                        run = []
                    else:
                        run = [c]
            if (w[-1][0] - x) * side >= 0:
                run.append(w[-1])
            keep.append(run)
            out += [r for r in keep if len(r) > 1 and LineString(r).length > 0.05]
            continue
        if all((p[0] - x) * side < 0 for p in w):
            out.append(w)                            # wholly on the other side: not this passage's to move
            continue
        for k in (0, -1):                            # a free end just short of the line: drawn on to it
            e = w[k]
            gap = (e[0] - x) * side
            if 0 < gap <= LINE_REACH and abs(e[1] - j[1]) < LINE_HEIGHT:
                inward = w[1] if k == 0 else w[-2]
                if (inward[0] - x) * side > gap:     # the wall runs away from the line here
                    if k == 0:
                        w.insert(0, (x, e[1]))
                    else:
                        w.append((x, e[1]))
        out.append(w)
    return out


def trim_at_joins(walls, joins, stations, others=()):
    """Elevation walls where a scrap meets the next end in line: a wall end
    near the join that runs further out (away from the scrap's stations)
    than the nearest end of the wall opposite it (floor and ceiling) is
    cut back to it (Style.md, Scraps; TritonSouth, log row 137)."""
    if not joins or not stations:
        return walls
    cx = sum(p[0] for p in stations) / len(stations)
    pts = [(i, k) for i, w in enumerate(walls) if len(w) > 1 for k in (0, -1)]

    def free(i, k):
        e = walls[i][k]
        return not any(j != i and LineString(w).distance(Point(e)) < 0.3 for j, w in enumerate(walls) if len(w) > 1)
    near_join = lambda p: min(abs(p[0] - j[0]) for j in joins) < JOIN_REACH      # along the passage: roofs are high
    ends = [(i, k) for i, k in pts if free(i, k) and near_join(walls[i][k])]
    # the opposite wall may be this scrap's or the next one's (the short bit of ceiling closest)
    theirs = [w[k] for w in others if len(w) > 1 for k in (0, -1) if near_join(w[k])]
    out = [list(w) for w in walls]
    for i, k in ends:
        e = walls[i][k]
        side = 1 if e[0] > cx else -1                # the join's side of the scrap
        # only where the scrap ends at the join: a branch joining part way along leaves the
        # passage carrying on past it (TridentCentre: 4 joins 3 to 7 from the side, the user)
        j = min(joins, key=lambda q: abs(q[0] - e[0]))
        if not TRIM_ALL and any((s[0] - j[0]) * side > IN_LINE for s in stations):
            continue
        opp = [walls[j][m] for j, m in ends if j != i] + theirs
        opp = [q for q in opp if abs(q[1] - e[1]) > 0.5 and abs(q[0] - e[0]) < JOIN_REACH]
        if not opp:
            continue
        f = min(opp, key=lambda q: abs(q[0] - e[0]))
        if (e[0] - f[0]) * side <= IN_LINE:
            continue
        x = f[0]
        w = out[i] if k == 0 else out[i][::-1]       # from the end being cut
        keep = [p for p in w if (p[0] - x) * side <= 0]
        if len(keep) < 2:
            continue
        # where the wall crosses x, then the rest
        first = next(n for n, p in enumerate(w) if (p[0] - x) * side <= 0)
        if first > 0:
            a, b = w[first - 1], w[first]
            t = (x - a[0]) / (b[0] - a[0]) if b[0] != a[0] else 0.0
            keep = [(x, a[1] + t * (b[1] - a[1]))] + w[first:]
        else:
            keep = w[first:]
        out[i] = keep if k == 0 else keep[::-1]
    return out


DASH_JOIN = False    # dashed lines joined across gaps (notation.join_dashed): worse on the ten, off
ELEVATION_DASH_GAP = 1.2   # m: dashes of one line in an elevation (a big chamber's roof drawn sparsely:
                           # FairyChimneys 34 to 39, Connection; plans keep notation.DASH_GAP)


GREEN_WALL = (0.8, 0.3)   # m: a green stroke this long or more, meeting a wall's end this near, is wall


def green_walls(lines, walls):
    """Open green strokes (flowstone) carrying a wall on from its end: the
    wall there, drawn in green (the user: Trident 31 to the sand, FairyChimneys
    34). Its subtype comes from the flowstone marks."""
    ends = [Point(w[k]) for w in walls if len(w) > 1 for k in (0, -1)]
    out = []
    for c, pp in lines:
        if c != 'GREEN' or len(pp) < 2 or LineString(pp).length < GREEN_WALL[0] or math.dist(pp[0], pp[-1]) < 0.15:
            continue
        if any(Point(e).distance(q) < GREEN_WALL[1] for e in (pp[0], pp[-1]) for q in ends):
            out.append(list(pp))
    return out


def presumed_strokes(lines, dash_gap=None):
    """(lines with each black dashed line as one stroke, [those strokes]) with
    dashed_presumed; the dashes themselves are gone."""
    if not SETTINGS['dashed_presumed']:
        return lines, []
    from . import notation
    found, used = notation.presumed(lines, dash_gap or notation.DASH_GAP,
                                    3 * dash_gap if dash_gap == ELEVATION_DASH_GAP and DASH_JOIN else None)
    return [l for k, l in enumerate(lines) if k not in used] + [('BLACK', pp) for pp in found], found


def presumed_marks(presumed, poly, px):
    """`# wall-subtype presumed: ...` for the dashed lines at this scrap's
    passage, for smooth.wall_subtypes to apply to the walls made from them."""
    out = ["# wall-subtype presumed: " + " ".join("%.1f %.1f" % px(p) for p in pp)
           for pp in presumed if LineString(pp).distance(poly) < 0.5]
    return out + ([""] if out else [])


def subtype_marks(lines, px, kinds={}):
    """Comment lines recording where walls are drawn in a colour that means
    a wall subtype (green: `flowstone`, or `blocks` if drawn lumpy; brown: `debris` where
    boulders lie along it, else `sand`: mud is drawn as sand, never clay), for
    smooth.wall_subtypes to apply once the walls are final:
    `# wall-subtype sand: x y x y ...` in drawing units."""
    out = []
    from .elevation import _closed, BOULDER_MAX
    rocks = [LineString(pp) for c, pp in lines if len(pp) > 3 and _closed(pp)
             and sum(math.dist(a, b) for a, b in zip(pp, pp[1:])) <= BOULDER_MAX]
    for c, pp in lines:
        if c not in ('BROWN', 'GREEN') or len(pp) < 2 or not is_outline(pp):
            continue
        L = LineString(pp)
        if id(pp) in kinds:
            kind = kinds[id(pp)]
        elif c == 'GREEN':                       # colour is a hint: shape decides
            kind = 'blocks' if _lumpy(pp) else 'flowstone'
        elif sum(1 for r in rocks if L.distance(r) < 0.3) >= max(2, L.length / 2.0):
            kind = 'debris'                      # boulders along it: a floor of debris
        else:
            kind = 'sand'                        # mud or sand: sand (user, 2026-10-11: no clay)
        out.append(f"# wall-subtype {kind}: " + " ".join("%.1f %.1f" % px(p) for p in pp))
    return out + ([""] if out else [])


def cut_glitches(lines, boxes):
    """Strokes with their points inside any box (x0, y0, x1, y1) removed,
    cut into the pieces either side."""
    if not boxes:
        return lines
    inside = lambda p: any(b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3] for b in boxes)
    out = []
    for c, pp in lines:
        if not any(inside(p) for p in pp):
            out.append((c, pp))
            continue
        run = []
        for p in pp:
            if inside(p):
                if len(run) > 1:
                    out.append((c, run))
                run = []
            else:
                run.append(p)
        if len(run) > 1:
            out.append((c, run))
    return out


def _extended(sketch, opt, out_path, layout=None, plan_layout=None, tol=1.5, below=3.0, above=5.0):
    K = sketch.scale
    if getattr(opt, 'glitches', None):        # slips of the pen ([glitches] in project.toml)
        sketch.lines = cut_glitches(sketch.lines, opt.glitches)
    sketch, groups, flipped = _split(sketch, layout, opt.survey, tol)
    pos = sketch.positions()
    px = lambda p: (K * p[0], K * p[1])
    xs_text, made, used = section_scraps(sketch, opt, K, 'E')
    lines = [l for i, l in enumerate(sketch.lines) if i not in used]
    # dashed lines found before the strokes are shared out between scraps (one crossing two
    # scraps would break into runs too short to count)
    lines, presumed_all = presumed_strokes(lines, ELEVATION_DASH_GAP)
    legs_all = [(a, b) for a, b, *_ in sketch.legs()]
    marks = None
    if opt.scraps and SETTINGS['hand_scraps']:    # chosen by hand ([scraps_extended]), as in plan
        from . import scraps as by_hand
        names = sorted(pos, key=register.natural)
        groups = by_hand.complete(by_hand.parse(opt.scraps, names), names, legs_all)
        placed = set()
        marks = vertical_splays(sketch, opt.survey) if SETTINGS['outer_walls'] else None
        if marks:                                # a grey line the splays end on is a floor or ceiling
            lines = splayed_walls(lines, marks)
        pieces = drawn_on(by_hand.assign(lines, groups, pos, legs_all, share=True, placed=placed, marks=marks),
                          lines, [len(g) for g in groups], keep=placed)
        colours = set(SETTINGS['wall_colours']) | {'BLACK'}
        pieces = by_hand.one_wall_each_side(pieces, groups, pos, colours)
        pieces = by_hand.carried_through(pieces, colours)
        pieces = by_hand.inner_walls_moved(pieces, groups, pos, colours, legs_all)
    else:
        member = {n: i for i, g in enumerate(groups) for n in g}
        near = lambda p: member.get(_nearest(pos, p), 0) if pos else 0
        pieces = [(near(pp[len(pp) // 2]), c, pp) for c, pp in lines if pp]

    body, scraps, polys_all = [], [], []
    for gi, g in enumerate(groups):
        if len(g) < 2:
            continue
        mine = [(c, pp) for k, c, pp in pieces if k == gi]
        presumed = presumed_all
        feats = None
        if SETTINGS['elevation_features']:       # pools, flow, curtains, blocks, rocks, rubble (elevation.py)
            from . import elevation as el
            feats = el.features(mine, [pos[n] for n in g])
            el.pillars_apart(feats, [(pos[a], pos[b]) for a, b in legs_all if a in pos and b in pos])
            mine = feats.lines
        walls, _b, _a = wall_strokes(mine)
        if feats:      # a green stroke carrying a wall on, end to end: the wall there, flowstone (Trident 31)
            walls += green_walls(mine, walls)
        walls = clean(walls)
        if SETTINGS['outer_walls']:
            walls = corners(walls)
        gset = set(g)
        if len(groups) > 1:                      # where this scrap meets the next, its walls end in line
            from .scraps import junction_joins
            at = [(j, o) for k, j, o in junction_joins(groups, legs_all) if k == gi and j in pos and o in pos]
            if at:                               # a passage from a junction: its walls start on a line up through it
                for j, o in at:
                    walls = walls_to_line(walls, pos[j], 1 if pos[o][0] > pos[j][0] else -1)
            else:
                joins = [pos[x] for a, b in legs_all for x in (a, b) if (a in gset) != (b in gset) and x in pos]
                theirs = clean(wall_strokes([(c, pp) for k, c, pp in pieces if k != gi and pp])[0])
                walls = trim_at_joins(walls, joins, [pos[n] for n in g if n in pos], theirs)
        if feats:
            walls += el.bowls(feats, walls)
        if not walls:
            continue
        if len(groups) > 1 and SETTINGS['outer_walls']:   # with the legs at a junction going with the passage beyond it
            from .scraps import leg_owner
            own = leg_owner(groups, legs_all)
            legs = [(pos[a], pos[b]) for a, b in legs_all if own.get((a, b)) == gi and a in pos and b in pos]
        else:
            legs = [(pos[a], pos[b]) for a, b in legs_all if a in gset and b in gset]
        extra = [pp for c, pp in mine if c == 'BLUE'] + \
            ([[(x0, y), (x1, y)] for x0, x1, y in feats.pools] if feats else [])
        others = [(c, pp) for k, c, pp in pieces if k != gi and pp]
        stops = clean(wall_strokes(others)[0]) if others else []
        # the fill reaches as high as the splays say the roof is (FairyChimneys 31 to 39: a chamber
        # 7 to 11 m high, its dashed roof drawn there)
        reach = above
        if marks:
            ups = [e[1] - pos[n][1] for n in g if n in marks and n in pos for e in marks[n] if e[1] > pos[n][1]]
            reach = max([above] + [u + 0.5 for u in ups])
        # and in a pitch as far sideways as the splays say the walls are (OIAS_V2 9 to 20: a shaft
        # 20 to 30 m across, its walls drawn far from the legs)
        side = max([above] + [abs(e[0] - p[0]) + 0.5 for n, p, e in sketch.splays() if n in gset
                              and math.degrees(math.atan2(abs(e[1] - p[1]), abs(e[0] - p[0]))) < 40]) \
            if SETTINGS['pitch_fill'] else 0.0
        polys = elevation_fill(walls, legs, extra, below, reach, stops, side)
        if SETTINGS['rock_faces'] and SETTINGS['outer_walls']:     # the rock its closing-up took in goes, as in plan
            polys = [drop_rock_faces(p, walls, legs, [pos[n] for n in g if n in pos], seal=ELEVATION_SEAL,
                                     margin=0.1) for p in polys]
        # the stations in (or by) each fill; a scrap left with fewer than two takes the group's
        # stations by no fill (TridentCentre 8 to 10: no walls sketched there, still the scrap's;
        # others far from the drawing left out, FairyChimneys 40, TritonSouth 1: the user)
        home = {n: next((k for k, p in enumerate(polys) if p.buffer(1.0).contains(Point(pos[n]))), None)
                for n in g if n in pos}
        for pi in range(len(polys)):
            if 0 < sum(1 for h in home.values() if h == pi) < 2:
                for n, h in home.items():
                    if h is None:
                        home[n] = pi
        for pi, poly in enumerate(polys):
            inside = [n for n in g if home.get(n) == pi]
            if not inside:
                continue
            name = f"{opt.name}{SETTINGS['elevation_suffix']}{len(scraps) + 1}"
            o = [f"scrap {name} -projection extended{opt.attrs(K)}", ""]
            o += presumed_marks(presumed, poly, px)
            if SETTINGS['wall_subtypes']:
                o += (el.debris_marks(feats, px) if feats else []) + \
                    subtype_marks(mine, px, feats.kinds if feats else {})
            o += walls_th2(walls, poly, px, inner='line wall -outline none' if feats else None)
            o += water_th2(mine, poly, px, name, flow=False)
            if feats:
                o += el.th2(feats, poly, walls, px, name)
            for n, sname, centre, W, H in made:      # cross sections where they were sketched
                if n in inside:
                    o += ["point %.2f %.2f section -scrap %s" % (*px(centre), sname), ""]
            for n in inside:
                o += ["point %.2f %.2f station -name %s" % (*px(pos[n]), opt.station(n)), ""]
            o += ["endscrap", ""]
            body += o
            scraps.append(name)
            polys_all.append(poly)

    xs_plan = []
    if made and plan_layout is not None:
        ppos = {}
        for n, *_ in made:
            ps = plan_layout.find(n, opt.survey)
            if ps:
                ppos[n] = ps[0]
        # every station and shot nearby, for direction, width and clearance
        allpos = {}
        for (nm, sv), ps in plan_layout.by_name.items():
            allpos.setdefault(f"{nm}@{sv}", ps[0])
        geo = PlanGeometry(allpos, plan_layout.shots)
        key = {n: f"{n}@{opt.survey}" if f"{n}@{opt.survey}" in allpos else
               next((k for k in allpos if k.split('@')[0] == n), None) for n in ppos}
        madek = [(key[n], name, c, W, H) for n, name, c, W, H in made if key.get(n)]
        if madek:
            pname = f"{opt.name}XS"
            xs_plan = [f"scrap {pname} -projection plan{opt.attrs(K)}", "",
                       "# Where each cross section is cut (line section) and drawn (point section).", ""]
            xs_plan += place_sections(geo, madek, px, [])
            for k, *_ in madek:
                xs_plan += ["point %.2f %.2f station -name %s" % (*px(allpos[k]), opt.station(k.split('@')[0])), ""]
            xs_plan += ["endscrap", ""]
    anchor = next(iter(pos)) if pos else ''
    head = header(sketch.path if sketch.path.lower().endswith('.xvi') and not flipped else None,
                  out_path, anchor, px(pos[anchor]) if anchor else (0, 0), polys_all, px)
    note = ["# Converted from %s by tools/sketch2therion (extended elevation)." % os.path.basename(sketch.path or 'a sketch'),
            ("# Split into one scrap per group of stations that fits Therion's layout." if SETTINGS['layout_split'] else
             "# One scrap per sketch, or as chosen by hand ([scraps_extended] in tools/project.toml)."), ""]
    plan_scraps = [f"{opt.name}XS"] if xs_plan else []
    return "\n".join(head + note + body + xs_text + xs_plan), scraps, [m[1] for m in made], plan_scraps
