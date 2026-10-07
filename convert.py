# Ported from caves-mendip-swildons, tools/sketch2therion (commit 198bf46,
# https://github.com/paperclipmonkey/caves-mendip-swildons). GPLv3: see tools/LICENSE.
"""Sketch -> th2: plan scraps, extended-elevation scraps and cross-sections.

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


def wall_strokes(lines):
    """(wall strokes, boulders, slope arrows) from the sketch lines."""
    black = [pp for c, pp in lines if c == 'BLACK' and len(pp) > 1
             and sum(math.dist(a, b) for a, b in zip(pp, pp[1:])) >= 0.15]
    black, boulders, arrows = split_symbols(black)
    cols = [c for c in SETTINGS['wall_colours'] if c != 'BLACK']
    other = [pp for c, pp in lines if c in cols and len(pp) > 1 and is_outline(pp)]
    return black + other, boulders, arrows


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


def elevation_fill(walls, legs, extra=(), below=3.0, above=5.0):
    """As plan_fill, plus a band from floor to roof along each leg: the nearest
    sketch line below (within `below` m) and above (within `above` m), every
    20 cm. Where either is missing no band is drawn, so a gap in the sketch
    stays a gap instead of filling the space between passages."""
    segs = [(a, b) for w in walls for a, b in zip(w, w[1:]) if abs(b[0] - a[0]) > 1e-6]
    boxes = []
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


def traced_outer(run, poly, others, legs, samples=5, reach=20.0, leg_reach=8.0):
    """(side, width) if, for most of the stroke, tracing out to one side
    (+1 left, -1 right) reaches the edge of the passage fill without
    crossing another wall stroke or a survey leg, while the other side has
    a survey leg (the passage); else None. width: how far the fill goes on
    beyond the stroke there (median). The fill's closing-up bridges a
    wall's inward bends, leaving the real wall inside it; a pillar's wall
    fails, as tracing through the pillar meets its far wall."""
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
            if back.intersects(legs):
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
            t = traced_outer(run, poly, others, leg_lines)
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


def walls_th2(walls, poly, px, legs=(), splay_ends=()):
    ring = list(poly.exterior.coords)
    o = []
    for edge, run in wall_runs(walls, poly):
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
    def __init__(self, name, survey=None, author=None, copyright=None, qualify=False):
        self.name = name
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


# -- cross-sections ----------------------------------------------------------------

def gather_section(centre, lines, used, stations, near=1.2, reach=6.0):
    """Indices of the sketch lines making up the cross-section drawn around
    `centre`: lines within `near` of it or around it, then lines touching those,
    keeping only lines wholly within `reach` of the centre and clear of the
    survey stations (which are on the main drawing, not the section)."""
    C = Point(centre)
    stp = [Point(p) for p in stations]

    def ok(pp):
        if any(math.dist(p, centre) > reach for p in pp):
            return False
        ls = LineString(pp)
        return all(ls.distance(q) > 0.3 for q in stp)

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


def section_outline(strokes):
    """One closed outline for a cross-section, from its wall strokes.

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
    for d in (0.1, 0.2, 0.35, 0.6):
        g = U.buffer(d, join_style=1)
        big = max(_polygons(g, 0.0) or [Polygon()], key=lambda p: p.area)
        if big.is_empty:
            continue
        filled = Polygon(big.exterior)
        if filled.area - g.area > 0.2 * filled.area:      # it encloses a passage
            o = filled.buffer(-d, join_style=1)
            ps = _polygons(o, 0.01)
            if ps:
                out = max(ps, key=lambda p: p.area)
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
    """A cross-section scrap. lines: [(colour, pts)] gathered for it.
    Returns (th2 lines, width, height) or None if it has no walls."""
    wl = [pp for c, pp in lines if c in WALLS and len(pp) > 1]
    if not wl:
        return None
    poly = section_outline(wl)
    if poly is None:
        return None
    xpx = lambda p: (K * (p[0] - centre[0]) + 1000, K * (p[1] - centre[1]) + 1000)
    o = [f"scrap {name} -projection none{attrs}", "", comment, ""]
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
    for pp in clean(rest, min_len=0.3):
        o += ["line border -clip off"] + bezier_lines(pp, xpx) + ["endline", ""]
    o += water_th2(lines, poly, xpx, name, flow=False)
    o += ["endscrap", ""]
    b = poly.bounds
    return o, b[2] - b[0], b[3] - b[1]


def section_scraps(sketch, opt, K):
    """Cross-section scraps for every connect line in the sketch.
    Returns (th2 lines, [(station, scrap name, centre, width, height)], used line indices)."""
    pos = sketch.positions()
    used = set()
    o, made = [], []
    for n, spos, centre in sketch.sections():
        idx = gather_section(centre, sketch.lines, used, list(pos.values()))
        used |= set(idx)
        mine = [sketch.lines[i] for i in idx]
        name = f"{opt.name}_xs_{n}".replace('.', '_')
        r = section_th2(name, opt.attrs(K), mine, centre, K, f"# Cross-section at station {n}.")
        if r is None:
            continue
        o += r[0]
        W, H = r[1], r[2]
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


def section_line(geo, n, px):
    """`line section` across the passage at station n."""
    P = geo.pos[n]
    u = geo.direction(n)
    perp = (-u[1], u[0])
    hw = geo.half_width(n, perp)
    a = (P[0] - perp[0] * hw, P[1] - perp[1] * hw)
    b = (P[0] + perp[0] * hw, P[1] + perp[1] * hw)
    return ["line section", "  %.2f %.2f" % px(a), "  %.2f %.2f" % px(b), "endline", ""], perp, hw


def place_sections(geo, made, px, placed):
    """Put cross-sections drawn in a side view beside the passage on the plan,
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
    """Station groups that fit Therion's layout with one shift each."""
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
    xs_text, made, used = section_scraps(sketch, opt, K)
    lines = [l for i, l in enumerate(sketch.lines) if i not in used]
    geo = PlanGeometry(pos, sketch.shots)
    member = {n: i for i, g in enumerate(groups) for n in g}
    near = lambda p: member.get(_nearest(pos, p), 0) if pos else 0

    body, scraps, polys_all = [], [], []
    placed = []
    for gi, g in enumerate(groups):
        mine = [(c, pp) for c, pp in lines if pp and near(pp[len(pp) // 2]) == gi]
        notes = []
        if SETTINGS['notation']:          # steps and overhangs, by their notation
            from . import notation
            notes, used_n = notation.find(mine)
            mine = [l for k, l in enumerate(mine) if k not in used_n]
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
        gset = set(g)
        legs = [[pos[a], pos[b]] for a, b in geo.legs if a in gset and b in gset]
        polys = plan_fill(walls, legs, [pp for c, pp in mine if c == 'BLUE'])
        if SETTINGS['interior_borders']:      # cut the fill back to the outer walls it bridged
            ends = [e for _, _, e in sketch.splays()]
            polys = [cut_back(p, walls, legs, ends) for p in polys]
        for poly in polys:
            name = f"{opt.name}P{len(scraps) + 1}"
            inside = [n for n in g if poly.buffer(1.0).contains(Point(pos[n]))]
            if not inside:
                inside = [_nearest({n: pos[n] for n in g}, poly.representative_point().coords[0])]
            o = [f"scrap {name} -projection plan{opt.attrs(K)}", ""]
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
    its cross-sections (if Therion's plan layout is given)."""
    K = sketch.scale
    sketch, groups, flipped = _split(sketch, layout, opt.survey, tol)
    pos = sketch.positions()
    px = lambda p: (K * p[0], K * p[1])
    xs_text, made, used = section_scraps(sketch, opt, K)
    lines = [l for i, l in enumerate(sketch.lines) if i not in used]
    legs_all = [(a, b) for a, b, *_ in sketch.legs()]
    member = {n: i for i, g in enumerate(groups) for n in g}
    near = lambda p: member.get(_nearest(pos, p), 0) if pos else 0

    body, scraps, polys_all = [], [], []
    for gi, g in enumerate(groups):
        if len(g) < 2:
            continue
        mine = [(c, pp) for c, pp in lines if pp and near(pp[len(pp) // 2]) == gi]
        walls, _b, _a = wall_strokes(mine)
        walls = clean(walls)
        if not walls:
            continue
        gset = set(g)
        legs = [(pos[a], pos[b]) for a, b in legs_all if a in gset and b in gset]
        for poly in elevation_fill(walls, legs, [pp for c, pp in mine if c == 'BLUE'], below, above):
            inside = [n for n in g if poly.buffer(1.0).contains(Point(pos[n]))]
            if not inside:
                continue
            name = f"{opt.name}E{len(scraps) + 1}"
            o = [f"scrap {name} -projection extended{opt.attrs(K)}", ""]
            o += walls_th2(walls, poly, px)
            o += water_th2(mine, poly, px, name, flow=False)
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
                       "# Where each cross-section is cut (line section) and drawn (point section).", ""]
            xs_plan += place_sections(geo, madek, px, [])
            for k, *_ in madek:
                xs_plan += ["point %.2f %.2f station -name %s" % (*px(allpos[k]), opt.station(k.split('@')[0])), ""]
            xs_plan += ["endscrap", ""]
    anchor = next(iter(pos)) if pos else ''
    head = header(sketch.path if sketch.path.lower().endswith('.xvi') and not flipped else None,
                  out_path, anchor, px(pos[anchor]) if anchor else (0, 0), polys_all, px)
    note = ["# Converted from %s by tools/sketch2therion (extended elevation)." % os.path.basename(sketch.path or 'a sketch'),
            "# Split into one scrap per group of stations that fits Therion's layout.", ""]
    plan_scraps = [f"{opt.name}XS"] if xs_plan else []
    return "\n".join(head + note + body + xs_text + xs_plan), scraps, [m[1] for m in made], plan_scraps
