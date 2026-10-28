# Part of tools/sketch2therion (new for the Cheddar Catchment survey). GPLv3: see LICENSE.
"""Outlines as Therion joins them, and which way round their walls go.

Plain Python (no shapely), so th2lint can use it too."""
import math


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


def wrong_way(lines, inner=()):
    """Indices of the lines that go round their outline with the passage
    on their right (Style.md, hard rule 6, in every projection). lines:
    point lists as Therion takes them (after -reverse on); inner: indices
    of -outline in lines, whose passage is outside them, as it is outside
    an outline lying inside another (a pillar without -outline in).
    Outlines that enclose nothing are left out."""
    rings = []
    for outer in (True, False):
        group = [i for i in range(len(lines)) if (i in inner) != outer]
        sub = [lines[i] for i in group]
        for ring in therion_rings(sub):
            pts = [p for k, rev in ring for p in (sub[k][::-1] if rev else sub[k])]
            area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))
            if abs(area) >= 1e-9:
                rings.append((outer, area, pts, [(group[k], rev) for k, rev in ring]))
    out = []
    for outer, area, pts, ring in rings:
        if outer and any(q is not pts and _inside(pts, q) for _, _, q, _ in rings):
            outer = False
        out += [i for i, rev in ring if ((area > 0) != rev) != outer]
    return sorted(out)


def _inside(pts, ring):
    """Whether most of pts lie inside the closed ring (even-odd rule)."""
    def within(p):
        x, y, n = p[0], p[1], False
        for a, b in zip(ring, ring[1:] + ring[:1]):
            if (a[1] > y) != (b[1] > y) and x < a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]):
                n = not n
        return n
    return sum(map(within, pts)) > 0.8 * len(pts)
