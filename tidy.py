# Ported from caves-mendip-swildons, tools/sketch2therion (commit 198bf46,
# https://github.com/paperclipmonkey/caves-mendip-swildons). GPLv3: see tools/LICENSE.
"""Tidy converted drawings so they follow Therion drawing conventions.

The converter first draws a scrap's walls with their outline switched off
(`line wall -outline none`) and fills the passage from a separate invisible
closed line. That works, but it is not how Therion drawings are made, and
it shows: the fill doesn't follow the walls exactly, and wall direction is
never checked. This module rewrites such scraps the conventional way:

- walls are outline walls, drawn with the passage on their LEFT, so the
  fill follows the walls. A gap where the wall runs along the passage
  but wasn't sketched is a presumed wall; a gap across the passage (an
  open end, a junction, where the drawing stops) is left open, and
  Therion closes it, joining each wall's end to the nearest free end
- nothing is drawn with `-clip off`; water has one invisible border,
  which runs out under the walls it lies against so that the wall is its
  edge (Therion clips it to the outline); marks outside the walls are
  dropped
- big boulders get rock edges
- slope arrows are kept off floor steps and pitches
- climbs are labelled C2, pitches P5 (no units), and labels are moved
  outside the passage so they don't break the walls

Only scraps the converter made are changed (they have the invisible closed
line); hand-drawn scraps in the same file are left exactly as they are.

    python3 -m tools.sketch2therion tidy FILE.th2 [...] [--scale 500]
"""
from .settings import inner_wall_head
import bisect
import math
import re

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import substring, unary_union

from .. import project as _project

# The drawings' licence (tools/project.toml), written at the top of each file.
LICENCE = _project.load().licence_comment

# label text heights in mm on the page, by -scale
REPORT = []     # (scrap, wall length kept on the outline, wall length) for checking

LABEL_MM = {'xs': 1.4, 's': 1.8, 'm': 2.4, 'l': 3.4, 'xl': 4.6}


# -- reading and writing th2 objects ----------------------------------------------

class Obj:
    """One line, area or point of a scrap, or a run of other text."""

    def __init__(self, kind, head='', rows=None, raw=''):
        self.kind = kind            # 'line', 'area', 'point', 'text'
        self.head = head            # e.g. "line wall -outline none"
        self.rows = rows or []      # the lines between head and endline/endarea
        self.raw = raw

    def text(self):
        if self.kind == 'line':
            return '\n'.join([self.head] + self.closed_rows() + ['endline'])
        if self.kind == 'area':
            return '\n'.join([self.head] + self.rows + ['endarea'])
        if self.kind == 'point':
            return self.head
        return self.raw

    def closed_rows(self):
        """A closed line ends where it starts. xtherion otherwise adds the
        point itself on loading and is left with a stale point selected, so
        selecting a line afterwards fails ("no such element in array")."""
        segs = self.segments()
        if '-close on' not in self.head or len(segs) < 2:
            return self.rows
        first = ('%.2f' % segs[0][-2], '%.2f' % segs[0][-1])
        if ('%.2f' % segs[-1][-2], '%.2f' % segs[-1][-1]) == first:
            return self.rows
        return self.rows + ['  ' + ' '.join(first)]

    # geometry of a line: rows are "x y" then "c1x c1y c2x c2y x y" (Bezier)
    def segments(self):
        out = []
        for r in self.rows:
            v = r.split()
            try:
                v = [float(x) for x in v]
            except ValueError:
                continue
            if len(v) in (2, 6):
                out.append(v)
        return out

    def set_segments(self, segs):
        # a point repeated straight after itself is a duplicate outline point
        # to Therion, and its 3D model then fails ("invalid scrap outline")
        rows, last = [], None
        for s in segs:
            end = ('%.2f' % s[-2], '%.2f' % s[-1])
            if end == last:
                continue
            rows.append('  ' + ' '.join('%.2f' % x for x in s))
            last = end
        self.rows = rows


def parse_scrap(body):
    objs = []
    lines = body.split('\n')
    i = 0
    text = []
    while i < len(lines):
        l = lines[i]
        s = l.strip()
        if s.startswith('line ') or s.startswith('area '):
            if text:
                objs.append(Obj('text', raw='\n'.join(text)))
                text = []
            kind = s.split()[0]
            end = 'endline' if kind == 'line' else 'endarea'
            rows = []
            i += 1
            while i < len(lines) and lines[i].strip() != end:
                rows.append(lines[i])
                i += 1
            if kind == 'line' and any(r.strip().startswith('adjust') for r in rows):
                # a point adjusted to line up (a pool's level surface): left as drawn
                objs.append(Obj('text', raw='\n'.join([l] + rows + [lines[i] if i < len(lines) else end])))
            else:
                objs.append(Obj(kind, s, rows))
        elif s.startswith('point '):
            if text:
                objs.append(Obj('text', raw='\n'.join(text)))
                text = []
            objs.append(Obj('point', s))
        else:
            text.append(l)
        i += 1
    if text:
        objs.append(Obj('text', raw='\n'.join(text)))
    return objs


def bezier_points(segs, n=8):
    """A line's rows as a dense polyline."""
    pts = []
    for s in segs:
        if len(s) == 2 or not pts:
            pts.append((s[-2], s[-1]))
            continue
        p0 = pts[-1]
        c1, c2, p3 = (s[0], s[1]), (s[2], s[3]), (s[4], s[5])
        for k in range(1, n + 1):
            t = k / n
            u = 1 - t
            pts.append((u ** 3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p3[0],
                        u ** 3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p3[1]))
    return pts


def reverse_segments(segs):
    """The same line drawn the other way."""
    if not segs:
        return segs
    ends = [(s[-2], s[-1]) for s in segs]
    out = [[ends[-1][0], ends[-1][1]]]
    for i in range(len(segs) - 1, 0, -1):
        s = segs[i]
        e = ends[i - 1]
        if len(s) == 6:
            out.append([s[2], s[3], s[0], s[1], e[0], e[1]])
        else:
            out.append([e[0], e[1]])
    return out


def _cross(a, b, c, d):
    """Where segment ab properly crosses segment cd, or None."""
    rx, ry = b[0] - a[0], b[1] - a[1]
    sx, sy = d[0] - c[0], d[1] - c[1]
    den = rx * sy - ry * sx
    if abs(den) < 1e-12:
        return None
    t = ((c[0] - a[0]) * sy - (c[1] - a[1]) * sx) / den
    u = ((c[0] - a[0]) * ry - (c[1] - a[1]) * rx) / den
    if 0 <= t <= 1 and 0 <= u <= 1:
        return (a[0] + t * rx, a[1] + t * ry)
    return None


def remove_loops(pts):
    """A polyline with its little self-crossing loops cut out."""
    pts = list(pts)
    closed = len(pts) > 2 and pts[0] == pts[-1]
    i = 0
    while i < len(pts) - 1:
        a, b = pts[i], pts[i + 1]
        x0, x1 = min(a[0], b[0]), max(a[0], b[0])
        y0, y1 = min(a[1], b[1]), max(a[1], b[1])
        hit = None
        for j in range(i + 2, len(pts) - 1):
            if closed and i == 0 and j == len(pts) - 2:
                continue
            c, d = pts[j], pts[j + 1]
            if max(c[0], d[0]) < x0 or min(c[0], d[0]) > x1 or max(c[1], d[1]) < y0 or min(c[1], d[1]) > y1:
                continue
            q = _cross(a, b, c, d)
            if q is not None:
                hit = (j, q)
                break
        if hit:
            j, q = hit
            pts = pts[:i + 1] + [q] + pts[j + 1:]
        else:
            i += 1
    return pts


def smooth_segments(pts):
    """Bezier rows through the points (Catmull-Rom)."""
    out = [[pts[0][0], pts[0][1]]]
    for i in range(len(pts) - 1):
        p0 = pts[max(0, i - 1)]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[min(len(pts) - 1, i + 2)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        out.append([c1[0], c1[1], c2[0], c2[1], p2[0], p2[1]])
    return out


def opt_remove(head, opt):
    return re.sub(r'\s+' + re.escape(opt) + r'(?=\s|$)', '', head)


def dense(segs, n=8):
    """A line's rows as a dense polyline, with the index in it of each row's end."""
    pts, idx = [], []
    for s in segs:
        if len(s) == 6 and pts:
            p0 = pts[-1]
            c1, c2, p3 = (s[0], s[1]), (s[2], s[3]), (s[4], s[5])
            for k in range(1, n):
                t = k / n
                u = 1 - t
                pts.append((u ** 3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p3[0],
                            u ** 3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p3[1]))
        pts.append((s[-2], s[-1]))
        idx.append(len(pts) - 1)
    return pts, idx


def clean_segments(segs, K):
    """Rows without repeated points, and with any little loops cut out."""
    out = []
    for s in segs:
        if out and abs(s[-2] - out[-1][-2]) < 0.005 and abs(s[-1] - out[-1][-1]) < 0.005:
            continue
        out.append(list(s))
    if out:
        out[0] = out[0][-2:]
    pts = bezier_points(out)
    if len(pts) > 2 and not LineString(pts).is_simple:
        pts = remove_loops(pts)
        pts = list(LineString(pts).simplify(0.02 * K).coords)
        out = smooth_segments(pts)
        if not LineString(bezier_points(out)).is_simple:
            out = [[x, y] for x, y in remove_loops(bezier_points(out))]
    return out


def _split_row(p0, row, u):
    """Split one row (straight or Bezier, starting at p0) at parameter u:
    (first part, second part)."""
    if len(row) == 2:
        q = [p0[0] + (row[0] - p0[0]) * u, p0[1] + (row[1] - p0[1]) * u]
        return q, list(row)
    P = [p0, row[0:2], row[2:4], row[4:6]]
    lerp = lambda a, b: [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u]
    a, b, c = lerp(P[0], P[1]), lerp(P[1], P[2]), lerp(P[2], P[3])
    d, e = lerp(a, b), lerp(b, c)
    f = lerp(d, e)
    return a + d + f, e + c + list(P[3])


def _where(w, t):
    """(row, parameter in the row) at distance t along a wall."""
    pts, idx, cum = w['pts'], w['idx'], w['cum']
    t = max(0.0, min(cum[-1], t))
    k = max(0, min(len(cum) - 2, bisect.bisect_right(cum, t) - 1))
    frac = (t - cum[k]) / ((cum[k + 1] - cum[k]) or 1)
    r = bisect.bisect_left(idx, k + 1)
    first = idx[r - 1]
    n = idx[r] - first
    return r, ((k - first) + frac) / n


def wall_piece(w, t0, t1):
    """The part of a wall from distance t0 to t1 along it (t0 < t1), as rows,
    cut exactly out of its curves."""
    segs = w['segs']
    r0, u0 = _where(w, t0)
    r1, u1 = _where(w, t1)
    end = lambda r: segs[r][-2:]
    if r0 == r1:
        left, _ = _split_row(end(r0 - 1), segs[r0], u1)
        q, right = _split_row(end(r0 - 1), left, u0 / u1 if u1 else 0)
        return [q[-2:], right]
    first, second = _split_row(end(r0 - 1), segs[r0], u0)
    out = [first[-2:], second]
    out += [list(s) for s in segs[r0 + 1:r1]]
    last, _ = _split_row(end(r1 - 1), segs[r1], u1)
    out.append(last)
    return out


def overshoot(a, b, d):
    """The line from a to b, carried on a little past b so that it
    certainly crosses whatever b is on."""
    L = a.distance(b) or 1
    return LineString([a, (b.x + (b.x - a.x) / L * d, b.y + (b.y - a.y) / L * d)])


def _inside_rules():
    """The Cheddar Catchment rules for walls inside the passage fill
    ([convert] interior_borders) rather than upstream's."""
    from .settings import SETTINGS
    return SETTINGS['interior_borders']


def rebuild_outline(objs, ring_obj, K, name=''):
    """Make the walls the scrap's outline, in place of the converter's closed
    invisible fill line (ring_obj).

    The fill line runs round the walls a little way off them. The thin
    sliver between each wall and the fill line beside it (with no survey
    station in it) is cut away, and the thin lens where a wall runs just
    outside the fill line is taken in, so that the fill reaches the walls
    exactly. Going round it anticlockwise, every stretch along a wall
    becomes that part of the wall, drawn with the passage on its left;
    close_outline() then deals with the gaps between them. Walls that end up inside the passage
    are the edges of other things (a ledge, another level): borders.
    Returns (objs, outline polygon)."""
    rp = Polygon(bezier_points(ring_obj.segments())).buffer(0)
    if rp.geom_type != 'Polygon':
        rp = max(rp.geoms, key=lambda g: g.area)
    walls = []
    for o in objs:
        if o.kind == 'line' and o.head.startswith('line wall') and '-outline none' in o.head \
                and '-close on' not in o.head:
            segs = clean_segments(o.segments(), K)
            if len(segs) < 2:
                continue
            pts, idx = dense(segs)
            line = LineString(pts)
            if line.length < 0.05 * K:
                continue
            cum = [0.0]
            for p, q in zip(pts, pts[1:]):
                cum.append(cum[-1] + math.dist(p, q))
            walls.append({'obj': o, 'segs': segs, 'pts': pts, 'idx': idx, 'line': line, 'cum': cum})
    # walls (almost) all inside the fill take no part in the outline: one
    # touching it only at an end would pull the outline in to that end
    def on_ring(w):
        return sum(1 for p in w['pts'] if rp.exterior.distance(Point(p)) < 0.1 * K) / len(w['pts'])
    inner_walls = [w for w in walls if _inside_rules() and on_ring(w) < 0.2]
    walls = [w for w in walls if not _inside_rules() or on_ring(w) >= 0.2]
    stations = [Point(float(o.head.split()[1]), float(o.head.split()[2])) for o in objs
                if o.kind == 'point' and re.match(r'point \S+ \S+ station\b', o.head)]
    REPORT_ROW = [name, 0.0, sum(w['line'].length for w in walls)]
    if not walls:
        REPORT.append(tuple(REPORT_ROW))
        return objs, rp
    all_walls = unary_union([w['line'] for w in walls])

    # Between each wall and the stretch of fill line beside it there's a
    # sliver: cut it away if it's thin and has no survey station in it,
    # and take in the thin lens where a wall runs just outside the fill line.
    ring = rp.exterior
    L = ring.length
    cuts, adds = [], []

    def keep_outer(w, g):
        # where another wall runs through the sliver, that wall is the outer
        # one (a wall drawn again a little further out): the sliver is not
        # cut there, so the outline goes on along the outer wall
        core = g.buffer(-0.02 * K)
        outer = [v['line'] for v in walls if v is not w and v['line'].intersection(core).length > 0.3 * K]
        return g.difference(unary_union(outer).buffer(0.3 * K)) if outer else g

    for w in walls:
        ta, tb = ring.project(Point(w['pts'][0])), ring.project(Point(w['pts'][-1]))
        lo, hi = min(ta, tb), max(ta, tb)
        arcs = [substring(ring, lo, hi)]
        if lo > 0 or hi < L:
            arcs.append(LineString(list(substring(ring, hi, L).coords) + list(substring(ring, 0, lo).coords)[1:]))
        arc = min(arcs, key=lambda g: abs(g.length - w['line'].length))
        ac = list(arc.coords)
        if math.dist(ac[0], w['pts'][-1]) > math.dist(ac[-1], w['pts'][-1]):
            ac = ac[::-1]           # round from the wall's end back to its start
        try:
            sliver = Polygon(list(w['pts']) + ac).buffer(0)
            if sliver.is_empty:
                continue
            inner = sliver.intersection(rp)
            outer = sliver.difference(rp)
        except Exception:           # degenerate geometry: leave this wall as it is
            continue
        # thin on average and everywhere: a long wall mostly on the fill
        # line can have a stretch inside the passage, and that is not a sliver
        if not inner.is_empty and inner.area / w['line'].length < 1.2 * K \
                and (not _inside_rules() or inner.buffer(-0.6 * K).is_empty) \
                and not any(inner.contains(st) and w['line'].distance(st) > 0.15 * K for st in stations):
            cuts.append(keep_outer(w, inner) if _inside_rules() else inner)
        if not outer.is_empty and outer.area / w['line'].length < 0.4 * K \
                and (not _inside_rules() or outer.buffer(-0.2 * K).is_empty):
            adds.append(outer)
    F = unary_union([rp] + adds).difference(unary_union(cuts).buffer(0.001 * K)) if cuts else unary_union([rp] + adds)
    # strips thinner than a few centimetres left along a wall go too, but not
    # a thin neck joining on another part of the passage
    if F.geom_type != 'Polygon' and not F.is_empty:
        F = max(F.geoms, key=lambda g: g.area)
    def build(r):
        """The outline, after taking away strips thinner than 2r metres."""
        F = F0.buffer(-r * K, join_style=2).buffer(r * K, join_style=2).intersection(F0)
        parts = sorted(getattr(F, 'geoms', [F]), key=lambda g: -g.area)
        if len(parts) > 1:
            cut_off = F0.difference(F).buffer(0)
            bits = list(getattr(cut_off, 'geoms', [cut_off]))
            F = parts[0]
            others = [p for p in parts[1:] if p.area > (0.3 * K) ** 2]
            grew = True
            while grew and others:
                grew = False
                for p in list(others):
                    necks = [b for b in bits if b.distance(F) < 0.01 * K and b.distance(p) < 0.01 * K]
                    if necks:
                        F = unary_union([F, p] + necks).buffer(0)
                        others.remove(p)
                        grew = True
        if F.is_empty:
            return None, 'nothing left'
        if F.geom_type != 'Polygon':
            F = max(F.geoms, key=lambda g: g.area)
        F = Polygon(F.exterior)
        coords = list(F.exterior.coords)[:-1]
        if not F.exterior.is_ccw:
            coords = coords[::-1]
        n = len(coords)

        # which wall each edge of the outline lies along
        lab = []
        for i in range(n):
            a, b = coords[i], coords[(i + 1) % n]
            m = Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            best = None
            for k, w in enumerate(walls):
                d = w['line'].distance(m)
                if d < 0.02 * K and (best is None or d < best[0]):
                    best = (d, k)
            lab.append(best[1] if best else None)
        if all(x is None for x in lab):
            return None, 'no wall on the outline'
        # start where a wall begins, and group the edges into runs
        start = next(i for i in range(n) if lab[i] is not None and lab[i - 1] != lab[i])
        runs = []
        for k in range(n):
            i = (start + k) % n
            if runs and runs[-1][0] == lab[i]:
                runs[-1][1].append(coords[(i + 1) % n])
            else:
                runs.append([lab[i], [coords[i], coords[(i + 1) % n]]])

        # the wall stretches: whole rows of the wall, the right way round
        pieces = []         # ('wall', k, segs) or ('gap', points)
        used = {k: [] for k in range(len(walls))}
        for k, ps in runs:
            if k is None:
                pieces.append(['gap', ps])
                continue
            w = walls[k]
            t0, t1 = w['line'].project(Point(ps[0])), w['line'].project(Point(ps[-1]))
            if abs(t1 - t0) < 0.02 * K:
                pieces.append(['gap', ps])
                continue
            segs = wall_piece(w, min(t0, t1), max(t0, t1))
            if t0 > t1:
                segs = reverse_segments(segs)
            # end exactly where the outline leaves the wall (the cut is only
            # as exact as the polyline the distances were measured on)
            segs[0] = [ps[0][0], ps[0][1]]
            segs[-1] = list(segs[-1][:-2]) + [ps[-1][0], ps[-1][1]]
            pieces.append(['wall', k, segs, ps, (min(t0, t1), max(t0, t1))])
        def assemble(pieces):
            # join the gaps up to the wall ends, merging neighbouring gaps
            merged = []
            for p in pieces:
                if merged and p[0] == 'gap' and merged[-1][0] == 'gap':
                    merged[-1][1] += p[1][1:]
                else:
                    merged.append(p)
            if len(merged) > 1 and merged[0][0] == 'gap' and merged[-1][0] == 'gap':
                merged[-1][1] += merged[0][1][1:]
                merged = merged[1:]
            m = len(merged)
            out_lines = []
            for i, p in enumerate(merged):
                if p[0] == 'wall':
                    out_lines.append(('wall', p[2]))
                    nxt = merged[(i + 1) % m]
                    if nxt[0] == 'wall':
                        a, b = p[2][-1][-2:], nxt[2][0][-2:]
                        if math.dist(a, b) > 0.005:
                            out_lines.append(('gap', [a, b]))
                else:
                    prv, nxt = merged[i - 1], merged[(i + 1) % m]
                    ps = list(p[1])
                    if prv[0] == 'wall':
                        ps[0] = tuple(prv[2][-1][-2:])
                    if nxt[0] == 'wall':
                        ps[-1] = tuple(nxt[2][0][-2:])
                    if len(ps) > 2:
                        ps = list(LineString(ps).simplify(0.03 * K).coords)
                    out_lines.append(('gap', ps))

            # check it: one simple closed outline, much the same as the faces
            ring_pts = []
            for kind, g in out_lines:
                pts = bezier_points(g, 20) if kind == 'wall' else [tuple(q) for q in g]
                ring_pts += pts if not ring_pts else pts[1:]
            test = Polygon(ring_pts)
            if len(ring_pts) < 4 or not test.is_valid or abs(test.area - F.area) > 0.1 * F.area:
                return None, test
            return out_lines, None

        # a wall piece the outline can't follow cleanly (a hairpin, say)
        # becomes invisible outline there instead, and stays drawn as wall
        for attempt in range(12):
            out_lines, bad = assemble(pieces)
            if out_lines:
                break
            from shapely.validation import explain_validity
            why = explain_validity(bad)
            m = re.search(r'\[([-\d.e]+) ([-\d.e]+)\]', why)
            if not m:
                return None, why
            q = Point(float(m.group(1)), float(m.group(2)))
            hit = [i for i, p in enumerate(pieces) if p[0] == 'wall'
                   and LineString(bezier_points(p[2], 20)).distance(q) < 0.1 * K]
            if not hit:
                return None, why
            for i in hit:
                pieces[i] = ['gap', pieces[i][3]]
        else:
            return None, why
        used = {k: [] for k in range(len(walls))}
        for p in pieces:
            if p[0] == 'wall':
                used[p[1]].append(p[4])
        return (F, out_lines, used), ''

    # a wall doubling back on itself in a hairpin can tangle the outline:
    # then try again without such thin bits
    F0 = F
    for r in (0.08, 0.2, 0.4):
        got, why = build(r)
        if got:
            break
    if not got:
        REPORT.append((name, 0.0, REPORT_ROW[2], why))
        return objs, rp
    F, out_lines, used = got

    # write it
    new = []
    for kind, g in out_lines:
        o = Obj('line', 'line wall' if kind == 'wall' else 'line wall -subtype invisible', [])
        o.set_segments(g if kind == 'wall' else [[x, y] for x, y in g])
        if len(o.rows) >= 2:
            new.append(o)
    kept_len = 0.0
    replace = {}
    for k, w in enumerate(walls):
        spans = sorted(used[k])
        kept_len += sum(hi - lo for lo, hi in spans)
        rest, pos = [], 0.0
        for lo, hi in spans:
            if lo - pos > 0.02 * K:
                rest.append((pos, lo))
            pos = max(pos, hi)
        if w['cum'][-1] - pos > 0.02 * K:
            rest.append((pos, w['cum'][-1]))
        extra = []
        for lo, hi in rest:
            piece = wall_piece(w, lo, hi)
            o = Obj('line', 'line wall -outline none', [])
            if not spans:
                # a wall that isn't on the outline at all: inside the passage
                # it's the edge of something (a ledge, another level)
                mid = w['line'].interpolate(0.5, normalized=True)
                if F.buffer(-0.1 * K).contains(mid):
                    o.head = inner_wall_head()
            o.set_segments(piece)
            if len(o.rows) >= 2:
                extra.append(o)
        replace[id(w['obj'])] = extra
    # an inside wall drawn on from the end of one on the outline (the same
    # stroke) stays wall; any other is the edge of something: a border
    ends = [p for w in walls for p in (w['pts'][0], w['pts'][-1])]
    for w in inner_walls:
        if not any(math.dist(q, p) < 0.05 * K for q in (w['pts'][0], w['pts'][-1]) for p in ends) \
                and F.buffer(-0.1 * K).contains(w['line'].interpolate(0.5, normalized=True)):
            w['obj'].head = inner_wall_head()
    res = []
    for o in objs:
        if o is ring_obj:
            res += new
        elif id(o) in replace:
            res += replace[id(o)]
        else:
            res.append(o)
    close_outline(res, K)
    res = [o for o in res if o.kind != 'drop']
    REPORT.append((name, kept_len, REPORT_ROW[2]))
    return res, F


def water_to_walls(pool, objs, K):
    """A pool out to the walls it lies against, and a little past them:
    Therion clips the area to the scrap outline, so the wall is the
    water's edge and there is no second line just inside it."""
    walls = [LineString(bezier_points(o.segments())) for o in objs
             if o.kind == 'line' and o.head.startswith('line wall') and '-outline none' not in o.head
             and len(o.segments()) > 1]
    if not walls:
        return pool
    reach = pool.buffer(0.35 * K, join_style=1).intersection(unary_union(walls).buffer(0.3 * K))
    g = unary_union([pool, reach]).buffer(0.05 * K, join_style=1).buffer(-0.05 * K, join_style=1)
    if g.geom_type != 'Polygon':
        g = max(g.geoms, key=lambda q: q.area)
    return g.simplify(0.02 * K)


def edge_fixes(objs, K, map_scale=500):
    """Slope arrows out of the water (and still inside the walls, off steps
    and pitches), and boulders at the edge of the passage drawn out over
    the wall, which clips them. Returns (arrows moved, arrows dropped,
    boulders extended)."""
    walls = [o for o in objs if o.kind == 'line' and o.head.startswith('line wall')
             and '-outline none' not in o.head and len(o.segments()) > 1]
    rings = therion_chain([bezier_points(o.segments(), 20) for o in walls])
    inside = Polygon(rings[0]).buffer(0) if len(rings) == 1 else None
    pools = []
    for o in objs:
        if o.kind == 'line' and o.head.startswith('line border') and '-id' in o.head and '-close on' in o.head:
            g = Polygon([(s[-2], s[-1]) for s in o.segments()]).buffer(0)
            if not g.is_empty:
                pools.append(g)
    water = unary_union(pools) if pools else None
    if inside is not None and water is not None:
        water = water.intersection(inside)
    steps = [LineString(bezier_points(o.segments())) for o in objs
             if o.kind == 'line' and re.match(r'line (floor-step|pit|ceiling-step|wall)\b', o.head)
             and len(o.segments()) > 1 and '-subtype invisible' not in o.head]
    half = 0.004 * map_scale * K / 2
    moved = dropped = extended = 0
    for o in objs:
        if o.kind != 'point' or not re.match(r'point \S+ \S+ gradient\b', o.head):
            continue
        v = o.head.split()
        x, y = float(v[1]), float(v[2])
        m = re.search(r'-orientation ([-\d.]+)', o.head)
        brg = math.radians(float(m.group(1))) if m else 0
        ux, uy = math.sin(brg), math.cos(brg)

        def clear(px, py):
            seg = LineString([(px - ux * half, py - uy * half), (px + ux * half, py + uy * half)])
            if inside is not None and not inside.contains(seg):
                return False
            if water is not None and seg.buffer(0.1 * K).intersects(water):
                return False
            return not any(seg.intersects(st) for st in steps)
        if water is None or not Point(x, y).buffer(half).intersects(water):
            continue
        spot = None
        for d in (0.5, 1.0, 1.5, 2.0, 3.0):
            for k in range(12):
                a = k * math.pi / 6
                q = (x + math.cos(a) * d * K, y + math.sin(a) * d * K)
                if clear(*q):
                    spot = q
                    break
            if spot:
                break
        if spot is None:
            o.kind = 'drop'
            dropped += 1
        else:
            o.head = re.sub(r'^point [-\d.]+ [-\d.]+', 'point %.2f %.2f' % spot, o.head)
            moved += 1
    if walls:
        wall_lines = unary_union([LineString(bezier_points(o.segments())) for o in walls])
        for o in objs:
            if not (o.kind == 'line' and o.head.startswith('line rock-border') and '-close on' in o.head):
                continue
            pts = bezier_points(o.segments())
            if len(pts) < 4:
                continue
            g = Polygon(pts).buffer(0)
            if g.is_empty or g.geom_type != 'Polygon' or g.distance(wall_lines) > 0.3 * K:
                continue
            from .settings import SETTINGS
            r = SETTINGS['boulder_over_wall']
            reach = g.buffer(r * K, join_style=2).intersection(wall_lines.buffer(min(0.25, r) * K))
            h = unary_union([g, reach]).buffer(0)
            if h.geom_type != 'Polygon':
                continue
            corners = list(h.exterior.simplify(0.06 * K).coords)
            o.set_segments([[a, b] for a, b in corners])
            extended += 1
    return moved, dropped, extended


# -- closing the outline the way Therion does --------------------------------------

def _station_legs(objs):
    """Survey legs between the scrap's stations, guessed from their names:
    24.31 to 24.32 and so on (PocketTopo and SexyTopo number along the survey)."""
    st = {}
    for o in objs:
        m = re.match(r'point (\S+) (\S+) station\b.*-name (\S+)', o.head) if o.kind == 'point' else None
        if m:
            st[m.group(3).split('@')[0]] = (float(m.group(1)), float(m.group(2)))
    legs = []
    for n, p in st.items():
        a, _, b = n.rpartition('.')
        if a and b.isdigit():
            q = st.get(f'{a}.{int(b) + 1}')
            if q:
                legs.append(LineString([p, q]))
    return legs


def therion_rings(lines):
    """Join outline lines into closed outlines as Therion does
    (thscrap::get_outline): the lines in order of the distance between
    their ends, longest first; each outline starts from the first line not
    yet used, and goes on to the line with an end at its end, else to the
    nearest end that no other line shares, else to the nearest end, as long
    as that is nearer than the outline's own start.
    [[(index into lines, reversed)]]"""
    order = sorted([i for i, l in enumerate(lines) if len(l) > 1],
                   key=lambda i: -math.dist(lines[i][0], lines[i][-1]))
    ends = [lines[i][k] for i in order for k in (0, -1)]
    free = {i: [lines[i][0] != lines[i][-1] and ends.count(lines[i][0]) == 1,
                lines[i][0] != lines[i][-1] and ends.count(lines[i][-1]) == 1] for i in order}
    used = set()
    out = []
    for n, i in enumerate(order):
        if i in used:
            continue
        used.add(i)
        ring = [(i, False)]
        start, last = lines[i][0], lines[i][-1]
        while start != last or len(ring) > 1:     # a closed line is an outline on its own
            best = None
            for search_all in (False, True):
                mind = math.dist(last, start)
                for j in order[n + 1:]:
                    if j in used:
                        continue
                    m = lines[j]
                    # Therion's order of tests, later ones winning ties
                    if m[-1] == last:
                        best, mind = (j, True), 0.0
                    if search_all or free[j][1]:
                        d = math.dist(m[-1], last)
                        if d <= mind:
                            best, mind = (j, True), d
                    if m[0] == last:
                        best, mind = (j, False), 0.0
                    if search_all or free[j][0]:
                        d = math.dist(m[0], last)
                        if d <= mind:
                            best, mind = (j, False), d
                if best is not None:
                    break
            if best is None:
                break
            used.add(best[0])
            ring.append(best)
            last = lines[best[0]][0] if best[1] else lines[best[0]][-1]
        out.append(ring)
    return out


def therion_chain(lines):
    """The closed outlines Therion makes of the outline lines (see
    therion_rings), each as one list of points. [[points]]"""
    lines = [list(l) for l in lines]
    out = []
    for ring in therion_rings(lines):
        pts = []
        for i, rev in ring:
            pts += lines[i][::-1] if rev else lines[i]
        out.append(pts)
    return out


def outline_sound(rings, lines=()):
    """What Therion and MetaPost need of a joined-up outline: one ring that
    doesn't cross itself and turns once round, and, where one line joins
    the next, no point visited twice and no cusp (a turn straight back,
    where MetaPost loses count)."""
    if len(rings) != 1:
        return False
    pts = [rings[0][0]]
    for q in rings[0][1:]:
        if math.dist(q, pts[-1]) > 1e-3:
            pts.append(q)
    if len(pts) > 1 and math.dist(pts[0], pts[-1]) < 1e-3:
        pts.pop()
    if len(pts) < 3 or not Polygon(pts).is_valid:
        return False
    ends = {(round(l[i][0], 2), round(l[i][1], 2)) for l in lines for i in (0, -1)}
    seen = {}
    turn = 0.0
    for i in range(len(pts)):
        a, b, c = pts[i - 2], pts[i - 1], pts[i]
        t = math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(b[1] - a[1], b[0] - a[0])
        t = (t + math.pi) % (2 * math.pi) - math.pi
        turn += t
        key = (round(b[0], 2), round(b[1], 2))
        if key in ends:
            if abs(t) > math.radians(170):
                return False
            seen[key] = seen.get(key, 0) + 1
    if any(v > 1 for v in seen.values()):
        return False
    return abs(abs(turn) - 2 * math.pi) < 0.5


def close_outline(objs, K):
    """Leave the gaps between walls open: Therion closes the outline itself,
    joining each wall's end to the nearest free end of another. Where its
    joining would go wrong without one (jumping across the passage, or
    closing the outline early), a short gap is bridged by carrying the
    wall on across it, and a longer one becomes a presumed wall.
    Returns (presumed, left open, needed)."""
    gaps = [o for o in objs if o.kind == 'line' and o.head.startswith('line wall')
            and '-subtype invisible' in o.head and '-close on' not in o.head]
    if not gaps:
        return 0, 0, 0
    presumed, opened = [], list(gaps)

    def outline_ok(skip):
        lines = [bezier_points(o.segments(), 20) for o in objs
                 if o.kind == 'line' and o.head.startswith('line wall') and '-outline none' not in o.head
                 and '-close on' not in o.head and o not in skip and len(o.segments()) > 1]
        return outline_sound(therion_chain(lines), lines)
    # leave each gap open where Therion's own joining then still makes
    # one clean outline; otherwise it has to stay
    skip, kept = set(), []
    for o in sorted(opened, key=lambda o: -LineString(bezier_points(o.segments())).length):
        skip.add(o)
        if not outline_ok(skip):
            skip.discard(o)
            kept.append(o)
    for o in skip:
        o.kind = 'drop'
    # the rest: a short one joins the walls either side (the wall it
    # carries on from is extended across it), a longer one is presumed wall
    walls = [w for w in objs if w.kind == 'line' and w.head.startswith('line wall') and w not in kept
             and '-subtype invisible' not in w.head and '-outline none' not in w.head and len(w.segments()) > 1]
    for o in kept:
        segs = o.segments()
        pts = [tuple(sg[-2:]) for sg in segs]
        if LineString(bezier_points(segs)).length < 0.5 * K:
            w = next((w for w in walls if math.dist(tuple(w.segments()[-1][-2:]), pts[0]) < 0.01), None)
            if w is not None:
                w.set_segments(w.segments() + [[x, y] for x, y in pts[1:]])
                o.kind = 'drop'
                continue
            w = next((w for w in walls if math.dist(tuple(w.segments()[0][-2:]), pts[-1]) < 0.01), None)
            if w is not None:
                w.set_segments([[x, y] for x, y in pts[:-1]] + [[w.segments()[0][-2], w.segments()[0][-1]]] + w.segments()[1:])
                o.kind = 'drop'
                continue
        from .settings import SETTINGS
        if SETTINGS['presumed_walls']:
            o.head = 'line wall -subtype presumed'
        else:                           # nothing was sketched there: leave it open (Therion closes it)
            o.kind = 'drop'
    return len(presumed), len(skip), len(kept)


# -- the tidy itself -----------------------------------------------------------------

def scale_of(header):
    """Drawing units per metre, from the scrap's -scale."""
    m = re.search(r'-scale \[([-\d.]+) [-\d.]+ ([-\d.]+) [-\d.]+ ([-\d.]+) [-\d.]+ ([-\d.]+) [-\d.]+ m\]', header)
    if not m:
        return 39.37
    x1, x2, X1, X2 = map(float, m.groups())
    return (x2 - x1) / (X2 - X1) if X2 != X1 else 39.37


def tidy_scrap(header, body, map_scale=500, elevation=False):
    K = scale_of(header)
    objs = parse_scrap(body)
    ring_obj = next((o for o in objs if o.kind == 'line' and o.head.startswith('line wall')
                     and '-subtype invisible' in o.head and '-close on' in o.head), None)
    outline_poly = None

    # 1. walls and outline
    if ring_obj is not None:
        objs, outline_poly = rebuild_outline(objs, ring_obj, K, header.split()[1])
    else:
        # a cross-section: its closed wall is the outline
        cw = next((o for o in objs if o.kind == 'line' and o.head.startswith('line wall') and '-close on' in o.head), None)
        if cw:
            pts = bezier_points(cw.segments())
            if len(pts) > 3 and not LineString(pts).is_simple:
                pts = remove_loops(pts)
                if math.dist(pts[0], pts[-1]) < 1e-6:
                    pts = pts[:-1]
                pts = list(LineString(pts).simplify(0.01 * K).coords)
                segs = smooth_segments(pts + [pts[0]])
                if LineString(bezier_points(segs)).is_simple:
                    cw.set_segments(segs)
                else:
                    cw.set_segments([[x, y] for x, y in pts + [pts[0]]])
                pts = bezier_points(cw.segments())
            outline_poly = Polygon(pts).buffer(0)

    # 2. no -clip off; water with an invisible border, out to the walls it lies against
    drop_ids = set()
    from .settings import SETTINGS
    water_ids = {r.strip() for o in objs if o.kind == 'area' and o.head.split()[:2] == ['area', 'water']
                 for r in o.rows if r.strip()}
    for o in objs:
        if o.kind in ('line', 'area'):
            o.head = opt_remove(o.head, '-clip off')
        if o.kind == 'line' and o.head.startswith('line border') and '-id' in o.head and '-close on' in o.head \
                and re.search(r'-id (\S+)', o.head).group(1) in water_ids:
            if '-subtype invisible' not in o.head:
                o.head = o.head.replace('line border', 'line border -subtype invisible', 1)
            if outline_poly is not None and not outline_poly.is_empty:
                pool = Polygon([(s[-2], s[-1]) for s in o.segments()]).buffer(0)
                pool = pool.intersection(outline_poly.buffer(0.3 * K))
                if pool.geom_type == 'MultiPolygon':
                    pool = max(pool.geoms, key=lambda g: g.area)
                if pool.is_empty or pool.geom_type != 'Polygon' or pool.area < (0.15 * K) ** 2:
                    drop_ids.add(re.search(r'-id (\S+)', o.head).group(1))
                    o.kind = 'drop'
                elif SETTINGS['water_to_walls']:
                    o.set_segments([[x, y] for x, y in list(water_to_walls(pool, objs, K).exterior.coords)[:-1]])
                else:
                    o.set_segments([[x, y] for x, y in list(pool.simplify(0.02 * K).exterior.coords)[:-1]])
    for o in objs:
        if o.kind == 'area' and any(r.strip() in drop_ids for r in o.rows):
            o.kind = 'drop'

    # 3. points: drop marks outside the walls, keep slope arrows off steps
    steps = [LineString(bezier_points(o.segments())) for o in objs
             if o.kind == 'line' and re.match(r'line (floor-step|pit|ceiling-step|wall)\b', o.head)
             and len(o.segments()) > 1 and '-subtype invisible' not in o.head]
    arrow_half = 0.004 * map_scale * K / 2       # a slope arrow is about 4 mm long on the page
    for o in objs:
        if o.kind != 'point':
            continue
        v = o.head.split()
        try:
            x, y = float(v[1]), float(v[2])
        except (IndexError, ValueError):
            continue
        typ = v[3] if len(v) > 3 else ''
        # in an elevation water flow is drawn just under the floor (elevation.py)
        under = 0.6 if typ == 'water-flow' and inner_wall_head() != 'line border' else 0.1
        if outline_poly is not None and typ in ('water-flow', 'flowstone', 'stalagmite', 'stalactite', 'gradient') \
                and not outline_poly.buffer(under * K).contains(Point(x, y)):
            o.kind = 'drop'
            continue
        if typ == 'gradient':
            m = re.search(r'-orientation ([-\d.]+)', o.head)
            brg = math.radians(float(m.group(1))) if m else 0
            ux, uy = math.sin(brg), math.cos(brg)

            def clear(px, py):
                seg = LineString([(px - ux * arrow_half, py - uy * arrow_half), (px + ux * arrow_half, py + uy * arrow_half)])
                inside = outline_poly is None or outline_poly.contains(seg)
                return inside and not any(seg.intersects(st) for st in steps)
            if not clear(x, y):
                spot = None
                for d in (0.5, 1.0, 1.5, 2.0):
                    for sx, sy in ((ux, uy), (-ux, -uy), (-uy, ux), (uy, -ux)):
                        q = (x + sx * d * K, y + sy * d * K)
                        if clear(*q):
                            spot = q
                            break
                    if spot:
                        break
                if spot is None:
                    o.kind = 'drop'
                else:
                    o.head = re.sub(r'^point [-\d.]+ [-\d.]+', 'point %.2f %.2f' % spot, o.head)

    # 4. boulders: rock edges inside the big ones
    extra = []
    for o in objs:
        if o.kind == 'line' and o.head.startswith('line rock-border'):
            pts = bezier_points(o.segments())
            if len(pts) < 4:
                continue
            g = Polygon(pts).buffer(0)
            if g.is_empty or g.area < (1.1 * K) ** 2:
                continue
            c = g.centroid
            far = sorted(pts, key=lambda p: -math.dist(p, (c.x, c.y)))
            a = far[0]
            b = next((p for p in far[1:] if math.dist(p, a) > 0.6 * math.dist(a, (c.x, c.y)) * 1.5), far[-1])
            e = Obj('line', 'line rock-edge', [])
            e.set_segments([[a[0] * 0.85 + c.x * 0.15, a[1] * 0.85 + c.y * 0.15], [c.x, c.y],
                            [b[0] * 0.85 + c.x * 0.15, b[1] * 0.85 + c.y * 0.15]])
            extra.append((o, e))
    for o, e in extra:
        objs.insert(objs.index(o) + 1, e)

    # 5. labels: climbs and pitches without units, and every label clear of the walls
    placed = []
    if outline_poly is not None:
        keep_out = outline_poly.buffer(0.25 * K)
    for o in objs:
        if o.kind != 'point' or ' label ' not in o.head:
            continue
        m = re.search(r'-text "([^"]*)"', o.head)
        text = m.group(1) if m else ''
        cm = re.fullmatch(r'C([\d.]+)m', text)
        if cm:
            h = float(cm.group(1))
            from .settings import SETTINGS
            if SETTINGS['climb_whole']:
                h = max(1, math.floor(h + 0.5))
            text = ('P' if h >= 3 else 'C') + ('%g' % h)
            o.head = o.head.replace(m.group(0), '-text "%s"' % text)
        if outline_poly is None:
            continue
        v = o.head.split()
        x, y = float(v[1]), float(v[2])
        sc = re.search(r'-scale (\w+)', o.head)
        hmm = LABEL_MM.get(sc.group(1) if sc else 'm', 2.4)
        plain = re.sub(r'<[^>]*>', '\n', text)
        rows = [r for r in plain.split('\n') if r.strip()] or [text]
        w = max(len(r) for r in rows) * hmm * 0.55 * map_scale / 1000 * K
        h = len(rows) * hmm * 1.25 * map_scale / 1000 * K

        def ok(px, py):
            bx = box(px - w / 2, py - h / 2, px + w / 2, py + h / 2)
            return not bx.intersects(keep_out) and not any(bx.intersects(p) for p in placed)
        if not ok(x, y):
            spot = None
            # step out from the nearest edge first, then try all round
            q = outline_poly.exterior.interpolate(outline_poly.exterior.project(Point(x, y)))
            dx, dy = q.x - x, q.y - y
            dl = math.hypot(dx, dy) or 1
            dirs = [(dx / dl, dy / dl)] + [(math.cos(a), math.sin(a)) for a in [k * math.pi / 8 for k in range(16)]]
            for dist in [d * K for d in (0.5, 1, 1.5, 2, 3, 4, 5, 6, 8, 10)]:
                for ux, uy in dirs:
                    px, py = x + ux * dist, y + uy * dist
                    if ok(px, py):
                        spot = (px, py)
                        break
                if spot:
                    break
            if spot:
                x, y = spot
                o.head = re.sub(r'^point [-\d.]+ [-\d.]+', 'point %.2f %.2f' % spot, o.head)
        placed.append(box(x - w / 2, y - h / 2, x + w / 2, y + h / 2))

    objs = [o for o in objs if o.kind != 'drop']
    edge_fixes(objs, K, map_scale)
    return '\n'.join(o.text() for o in objs if o.kind != 'drop')


def is_generated(name, body):
    return ('-subtype invisible -close on' in body or name.startswith('xs') or name.endswith('XS')
            or name.endswith('XSTop'))


def tidy_text(t, map_scale=500, elevation=None):
    """Tidy every converter-made scrap in a th2 file's text."""
    t = t.replace('\r\n', '\n')
    out = []
    pos = 0
    for m in re.finditer(r'^(scrap (\S+)[^\n]*)\n(.*?)^endscrap', t, re.S | re.M):
        header, name, body = m.group(1), m.group(2), m.group(3)
        out.append(t[pos:m.start()])
        if is_generated(name, body):
            el = ('-projection extended' in header) if elevation is None else elevation
            body = tidy_scrap(header, body, map_scale, el).rstrip('\n') + '\n'
        out.append(header + '\n' + body + 'endscrap')
        pos = m.end()
    out.append(t[pos:])
    t = ''.join(out)
    if LICENCE not in t:
        t = t.replace('encoding  utf-8\n', 'encoding  utf-8\n' + LICENCE + '\n', 1)
    return t


def tidy_file(path, map_scale=500):
    raw = open(path, 'rb').read()
    crlf = b'\r\n' in raw
    t = tidy_text(raw.decode('utf-8'), map_scale)
    if crlf:
        t = t.replace('\n', '\r\n')
    open(path, 'wb').write(t.encode('utf-8'))
