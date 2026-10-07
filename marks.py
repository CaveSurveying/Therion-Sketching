# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see tools/LICENSE.
"""Floor marks and interior lines, for caves whose sketches use brown for
the floor (tools/project.toml, [convert] brown = "floor").

Brown, in metres on the sketch:
- a closed loop at least `boulder_min` across is a boulder
  (`line rock-border -close on`);
- a smaller closed loop is debris; debris loops near each other make one
  `area debris`;
- dots are sand, short straight dashes are mud: three or more near each
  other make an `area sand` or `area clay`;
- any other brown line is a step or edge in the mud: a `line border`.

Lines inside the passage in other colours that are not walls, water or
formations (grey, mostly: ceiling and floor steps, channels) are
`line border`. Sketches are drawn by hand underground, so the shapes are
judged loosely; check them in the review.
"""
import math

from shapely.geometry import LineString, MultiPoint, Point, Polygon
from shapely.ops import unary_union

from .walls import bezier_closed, bezier_lines

NEAR = 0.6            # m: marks this close are one area
DOT = 0.12            # m: a stroke shorter than this is a dot
DASH = 0.6            # m: a straight open stroke shorter than this is a dash
NOT_INTERIOR = ('BLUE', 'GREEN', 'RED', 'ORANGE', 'PURPLE')


def length(pp):
    return sum(math.dist(a, b) for a, b in zip(pp, pp[1:]))


def span(pp):
    return max((math.dist(a, b) for a in pp for b in pp), default=0.0)


def is_closed(pp):
    L = length(pp)
    return L >= 0.2 and math.dist(pp[0], pp[-1]) <= max(0.15, 0.2 * L)


def is_straight(pp, tol=0.08):
    (x1, y1), (x2, y2) = pp[0], pp[-1]
    d = math.dist(pp[0], pp[-1]) or 1e-9
    return max(abs((x2 - x1) * (y1 - y) - (x1 - x) * (y2 - y1)) / d for x, y in pp) <= tol


def smooth_rows(pp, px, tol=0.04, window=0.5):
    """th2 rows for a hand-drawn line: points only where it really bends.
    The line is first smoothed (a running mean over `window` m, so hand
    wobble is not taken for bends), then simplified to within `tol` m, and
    drawn as a spline through what is left. Unless [convert] smooth_lines
    is off (then every sketch point is kept)."""
    from .settings import SETTINGS
    if SETTINGS['smooth_lines'] and len(pp) > 2:
        line = LineString(pp)
        n = max(2, round(line.length / 0.05))
        dense = [line.interpolate(k / n, normalized=True).coords[0] for k in range(n + 1)]
        h = max(1, round(window / 0.05 / 2))
        smooth = [dense[0]] + [
            (sum(p[0] for p in dense[max(0, k - h):k + h + 1]) / len(dense[max(0, k - h):k + h + 1]),
             sum(p[1] for p in dense[max(0, k - h):k + h + 1]) / len(dense[max(0, k - h):k + h + 1]))
            for k in range(1, len(dense) - 1)] + [dense[-1]]
        pp = list(LineString(smooth).simplify(tol).coords)
    return bezier_lines(pp, px)


def gour_rows(pp, px):
    """th2 rows for a gour: a smooth arc through a few evenly spaced points
    (three, or four on a long one), not every wobble of the sketch."""
    line = LineString(pp)
    n = 2 if line.length < 1.5 else 3
    pts = [line.interpolate(k / n, normalized=True).coords[0] for k in range(n + 1)]
    return bezier_lines(pts, px)


def green_loops(strokes):
    """Green closed loops that are not nested rings: [indices]. A ring
    inside another (or with one inside it) is a formation, a boss."""
    loops = [(i, Polygon(pp).buffer(0)) for i, pp in strokes if len(pp) > 3 and is_closed(pp)]
    out = []
    for i, g in loops:
        if g.is_empty:
            continue
        # nested: one ring wholly inside another (loops that merely touch are not)
        nested = any(j != i and not h.is_empty and
                     (g.buffer(0.03).contains(h) or h.buffer(0.03).contains(g))
                     for j, h in loops)
        if not nested:
            out.append(i)
    return out


def is_gour(pp):
    """A solid green line that runs on (not a ring or curl: those are formations)."""
    L = length(pp)
    return L >= 0.6 and not is_closed(pp) and math.dist(pp[0], pp[-1]) >= 0.5 * L


def kind_of(pp, boulder_min, mark_max=0.0):
    """'boulder', 'debris', 'sand', 'clay' or 'line' for one brown stroke.

    With `mark_max`, a closed loop smaller than that is a mark of dirt
    (counted as sand: alone it is ignored)."""
    if length(pp) < DOT or span(pp) < DOT:
        return 'sand'
    if mark_max and is_closed(pp) and span(pp) < mark_max:
        return 'sand'
    if is_closed(pp):
        return 'boulder' if span(pp) >= boulder_min else 'debris'
    if length(pp) < DASH and is_straight(pp):
        return 'clay'
    return 'line'


def cluster(geoms, near=NEAR):
    """Groups of indices of geometries within `near` of each other."""
    groups = []
    for i, g in enumerate(geoms):
        hit = [k for k, grp in enumerate(groups) if any(g.distance(geoms[j]) < near for j in grp)]
        merged = {i}
        for k in sorted(hit, reverse=True):
            merged |= groups.pop(k)
        groups.append(merged)
    return groups


def _keep_side(g, marks_geoms, barriers):
    """Area `g` cut along the barrier lines (a trench, a step), keeping the
    pieces that hold marks: an area does not cross to the other side."""
    if not barriers:
        return g
    cut = g.difference(unary_union([b.buffer(0.05) for b in barriers]))
    pieces = list(getattr(cut, 'geoms', [cut]))
    keep = [p for p in pieces if p.geom_type == 'Polygon' and any(p.intersects(m) for m in marks_geoms)]
    return unary_union(keep) if keep else g


def brown(strokes, passage, boulder_min, barriers=()):
    """(boulders [closed point lists], areas [(kind, Polygon)], lines [point lists]).

    With [convert] area_marks, boulders near other loops go into an area
    (`blocks` if most loops are boulder-sized, else `debris`) instead of
    being drawn singly as well; only an isolated boulder is drawn alone.
    Areas do not cross `barriers` (LineStrings: interior lines, steps)."""
    from .settings import SETTINGS
    sorted_ = {'boulder': [], 'debris': [], 'sand': [], 'clay': [], 'line': []}
    for pp in strokes:
        if not pp:
            continue
        if not passage.buffer(0.3).intersects(LineString(pp) if len(pp) > 1 else Point(pp[0])):
            continue
        sorted_[kind_of(pp, boulder_min, SETTINGS['mark_max'])].append(pp)

    def shape(kind, pp):
        if kind in ('boulder', 'debris') and len(pp) > 2:
            return Polygon(pp).buffer(0)
        return LineString(pp) if len(pp) > 1 else Point(pp[0])

    groups = []          # (area kind, [marks], marks needed)
    if SETTINGS['area_marks']:
        loops = [('boulder', pp) for pp in sorted_['boulder']] + [('debris', pp) for pp in sorted_['debris']]
        alone = []
        for grp in cluster([shape(k, pp) for k, pp in loops]):
            members = [loops[i] for i in grp]
            if len(members) == 1:
                k, pp = members[0]
                if k == 'boulder':
                    alone.append(pp)
                elif not SETTINGS['mark_max']:
                    groups.append(('debris', [pp], 1))
                continue                      # (a lone small loop is dirt when mark_max is set)
            big = sum(1 for k, _ in members if k == 'boulder')
            groups.append(('blocks' if big * 2 > len(members) else 'debris', [pp for _, pp in members], 1))
        sorted_['boulder'] = alone
    else:
        groups.append(('debris', sorted_['debris'], 1))
    groups += [('sand', sorted_['sand'], 3), ('clay', sorted_['clay'], 3)]

    areas = []
    for kind, marks, need in groups:
        mark_kind = 'debris' if kind in ('debris', 'blocks') else kind
        geoms = [shape(mark_kind, pp) for pp in marks]
        for grp in (cluster(geoms) if kind in ('sand', 'clay') or not SETTINGS['area_marks'] else [set(range(len(marks)))]):
            if len(grp) < need:
                continue
            pts = [p for i in grp for p in marks[i]]
            g = MultiPoint(pts).convex_hull.buffer(0.1, join_style=1).intersection(passage)
            g = _keep_side(g, [geoms[i] for i in grp], barriers)
            if SETTINGS['area_min_width']:
                # an area needs room for its symbols: thin parts are dropped
                w = SETTINGS['area_min_width'] * (0.6 if kind in ('sand', 'clay') else 1.0)
                g = g.buffer(-w / 2, join_style=1).buffer(w / 2, join_style=1)
            if g.geom_type == 'MultiPolygon':
                g = max(g.geoms, key=lambda q: q.area)
            if g.geom_type == 'Polygon' and g.area > max(0.02, SETTINGS['area_min_area']):
                if SETTINGS['area_over_walls']:
                    # run out over the walls, which clip it, rather than following them point by point
                    d = SETTINGS['area_over_walls']
                    g = unary_union([g, g.buffer(d, join_style=1).difference(passage.buffer(-0.02))
                                     .intersection(passage.buffer(d, join_style=1))]).buffer(0)
                    if g.geom_type == 'MultiPolygon':
                        g = max(g.geoms, key=lambda q: q.area)
                if SETTINGS['area_splines']:
                    # notches closed up first, so a few spline nodes follow the shape
                    r = 2 * SETTINGS['area_splines']
                    g = g.buffer(r, join_style=1).buffer(-r, join_style=1)
                areas.append((kind, g.simplify(SETTINGS['area_splines'] or 0.03)))
    return sorted_['boulder'], areas, sorted_['line']


def interior(lines, passage, wall_colours):
    """Open lines inside the passage that are not walls, water or formations
    (and not brown, when brown is read as floor marks)."""
    out = []
    inside = passage.buffer(-0.05)
    for c, pp in lines:
        if c in wall_colours or c in NOT_INTERIOR or c == 'BROWN' or len(pp) < 2 or length(pp) < 0.3:
            continue
        g = LineString(pp).intersection(inside)
        for part in getattr(g, 'geoms', [g]):
            if part.geom_type == 'LineString' and part.length >= 0.3:
                out.append(list(part.coords))
    return out


def th2(lines, passage, px, idbase, wall_colours, boulder_min, barriers=()):
    """th2 text for the floor marks and interior lines of one scrap."""
    from .settings import SETTINGS
    strokes = [pp for c, pp in lines if c == 'BROWN' and pp]
    inner = [LineString(pp) for pp in interior(lines, passage, wall_colours)]
    boulders, areas, brown_lines = brown(strokes, passage, boulder_min, list(barriers) + inner)
    o = []
    for pp in boulders:
        ring = list(Polygon(pp).buffer(0).simplify(0.03).exterior.coords) if len(pp) > 2 else pp
        if len(ring) >= 4:
            # straight segments, ending on the first point (tools/Style.md: rocks)
            ring = list(ring[:-1]) + [ring[0]]
            o += ["line rock-border -close on"] + ["  %.2f %.2f" % px(p) for p in ring] + ["endline", ""]
    for i, (kind, g) in enumerate(areas):
        lid = f"{idbase}-{kind}{i + 1}"
        ring = list(g.exterior.coords)[:-1]
        rows = bezier_closed(ring, px) if SETTINGS['area_splines'] and len(ring) >= 3 else \
            ["  %.2f %.2f" % px(p) for p in ring]
        o += [f"line border -subtype invisible -id {lid} -close on"] + rows + \
             ["endline", "", f"area {kind}", f"  {lid}", "endarea", ""]
    inside = passage.buffer(-0.05)
    for pp in brown_lines:
        g = LineString(pp).intersection(inside)
        for part in getattr(g, 'geoms', [g]):
            if part.geom_type == 'LineString' and part.length >= 0.3:
                o += ["line border"] + smooth_rows(list(part.coords), px) + ["endline", ""]
    for pp in interior(lines, passage, wall_colours):
        o += ["line border"] + smooth_rows(pp, px) + ["endline", ""]
    return o
