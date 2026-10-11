# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see tools/LICENSE.
"""Floor marks and interior lines, for caves whose sketches use brown for
the floor (tools/project.toml, [convert] brown = "floor").

Brown, in metres on the sketch:
- a closed loop at least `boulder_min` across is a boulder
  (`line rock-border -close on`);
- a smaller closed loop is debris; debris loops near each other make one
  `area debris`;
- dots and short straight dashes are sand (mud is drawn as sand: no clay):
  three or more near each other make an `area sand`;
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


def is_curl(pp):
    """A stroke curled round on itself (a loop not quite closed): at least
    twice as long as it is wide, its ends within 0.7 of its width."""
    sp = span(pp)
    return sp > 0 and length(pp) >= 2.0 * sp and math.dist(pp[0], pp[-1]) <= 0.7 * sp


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
        if SETTINGS['line_tol_rel']:        # in proportion to the legs nearby (scale.py)
            from . import scale
            mid = line.interpolate(0.5, normalized=True)
            t = scale.tol((mid.x, mid.y), SETTINGS['line_tol_rel'], tol)
            window, tol = 3 * t, t           # smoothed over 3 times the tolerance, as walls are
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
    """'boulder', 'debris', 'sand' or 'line' for one brown stroke.

    With `mark_max`, a closed loop smaller than that is a mark of dirt
    (counted as sand: alone it is ignored)."""
    if length(pp) < DOT or span(pp) < DOT:
        return 'sand'
    if mark_max and is_closed(pp) and span(pp) < mark_max:
        return 'sand'
    if is_closed(pp):
        return 'boulder' if span(pp) >= boulder_min else 'debris'
    if length(pp) < DASH and is_straight(pp):
        return 'sand'                   # a dash of mud: sand (user, 2026-10-11: no clay)
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


LARGE_ROCK = 0.25    # a rock this share of the passage's width across it, or more, is large: drawn


def passage_width(passage, c, n=12):
    """The narrowest chord of the passage through the point c (m)."""
    from shapely.geometry import Point as P_
    if passage is None or not passage.contains(P_(c)):
        return None
    reach = math.sqrt(passage.area) * 4 + 1
    best = None
    for i in range(n):
        a = math.pi * i / n
        d = (math.cos(a) * reach, math.sin(a) * reach)
        chord = LineString([(c[0] - d[0], c[1] - d[1]), (c[0] + d[0], c[1] + d[1])]).intersection(passage)
        parts = [g for g in getattr(chord, 'geoms', [chord]) if g.geom_type == 'LineString']
        part = next((g for g in parts if g.distance(P_(c)) < 1e-6), None)
        if part is not None and (best is None or part.length < best):
            best = part.length
    return best


def large_rock(pp, passage):
    """True if a rock (closed loop) is large for the passage it is in (Style.md, rocks)."""
    from shapely.geometry import Polygon as Pg
    if len(pp) < 3:
        return False
    g = Pg(pp).buffer(0)
    if g.is_empty:
        return False
    w = passage_width(passage, (g.centroid.x, g.centroid.y))
    size = max(g.bounds[2] - g.bounds[0], g.bounds[3] - g.bounds[1])
    return w is not None and size >= LARGE_ROCK * w


def brown(strokes, passage, boulder_min, barriers=()):
    """(boulders [closed point lists], areas [(kind, Polygon)], lines [point lists]).

    With [convert] area_marks, boulders near other loops go into an area
    (`blocks` if most loops are boulder-sized, else `debris`) instead of
    being drawn singly as well; only an isolated boulder is drawn alone.
    Areas do not cross `barriers` (LineStrings: interior lines, steps)."""
    from .settings import SETTINGS
    sorted_ = {'boulder': [], 'debris': [], 'sand': [], 'line': []}
    for pp in strokes:
        if not pp:
            continue
        if not passage.buffer(0.3).intersects(LineString(pp) if len(pp) > 1 else Point(pp[0])):
            continue
        if SETTINGS['curls_closed'] and len(pp) > 3 and not is_closed(pp) and is_curl(pp):
            pp = list(pp) + [pp[0]]      # a boulder drawn as a curl, not quite closed
        k = kind_of(pp, boulder_min, SETTINGS['mark_max'])
        if k == 'line' and SETTINGS['dash_max'] and length(pp) <= SETTINGS['dash_max'] \
                and math.dist(pp[0], pp[-1]) >= 0.85 * length(pp):
            k = 'sand'                  # a longer dash, roughly straight: mud, drawn as sand
        elif k == 'line' and SETTINGS['rock_curves'] and length(pp) <= (SETTINGS['dash_max'] or DASH) \
                and math.dist(pp[0], pp[-1]) < 0.7 * length(pp):
            k = 'boulder' if span(pp) >= boulder_min else 'debris'      # a curved one: part of a rock's outline
        sorted_[k].append(pp)

    def shape(kind, pp):
        if kind in ('boulder', 'debris') and len(pp) > 2:
            if not is_closed(pp):                # an open rock outline
                return LineString(pp).buffer(0.05)
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
            if SETTINGS['drawn_rocks']:
                # a group is an area; a rock in it large for the passage it is in is drawn too
                alone += [pp for k, pp in members if k == 'boulder' and large_rock(pp, passage)]
            big = sum(1 for k, _ in members if k == 'boulder')
            groups.append(('blocks' if big * 2 > len(members) else 'debris', [pp for _, pp in members], 1))
        sorted_['boulder'] = alone
    else:
        groups.append(('debris', sorted_['debris'], 1))
    if SETTINGS['mud_grow'] and barriers:
        # a mark touching a step or other line inside the passage is one of its ticks, not mud
        bar = unary_union(list(barriers))
        for k in ('sand',):
            touching = [pp for pp in sorted_[k] if min(bar.distance(Point(pp[0])), bar.distance(Point(pp[-1]))) <= 0.15]
            sorted_[k] = [pp for pp in sorted_[k] if not any(pp is t for t in touching)]
            sorted_['line'] += [pp for pp in touching if length(pp) >= DASH]      # a longer one stays a line
    if SETTINGS['mud_grow'] and groups:
        # marks among the rocks are the rocks' drawing, not mud or sand
        # (round the rocks themselves: a hull of them all can take in the mud beside them)
        rocks = unary_union([LineString(pp).buffer(0.3) if len(pp) > 1 else Point(pp[0]).buffer(0.3)
                             for _, ms, _ in groups for pp in ms])
        sorted_['sand'] = [pp for pp in sorted_['sand'] if not rocks.contains(Point(pp[len(pp) // 2]))]
    groups += [('sand', sorted_['sand'], 3)]

    areas = []
    for kind, marks, need in groups:
        mark_kind = 'debris' if kind in ('debris', 'blocks') else kind
        geoms = [shape(mark_kind, pp) for pp in marks]
        mud = kind == 'sand' and SETTINGS['mud_grow']
        groups_ = cluster(geoms, SETTINGS['mud_near'] or NEAR) if kind == 'sand' else \
            (cluster(geoms) if not SETTINGS['area_marks'] else [set(range(len(marks)))])
        for grp in groups_:
            if len(grp) < need:
                if kind == 'sand' and SETTINGS['dash_max']:     # a longer dash on its own stays a line
                    sorted_['line'] += [marks[i] for i in grp if length(marks[i]) >= DASH]
                continue
            pts = [p for i in grp for p in marks[i]]
            if mud:
                # a patch of mud or sand: round its marks, following the passage, not a hull across it
                r = SETTINGS['mud_grow']
                g = unary_union([geoms[i].buffer(r, join_style=1) for i in grp]) \
                    .buffer(r, join_style=1).buffer(-r, join_style=1).intersection(passage)
            elif SETTINGS['area_grow']:
                # rocks: grown round their marks within the passage; _keep_side stops it at barriers
                r = SETTINGS['area_grow']
                bars = [b for b in barriers if b.length > 0]

                def grown(m):
                    # the mark's own side of any barrier it would grow across (so an area does
                    # not wrap round the end of a long line running beside it)
                    g = m.buffer(r, join_style=1)
                    near = [b for b in bars if b.intersects(g)]
                    if not near:
                        return g
                    cut = g.difference(unary_union([b.buffer(0.03) for b in near]))
                    parts = [p for p in getattr(cut, 'geoms', [cut]) if p.geom_type == 'Polygon']
                    mine = [p for p in parts if p.intersects(m)] or parts[:1]
                    return unary_union(mine) if mine else g
                g = unary_union([grown(geoms[i]) for i in grp]) \
                    .buffer(r / 4, join_style=1).buffer(-r / 4, join_style=1).intersection(passage)
            else:
                g = MultiPoint(pts).convex_hull.buffer(0.1, join_style=1).intersection(passage)
            g = _keep_side(g, [geoms[i] for i in grp], barriers)
            if SETTINGS['area_min_width']:
                # an area needs room for its symbols: thin parts are dropped
                w = SETTINGS['area_min_width'] * (0.6 if kind == 'sand' else 1.0)
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
                own = g
                if SETTINGS['area_splines']:
                    # notches closed up first, so a few spline nodes follow the shape
                    r = 2 * SETTINGS['area_splines']
                    g = g.buffer(r, join_style=1).buffer(-r, join_style=1)
                if SETTINGS['area_over_walls']:
                    # but never into another part of the passage, beyond a wall or pillar (the
                    # walls clip an area only to the scrap's outline, which holds that passage too)
                    from shapely import make_valid
                    try:
                        others = make_valid(passage).difference(make_valid(own).buffer(0.05)).buffer(-0.05)
                        g = make_valid(g).difference(others.buffer(SETTINGS['area_splines'] or 0.0)).buffer(0)
                    except Exception:           # (a degenerate shape: leave the area as it is)
                        pass
                    if g.geom_type == 'MultiPolygon':
                        g = max(g.geoms, key=lambda q: q.area)
                if g.geom_type == 'Polygon' and not g.is_empty and \
                        g.intersection(passage).area >= SETTINGS['area_inside_min'] * g.area:
                    # (an area mostly outside the walls, its marks drawn along the wall, is not drawn)
                    areas.append((kind, g.simplify(SETTINGS['area_splines'] or 0.03)))
    if SETTINGS['mud_grow']:
        areas = _mud_patches(areas)
    return sorted_['boulder'], areas, sorted_['line']


def _mud_patches(areas):
    """Sand areas (mud is drawn as sand) that overlap merged into one, and kept off the
    boulder and debris areas (the rocks are drawn there, not mud)."""
    from .settings import SETTINGS
    rocks = unary_union([g for k, g in areas if k in ('blocks', 'debris')])
    out = [(k, g) for k, g in areas if k not in ('sand', 'blocks', 'debris')]
    for kind in ('blocks', 'debris'):        # rock areas that overlap are one
        g = unary_union([g for k, g in areas if k == kind])
        for part in getattr(g, 'geoms', [g]):
            if part.geom_type == 'Polygon' and not part.is_empty:
                out.append((kind, Polygon(part.exterior).simplify(SETTINGS['area_splines'] or 0.03)))
    merged = {'sand': unary_union([g for k, g in areas if k == 'sand'])}
    for kind in ('sand',):
        g = merged[kind]
        if g.is_empty:
            continue
        if not rocks.is_empty:
            g = g.difference(rocks.buffer(0.05)).buffer(0)
        for part in getattr(g, 'geoms', [g]):
            if part.geom_type == 'Polygon' and part.area > max(0.02, SETTINGS['area_min_area']):
                out.append((kind, Polygon(part.exterior).simplify(SETTINGS['area_splines'] or 0.03)))
    return out


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


def chain_lines(lines, boulder_min, gap, turn=45.0):
    """Brown line strokes (not marks) drawn as one line in pieces: where one
    ends within `gap` m of the next and carries on (turning under `turn`
    degrees), they are joined into one line."""
    from .settings import SETTINGS
    idx = [k for k, (c, pp) in enumerate(lines) if c == 'BROWN' and len(pp) > 1
           and kind_of(pp, boulder_min, SETTINGS['mark_max']) == 'line' and length(pp) >= (SETTINGS['barrier_min'] or 0.6)]
    pieces = {k: list(lines[k][1]) for k in idx}

    def head(pp, at_end):
        a, b = (pp[-2], pp[-1]) if at_end else (pp[1], pp[0])
        d = math.dist(a, b) or 1.0
        return ((b[0] - a[0]) / d, (b[1] - a[1]) / d)
    joined = True
    while joined:
        joined = False
        keys = list(pieces)
        for i in keys:
            for j in keys:
                if i == j or i not in pieces or j not in pieces:
                    continue
                a, b = pieces[i], pieces[j]
                for ra in (False, True):
                    for rb in (False, True):
                        A = a[::-1] if ra else a
                        B = b[::-1] if rb else b
                        if math.dist(A[-1], B[0]) > gap:
                            continue
                        u, v = head(A, True), head(B, False)
                        v = (-v[0], -v[1])
                        if math.degrees(math.acos(max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1])))) > turn:
                            continue
                        pieces[i] = A + B
                        del pieces[j]
                        joined = True
                        break
                    if joined:
                        break
                if joined:
                    break
            if joined:
                break
    out = [l for k, l in enumerate(lines) if k not in idx]
    return out + [('BROWN', pp) for pp in pieces.values()]


def th2(lines, passage, px, idbase, wall_colours, boulder_min, barriers=()):
    """th2 text for the floor marks and interior lines of one scrap."""
    from .settings import SETTINGS
    if SETTINGS['chain_gap']:              # a line sketched in pieces is one line
        lines = chain_lines(lines, boulder_min, SETTINGS['chain_gap'])
    strokes = [pp for c, pp in lines if c == 'BROWN' and pp]
    inner_pp = interior(lines, passage, wall_colours)
    bmin = SETTINGS['barrier_min']
    # a short line inside the passage does not stop an area (it is often part of what is drawn there)
    inner = [LineString(pp) for pp in inner_pp if LineString(pp).length >= bmin]
    if bmin:
        # long brown lines (a ledge, a step drawn without ticks) also stop areas
        inner += [LineString(pp) for c, pp in lines if c == 'BROWN' and len(pp) > 1
                  and kind_of(pp, boulder_min, SETTINGS['mark_max']) == 'line' and LineString(pp).length >= bmin]
    boulders, areas, brown_lines = brown(strokes, passage, boulder_min, list(barriers) + inner)
    o = []
    for pp in boulders:
        g = Polygon(pp).buffer(0) if len(pp) > 2 else None
        if g is not None and g.geom_type == 'MultiPolygon':     # a loop drawn crossing itself
            g = max(g.geoms, key=lambda q: q.area)
        ring = list(g.simplify(0.03).exterior.coords) if g is not None and not g.is_empty else pp
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
    # (an area drawn as a spline bulges past its simplified outline by up to area_splines)
    rocks = [g.buffer(SETTINGS['area_splines']) for kind, g in areas if kind in ('blocks', 'debris')]
    if not SETTINGS['area_lines'] and rocks:
        # brown lines mostly inside a boulder or debris area are part of the rocks' drawing
        def in_rocks(pp):
            L = LineString(pp).intersection(inside)        # the part that would be drawn
            if SETTINGS['barrier_min'] and LineString(pp).length >= SETTINGS['barrier_min']:
                return False                               # a long line is not rock detail
            return L.length > 0 and max(L.intersection(r).length for r in rocks) >= 0.5 * L.length
        brown_lines = [pp for pp in brown_lines if len(pp) < 2 or not in_rocks(pp)]
    # interior lines are marked by an id: drawn in a colour that is not a wall's, they are
    # inner whatever side the legs are on (a channel either side of the leg: TridentLeft
    # 21 to 29), so the outer-line rule (smooth.outer_lines) leaves them be
    n = [0]

    def head():
        n[0] += 1
        return f"line border -id {idbase}-inner{n[0]}" if SETTINGS['outer_walls'] else "line border"
    for pp in brown_lines:
        g = LineString(pp).intersection(inside)
        for part in getattr(g, 'geoms', [g]):
            if part.geom_type == 'LineString' and part.length >= 0.3:
                o += [head()] + smooth_rows(list(part.coords), px) + ["endline", ""]
    rock_areas = unary_union([g for k, g in areas if k in ('blocks', 'debris')]) if bmin else None
    for pp in inner_pp:
        L = LineString(pp)
        if rock_areas is not None and not rock_areas.is_empty and L.length < bmin \
                and L.intersection(rock_areas).length >= 0.5 * L.length:
            continue                     # a short line among the rocks: part of their drawing
        o += [head()] + smooth_rows(pp, px) + ["endline", ""]
    return o
