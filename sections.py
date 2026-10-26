# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""Cross sections on the assembled plan: section lines evenly across their
passage, and section drawings clear of the passages and of each other.

    python3 -m tools.sketch2therion sections [X ...] [--write]

Every plan scrap is put in the cave's coordinates (Therion's plan layout,
output/layout-plan.xvi) by fitting it to its stations, as `joins` does,
so passages of other surveys are seen too (Style.md, Cross sections):

- a `line section` is redrawn across its own passage, through the same
  middle and at the same angle, ending MARGIN past the wall on each side.
  Where an end's arrow (drawn on the line's left) would land in another
  passage, that end comes in, down to MIN_MARGIN; if that is not enough
  the arrow on that side is left off (`-direction begin` or `end`);
- a section drawing (`-projection none` scrap) that overlaps a passage or
  another section drawing is moved along its section line, the least
  distance that clears it, by moving its `point section` only. Therion
  centres the drawing's bounding box on that point and ignores where the
  drawing itself is, which stays over its sketch in the backdrop.

Without --write it only reports. With it, each file is read again just
before it is written and only the changed objects are replaced.
"""
import argparse
import math
import os
import re

from shapely.geometry import LineString, MultiPoint, Point
from shapely.ops import unary_union

from . import project as _project
from . import register
from .joins import Drawing, plan_file
from .tidy import bezier_points, parse_scrap

PROJECT = _project.load()
MARGIN = 0.5        # m: a section line goes this far past the wall on each side (Style.md)
MIN_MARGIN = 0.1    # m: the least it may come in to, to keep its arrow out of another passage
ARROW = 0.5         # m: how far an arrow reaches from the line's end, on its left
STEP = 0.25         # m: section drawings are moved in steps of this
REACH = 12.0        # m: the furthest a section drawing is moved
CLEAR = 0.2         # m: room kept round a section drawing


def _inverse(f):
    o = complex(*f((0, 0)))
    a = complex(*f((1, 0))) - o
    return (lambda p: (lambda z: (z.real, z.imag))((complex(*p) - o) / a)), abs(a)


def _rows(o):
    return [[float(x) for x in r.split()] for r in o.rows
            if re.match(r'^\s*-?[\d.]+(\s+-?[\d.]+)+\s*$', r) and len(r.split()) in (2, 6)]


def survey_drawings(layout, surveys):
    out = {}
    for sv in surveys:
        try:
            if plan_file(sv):
                d = Drawing(sv, layout)
                if d.scraps:
                    out[sv] = d
        except Exception as e:                       # a drawing that cannot be fitted is left out
            print(f"{sv}: left out ({e})")
    return out


def plan_sections(d):
    """[(scrap index, obj index, head, (a, b) cave)] section lines; {name: (owner si, [cave points], point obj)}."""
    lines, drawings = [], {}
    text = d.text.replace('\r\n', '\n')
    owner = {}
    for si, (name, objs, f) in enumerate(d.scraps):
        for oi, o in enumerate(objs):
            if o.kind == 'line' and o.head.startswith('line section'):
                r = _rows(o)
                if len(r) >= 2:
                    lines.append((si, oi, o.head, (f(r[0][-2:]), f(r[-1][-2:]))))
            if o.kind == 'point':
                m = re.match(r'point (\S+) (\S+) section\b.*-scrap\s+(\S+)', o.head)
                if m:
                    owner[m.group(3).split('@')[0]] = (si, oi, (float(m.group(1)), float(m.group(2))))
    for m in re.finditer(r'(?ms)^scrap (\S+)([^\n]*)\n(.*?)^endscrap', text):
        if '-projection none' not in m.group(2) or m.group(1) not in owner:
            continue
        si, oi, at = owner[m.group(1)]
        f = d.scraps[si][2]
        pts = [p for o in parse_scrap(m.group(3)) if o.kind == 'line' and len(o.segments()) > 1
               for p in bezier_points(o.segments(), 8)]
        if len(pts) > 2:
            # where Therion draws it: its bounding box centred on the point
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            dx, dy = at[0] - (min(xs) + max(xs)) / 2, at[1] - (min(ys) + max(ys)) / 2
            drawings[m.group(1)] = (si, oi, [f((x + dx, y + dy)) for x, y in pts], f(at))
    return lines, drawings


def redo_line(a, b, own, others):
    """New ends (A, B) and direction for a section line a -> b across its passage `own`."""
    u = (b[0] - a[0], b[1] - a[1])
    L = math.hypot(*u)
    u = (u[0] / L, u[1] / L)
    left = (-u[1], u[0])
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    far = 50.0
    cross = LineString([(mid[0] - u[0] * far, mid[1] - u[1] * far), (mid[0] + u[0] * far, mid[1] + u[1] * far)])
    inside = cross.intersection(own)
    parts = [g for g in getattr(inside, 'geoms', [inside]) if g.geom_type == 'LineString' and g.length > 0]
    if not parts:
        return None
    piece = min(parts, key=lambda g: g.distance(Point(mid)))
    if piece.distance(Point(mid)) > 0.05:          # its middle not in the passage as filled: leave it
        return None
    t = sorted(cross.project(Point(p)) for p in piece.coords)
    lo, hi = t[0] - far, t[-1] - far                   # wall to wall, along u from mid
    ends, arrows = [], []
    for sgn, wall in ((-1, lo), (1, hi)):
        chosen = None
        m = MARGIN
        while m >= MIN_MARGIN - 1e-9:
            e = (mid[0] + u[0] * (wall + sgn * m), mid[1] + u[1] * (wall + sgn * m))
            tip = (e[0] + left[0] * ARROW, e[1] + left[1] * ARROW)
            stub = LineString([(mid[0] + u[0] * wall, mid[1] + u[1] * wall), e, tip])
            if others is None or not stub.intersects(others):
                chosen = (e, True)
                break
            m -= 0.1
        if chosen is None:
            chosen = ((mid[0] + u[0] * (wall + sgn * MARGIN), mid[1] + u[1] * (wall + sgn * MARGIN)), False)
        ends.append(chosen[0])
        arrows.append(chosen[1])
    return ends, arrows, u


def main(argv):
    p = argparse.ArgumentParser(prog='python3 -m tools.sketch2therion sections')
    p.add_argument('surveys', nargs='*', help='surveys to change (default: every survey with a plan)')
    p.add_argument('--write', action='store_true')
    a = p.parse_args(argv)
    layout = register.Layout(PROJECT.path(PROJECT.build['layout_plan']))
    folder = PROJECT.path(PROJECT.cave['folder'])
    every = sorted(x for x in os.listdir(folder) if os.path.exists(PROJECT.path(PROJECT.survey_file(x))))
    dr = survey_drawings(layout, every)
    fills = {(sv, si): d.scrap_fill(si) for sv, d in dr.items() for si in range(len(d.scraps))}
    allfill = unary_union([g for g in fills.values() if g is not None])
    todo = a.surveys or list(dr)
    secs = {sv: plan_sections(dr[sv]) for sv in dr}
    placed = {(sv, n): MultiPoint(pts).convex_hull.buffer(CLEAR)
              for sv, (_, ds) in secs.items() for n, (_, _, pts, _) in ds.items()}
    for sv in todo:
        if sv not in dr:
            continue
        d = dr[sv]
        lines, drawings = secs[sv]
        edits = {}                                    # (scrap name, obj index) -> new object text
        dirs = {}
        for si, oi, head, (pa, pb) in lines:
            own = fills.get((sv, si))
            if own is None:
                continue
            mid = Point((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
            if not own.buffer(0.05).contains(mid):       # its middle in another scrap of the survey
                own = unary_union([g for (s2, _), g in fills.items() if s2 == sv and g is not None])
            if not own.buffer(0.05).contains(mid):       # at a join, in the next survey's passage (TridentLeft 1)
                own = min(getattr(allfill, 'geoms', [allfill]), key=lambda g: g.distance(mid))
            others = allfill.difference(own.buffer(0.05))
            r = redo_line(pa, pb, own, others)
            if r is None:
                print(f"{sv} {d.scraps[si][0]}: a section line whose middle is not in a passage as filled, left as it is")
                continue
            (A, B), (arr_a, arr_b), u = r
            dirs[(si, oi)] = (u, (A, B))
            inv, k = _inverse(d.scraps[si][2])
            direction = 'both' if arr_a and arr_b else ('end' if arr_b else ('begin' if arr_a else 'both'))
            new_head = re.sub(r'\s-direction\s+\S+', '', head) + f' -direction {direction}'
            o = d.scraps[si][1][oi]
            edits[(d.scraps[si][0], oi)] = '\n'.join([new_head, '  %.2f %.2f' % inv(A), '  %.2f %.2f' % inv(B), 'endline'])
            note = '' if arr_a and arr_b else f" (arrow left off at the {'start' if not arr_a else 'end'})"
            print(f"{sv}: section line in {d.scraps[si][0]} across {math.dist(A, B) - 2 * MARGIN:.2f} m of passage{note}")
        moves = {}
        for name, (si, oi, pts, at) in drawings.items():
            hull = placed[(sv, name)]
            others = unary_union([allfill] + [g for key, g in placed.items() if key != (sv, name)])
            if not hull.intersects(others):
                continue
            # along its section line: the section line of the scrap holding its point, nearest it
            near = [v for (s2, o2), v in dirs.items() if s2 == si]
            u = min(near, key=lambda v: LineString(v[1]).distance(Point(at)))[0] if near else (1.0, 0.0)
            # the least move that clears it: along its line first (where it belongs), else any of
            # eight directions if that is much shorter
            best = None
            dirs8 = [(math.cos(math.radians(k * 45)), math.sin(math.radians(k * 45))) for k in range(8)]
            ang_u = math.atan2(u[1], u[0])
            dirs8 = [(math.cos(ang_u + math.radians(k * 45)), math.sin(ang_u + math.radians(k * 45))) for k in range(8)]
            for kstep in range(1, int(REACH / STEP) + 1):
                for v in dirs8:
                    dxy = (v[0] * kstep * STEP, v[1] * kstep * STEP)
                    g = MultiPoint([(x + dxy[0], y + dxy[1]) for x, y in pts]).convex_hull.buffer(CLEAR)
                    if not g.intersects(others):
                        along = abs(v[0] * u[0] + v[1] * u[1]) > 0.99
                        if best is None or (along and math.hypot(*dxy) <= 1.5 * math.hypot(*best[0])):
                            best = (dxy, along)
                if best and (best[1] or kstep * STEP > 1.5 * math.hypot(*best[0])):
                    break
            best = best[0] if best else None
            if not best:
                print(f"{sv} {name}: overlaps, and no clear place within {REACH} m along its line")
                continue
            placed[(sv, name)] = MultiPoint([(x + best[0], y + best[1]) for x, y in pts]).convex_hull.buffer(CLEAR)
            inv, k = _inverse(d.scraps[si][2])
            o0, o1 = inv((0, 0)), inv(best)
            moves[name] = (si, oi, (o1[0] - o0[0], o1[1] - o0[1]))
            print(f"{sv} {name}: moved {math.hypot(*best):.2f} m{' along its section line' if abs(best[0] * u[0] + best[1] * u[1]) > 0.99 * math.hypot(*best) else ''}, clear of the passages")
        if a.write and (edits or moves):
            write(d, edits, moves)


def shift_rows(body, dx, dy):
    """Th2 text with its coordinate rows and points moved by (dx, dy)."""
    out = []
    for line in body.split('\n'):
        v = line.split()
        if v and len(v) in (2, 6) and all(re.match(r'^-?[\d.]+$', x) for x in v):
            out.append('  ' + ' '.join('%.2f' % (float(x) + (dx if i % 2 == 0 else dy)) for i, x in enumerate(v)))
        else:
            m = re.match(r'(point )(\S+) (\S+)(.*)', line)
            out.append('%s%.2f %.2f%s' % (m.group(1), float(m.group(2)) + dx, float(m.group(3)) + dy, m.group(4)) if m else line)
    return '\n'.join(out)


def scrap_span(text, name):
    """Start and end of a scrap's body in th2 text."""
    m = re.search(rf'(?ms)^scrap {re.escape(name)}\b[^\n]*\n(.*?)^endscrap', text)
    return m.start(1), m.end(1)


def write(d, edits, moves):
    """Replace the changed objects, reading the file again first."""
    raw = open(d.path, encoding='utf-8', newline='').read()
    nl = '\r\n' if '\r\n' in raw else '\n'
    text = raw.replace('\r\n', '\n')

    # objects in plan scraps (section lines, point sections), by index in the scrap as read now;
    # a section drawing is moved by its point only
    by_scrap = {}
    for (sname, oi), new in edits.items():
        by_scrap.setdefault(sname, {})[oi] = new
    for name, (si, oi, (dx, dy)) in moves.items():
        o = d.scraps[si][1][oi]
        by_scrap.setdefault(d.scraps[si][0], {})[oi] = shift_rows(o.text(), dx, dy)
    for sname, reps in by_scrap.items():
        s, e = scrap_span(text, sname)
        body = text[s:e]
        objs = parse_scrap(body)
        for oi, new in sorted(reps.items(), key=lambda kv: -kv[0]):
            old = d.scraps[[x[0] for x in d.scraps].index(sname)][1][oi].text()
            if body.count(old) != 1:
                print(f"{os.path.basename(d.path)} {sname}: an object changed since it was read, left")
                continue
            body = body.replace(old, new, 1)
        text = text[:s] + body + text[e:]
    open(d.path, 'w', encoding='utf-8', newline='').write(text.replace('\n', nl))
    print(f"wrote {d.path}")
