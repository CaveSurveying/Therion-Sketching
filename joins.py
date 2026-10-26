# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""Where a new survey's plan joins an earlier one: the earlier drawing's
walls cut back to where the new survey starts.

    python3 -m tools.sketch2therion joins [X ...] [--write] [--pictures DIR]

For each 2026 survey X (or those named) and each survey it joins by an
equate (only: a passage overlapping another with no equate passes over
or under it, and both stay whole), the earlier
survey's plan walls lying inside the new survey's passage (or along its
walls, within REACH) near the join are found. Each such run is cut where
it enters the passage, at the point nearest the new survey's wall end if
one is close, by splitting the curve there (no node moves: the user,
2026-10-13), and the run is deleted. A picture of each join shows the
earlier survey kept (black), the new survey (blue) and what is deleted
(red). With --write the earlier plan files are changed.

Both drawings are put in the cave's coordinates (Therion's plan layout,
output/layout-plan.xvi) by fitting each scrap to its stations.
"""
import argparse
import math
import os
import re

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from . import project as _project
from . import register
from .tidy import bezier_points, parse_scrap, therion_chain

PROJECT = _project.load()
REACH = 0.5         # m: an earlier wall within this of the new passage is in it (drawn along its wall:
                    # NorthRift 94 on, 0.3 to 0.4 m outside Connection's)
CLOSE = 0.3         # m: gaps between the new survey's scraps closed
END_FREE = 0.3      # m: the last of a new wall is not one an earlier wall can run along
NEAR_JOIN = 4.0     # m: a run to delete comes within this of the join station
SNAP = 0.6          # m: a cut moves to the point nearest a new wall's end this close
MIN_RUN = 0.3       # m: shorter runs are left
LEFTOVER = 2.5      # m: a shorter piece left at a line's end goes too (CrystalPitch 32: 2 m left)
STEPS = 24          # samples a segment


def _cubic(p0, r):
    if len(r) == 6:
        return [p0, (r[0], r[1]), (r[2], r[3]), (r[4], r[5])]
    q = (r[0], r[1])
    return [p0, (p0[0] + (q[0] - p0[0]) / 3, p0[1] + (q[1] - p0[1]) / 3),
            (p0[0] + 2 * (q[0] - p0[0]) / 3, p0[1] + 2 * (q[1] - p0[1]) / 3), q]


def _split(c, t):
    """de Casteljau: the cubic c split at t: (first, second) control points."""
    lerp = lambda a, b: (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    a = [lerp(c[k], c[k + 1]) for k in range(3)]
    b = [lerp(a[0], a[1]), lerp(a[1], a[2])]
    m = lerp(b[0], b[1])
    return [c[0], a[0], b[0], m], [m, b[1], a[2], c[3]]


def _at(c, t):
    return _split(c, t)[0][3]


class Drawing:
    """A survey's plan th2 in the cave's coordinates, scrap by scrap."""

    def __init__(self, survey, layout):
        self.survey = survey
        self.path = plan_file(survey)
        self.text = open(self.path, encoding='utf-8', newline='').read()
        self.nl = '\r\n' if '\r\n' in self.text else '\n'
        self.scraps = []                       # [(name, start, end, objs, fit, inverse)]
        t = self.text.replace('\r\n', '\n')
        for m in re.finditer(r'^(scrap (\S+)([^\n]*))\n(.*?)^endscrap', t, re.S | re.M):
            if '-projection' in m.group(3) and '-projection plan' not in m.group(3):
                continue
            objs = parse_scrap(m.group(4))
            pairs = []
            for o in objs:
                p = re.match(r'point (\S+) (\S+) station\b.*-name\s+(\S+)', o.head) if o.kind == 'point' else None
                if p:
                    n, sv = (p.group(3).split('@') + [survey])[:2]
                    ps = layout.find(n, sv.split('.')[0])
                    if ps:
                        pairs.append((complex(float(p.group(1)), float(p.group(2))), complex(*ps[0])))
            if len(pairs) < 2:
                continue
            fit = _similarity(pairs)
            self.scraps.append((m.group(2), objs, fit))

    def walls(self, outer_only=True):
        """[(scrap index, obj index, head, [segment rows], cave polyline)]"""
        out = []
        for si, (name, objs, f) in enumerate(self.scraps):
            for oi, o in enumerate(objs):
                if o.kind != 'line' or not o.head.startswith('line wall') or len(o.segments()) < 2:
                    continue
                if outer_only and ('-outline none' in o.head or '-subtype invisible' in o.head):
                    continue
                out.append((si, oi, o.head, o.segments(), [f(p) for p in bezier_points(o.segments(), 8)]))
        return out

    def scrap_fill(self, si):
        """One scrap's passage as Therion fills it (its outline walls joined up), in cave coordinates."""
        name, objs, f = self.scraps[si]
        lines = [bezier_points(o.segments(), 8) for o in objs if o.kind == 'line'
                 and o.head.startswith('line wall') and len(o.segments()) > 1
                 and '-outline none' not in o.head and '-outline in' not in o.head
                 and '-subtype invisible' not in o.head]
        polys = [Polygon([f(p) for p in r]).buffer(0) for r in therion_chain(lines) if len(r) > 3]
        polys = [g for g in polys if not g.is_empty]
        return unary_union(polys) if polys else None

    def fill(self):
        """The passage as Therion fills it (its outline walls joined up), in cave coordinates."""
        polys = [g for g in (self.scrap_fill(si) for si in range(len(self.scraps))) if g is not None]
        return unary_union(polys) if polys else None


def _similarity(pairs):
    """z -> a z + b fitted to (drawing, cave) pairs; returned as a function on (x, y)."""
    n = len(pairs)
    mz = sum(z for z, _ in pairs) / n
    mw = sum(w for _, w in pairs) / n
    den = sum(abs(z - mz) ** 2 for z, _ in pairs)
    a = sum((w - mw) * (z - mz).conjugate() for z, w in pairs) / den if den else 1
    b = mw - a * mz

    def f(p):
        w = a * complex(p[0], p[1]) + b
        return (w.real, w.imag)
    return f


def plan_file(survey):
    folder = os.path.dirname(PROJECT.path(PROJECT.survey_file(survey)))
    for name in (f"{survey}.plan.th2", f"{survey}P.th2"):
        p = os.path.join(folder, name)
        if os.path.exists(p):
            return p
    found = sorted(f for f in os.listdir(folder) if f.endswith('.plan.th2'))     # Century: Centry.plan.th2
    return os.path.join(folder, found[0]) if len(found) == 1 else None


def _date(survey):
    t = open(PROJECT.path(PROJECT.survey_file(survey)), encoding='utf-8', errors='replace').read()
    m = re.search(r'^\s*date\s+(\S+)', t, re.M)
    return m.group(1) if m else ''


def equated_joins(surveys):
    """[(new, earlier, (name, survey) of the join station)] from the cave's equates."""
    cave = PROJECT.path(PROJECT.cave['plan_map_file'])
    t = open(cave, encoding='utf-8', errors='replace').read()
    out = []
    for m in re.finditer(r'^\s*equate\s+(.*?)\s*(?:#.*)?$', t, re.M):
        st = [s for s in m.group(1).split() if '@' in s]
        for i in range(len(st)):
            for j in range(i + 1, len(st)):
                (na, sa), (nb, sb) = st[i].split('@'), st[j].split('@')
                if sa == sb or not (sa in surveys or sb in surveys):
                    continue
                da, db = _date(sa), _date(sb)
                # the later survey is the new one; on the same day, the one starting there (its 0 or 1)
                if da != db:
                    new, old = ((sa, na), (sb, nb)) if da > db else ((sb, nb), (sa, na))
                else:
                    new, old = ((sa, na), (sb, nb)) if na in ('0', '1') and nb not in ('0', '1') else ((sb, nb), (sa, na))
                out.append((new[0], old[0], (old[1], old[0])))
    return out


def _legs(d, layout):
    """The survey's legs as lines in the layout's (cave) coordinates."""
    from .roofs import Splays, SQL
    sp = Splays.from_database(PROJECT.path(SQL))
    tag = '@' + d.survey
    out = []
    for a, bs in sp.legs.items():
        for b in bs:
            if a.endswith(tag) and b.endswith(tag) and a < b:
                pa, pb = layout.find(a.split('@')[0], d.survey), layout.find(b.split('@')[0], d.survey)
                if pa and pb and pa[0] != pb[0]:
                    out.append(LineString([pa[0], pb[0]]))
    return out


def resurveyed_legs(new, old, layout):
    """The earlier survey's legs lying inside the new survey's passage:
    surveyed again by it (Connection 25 to 28 over BoldStep 8 to 11). Its
    walls by them go too."""
    fill = new.fill()
    if fill is None:
        return []
    return [l for l in _legs(old, layout) if l.length > 0.2 and fill.contains(l.interpolate(0.5, normalized=True))
            and fill.buffer(REACH).contains(l)]


def runs_to_cut(new, old, at, layout):
    """[(scrap index, obj index, [(seg, t0, seg, t1)])]: the stretches of the
    earlier drawing's walls to delete, near the join station `at` (or
    anywhere along the new passage if at is None)."""
    fill = new.fill()
    if fill is None or fill.is_empty:
        return []
    # in the new passage, or along the new walls (not their ends: two walls meeting end to end
    # at a corner are not one drawn along the other; TridentCentre at 12)
    from shapely.ops import substring
    body = []
    for *_, pp in new.walls():
        l = LineString(pp)
        if l.length > 2 * END_FREE:
            body.append(substring(l, END_FREE, l.length - END_FREE))
    zone = fill.buffer(CLOSE, join_style=1).buffer(-CLOSE, join_style=1)
    if body:
        zone = zone.union(unary_union(body).buffer(REACH))
    centre = Point(layout.find(*at)[0]) if at and layout.find(*at) else None
    new_ends = [Point(pp[k]) for *_, pp in new.walls() for k in (0, -1)]
    dup = resurveyed_legs(new, old, layout)
    olegs = _legs(old, layout)
    out = []
    for si, oi, head, segs, _ in old.walls():
        f = old.scraps[si][2]
        samples = []                     # (seg, t, cave point)
        for s in range(1, len(segs)):
            c = _cubic(tuple(segs[s - 1][-2:]), segs[s])
            for q in range(STEPS + 1 if s == len(segs) - 1 else STEPS):
                t = q / STEPS
                samples.append((s, t, f(_at(c, t))))
        def by_dup(p):                   # nearest of its own legs surveyed again
            if not dup:
                return False
            q = Point(p)
            d_dup = min(l.distance(q) for l in dup)
            return d_dup < 2.0 and d_dup <= min((l.distance(q) for l in olegs), default=9e9) + 1e-6
        flags = [zone.contains(Point(p)) or by_dup(p) for _, _, p in samples]
        runs, k = [], 0
        while k < len(samples):
            if not flags[k]:
                k += 1
                continue
            j = k
            while j + 1 < len(samples) and flags[j + 1]:
                j += 1
            pts = [p for _, _, p in samples[k:j + 1]]
            length = LineString(pts).length if len(pts) > 1 else 0.0
            near = centre is None or LineString(pts if len(pts) > 1 else pts * 2).distance(centre) < NEAR_JOIN
            if length >= MIN_RUN and near:
                a, b = _snap(samples, k, new_ends), _snap(samples, j, new_ends)
                span = lambda a, b: [p for s_, t_, p in samples if a <= (s_, t_) <= b]
                if len(span(a, b)) < 2 or LineString(span(a, b)).length < MIN_RUN:
                    a, b = samples[k][:2], samples[j][:2]      # snapped to nothing: as found
                # nor a scrap of wall left at the line's end (CrystalPitch: 0.3 and 0.8 m left
                # beyond GoSouth's passage, an outline MetaPost could not draw)
                before = [p for s_, t_, p in samples if (s_, t_) <= a]
                after = [p for s_, t_, p in samples if (s_, t_) >= b]
                near_new = fill.buffer(1.0)                 # (only a piece still in the new passage)
                if len(before) < 2 or (LineString(before).length < LEFTOVER
                                       and near_new.contains(LineString(before))):
                    a = samples[0][:2]
                if len(after) < 2 or (LineString(after).length < LEFTOVER
                                      and near_new.contains(LineString(after))):
                    b = samples[-1][:2]
                mid = pts[len(pts) // 2]
                runs.append((a[0], a[1], b[0], b[1], length, mid))
            k = j + 1
        if runs:
            out.append((si, oi, runs))
    return out


def _snap(samples, k, ends):
    """The run's end at sample k, moved to the sample nearest a new wall's
    end if one is within SNAP of it (so the cut is where the new walls start)."""
    p = Point(samples[k][2])
    e = min(ends, key=lambda q: q.distance(p), default=None)
    if e is None or e.distance(p) > SNAP:
        return samples[k][0], samples[k][1]
    lo, hi = max(0, k - 3 * STEPS), min(len(samples), k + 3 * STEPS)
    best = min(range(lo, hi), key=lambda i: Point(samples[i][2]).distance(e))
    return samples[best][0], samples[best][1]


def cut_line(o, runs):
    """The line o without the stretches in runs, as one or more lines, its
    option rows kept with their points; a stretch starts or ends part way
    along a segment by splitting it there (no node moves)."""
    # rows grouped by point: [(segment values, [option rows after it])]
    pts, lead = [], []
    for r in o.rows:
        v = r.split()
        try:
            vals = [float(x) for x in v]
            if len(vals) in (2, 6):
                pts.append([vals, [], r])          # (the row as written, kept where not cut)
                continue
        except ValueError:
            pass
        (pts[-1][1] if pts else lead).append(r)
    segs = [p[0] for p in pts]
    # positions along the line as (segment, t); keep the complement of the runs
    pos = lambda s, t: s - 1 + t
    cuts = sorted((pos(a, ta), pos(b, tb)) for a, ta, b, tb, *_ in runs)
    keep, at = [], 0.0
    for x0, x1 in cuts:
        if x0 > at:
            keep.append((at, x0))
        at = max(at, x1)
    if at < len(segs) - 1:
        keep.append((at, len(segs) - 1))
    out = []
    for x0, x1 in keep:
        if x1 - x0 < 1e-6:
            continue
        rows = []
        s0, t0 = int(x0) + 1, x0 - int(x0)
        if s0 > len(segs) - 1:
            continue
        s1, t1 = int(x1) + 1, x1 - int(x1)
        if t1 < 1e-9 and s1 > 1:
            s1, t1 = s1 - 1, 1.0
        for s in range(s0, min(s1, len(segs) - 1) + 1):
            c = _cubic(tuple(segs[s - 1][-2:]), segs[s])
            curved = len(segs[s]) == 6
            a = t0 if s == s0 else 0.0
            b = t1 if s == s1 else 1.0
            if b - a < 1e-9:
                continue
            piece = _split(_split(c, b)[0], a / b if b else 0)[1] if (a > 0 or b < 1) else c
            if not rows:
                if a == 0:                          # a node: as written
                    v = pts[s - 1][2].split()
                    rows.append(['  ' + ' '.join(v[-2:]), pts[s - 1][1]])
                else:
                    rows.append(['  %.2f %.2f' % piece[0], []])
            end_opts = pts[s][1] if b == 1.0 else []
            if a == 0 and b == 1.0:                 # a whole segment: as written
                rows.append([pts[s][2], end_opts])
            else:
                vals = ['%.2f' % v for p in (piece[1:] if curved else piece[3:]) for v in p]
                if b == 1.0:                        # ending on a node: the node as written
                    vals[-2:] = pts[s][2].split()[-2:]
                rows.append(['  ' + ' '.join(vals), end_opts])
        if len(rows) > 1:
            out.append(lead + [x for r, opts in rows for x in [r] + opts])
    return out


def apply(old, cuts):
    """The earlier drawing's text with the runs deleted."""
    t = old.text.replace('\r\n', '\n')
    by_scrap = {}
    for si, oi, runs in cuts:
        by_scrap.setdefault(si, {})[oi] = runs
    pieces, pos = [], 0
    names = {si: old.scraps[si][0] for si in by_scrap}
    for m in re.finditer(r'^(scrap (\S+)[^\n]*)\n(.*?)^endscrap', t, re.S | re.M):
        si = next((k for k, n in names.items() if n == m.group(2)), None)
        if si is None:
            continue
        objs = parse_scrap(m.group(3))
        body = []
        for oi, o in enumerate(objs):
            if oi in by_scrap[si]:
                parts = cut_line(o, by_scrap[si][oi])
                for k, rows in enumerate(parts):       # an -id only once
                    h = o.head if k == 0 else re.sub(r' -id \S+', '', o.head)
                    body.append('\n'.join([h] + rows + ['endline']))
                continue
            body.append(o.text())
        tail = m.group(3)[len(m.group(3).rstrip('\n')):]      # its blank lines before endscrap kept
        pieces.append(t[pos:m.start(3)] + '\n'.join(body).rstrip('\n') + (tail or '\n'))
        pos = m.end(3)
    pieces.append(t[pos:])
    return ''.join(pieces).replace('\n', old.nl)


def picture(new, old, cuts, at, layout, out, R=7.0):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 8))
    dele = {(si, oi): runs for si, oi, runs in cuts}
    pts_all = []
    for si, oi, head, segs, pp in old.walls(outer_only=False):
        ax.plot([p[0] for p in pp], [p[1] for p in pp], color='k', lw=1.4, ls='--' if 'presumed' in head else '-')
        if (si, oi) in dele:
            f = old.scraps[si][2]
            for a, ta, b, tb, *_ in dele[(si, oi)]:
                q = []
                for s in range(a, b + 1):
                    c = _cubic(tuple(segs[s - 1][-2:]), segs[s])
                    lo = ta if s == a else 0.0
                    hi = tb if s == b else 1.0
                    q += [f(_at(c, lo + (hi - lo) * i / 20)) for i in range(21)]
                ax.plot([p[0] for p in q], [p[1] for p in q], color='#e00', lw=3.2, alpha=0.85, zorder=5)
                pts_all += q
    for *_, head, segs, pp in new.walls(outer_only=False):
        ax.plot([p[0] for p in pp], [p[1] for p in pp], color='#06f', lw=1.4, ls='--' if 'presumed' in head else '-')
    c = layout.find(*at)[0] if at and layout.find(*at) else (
        (sum(p[0] for p in pts_all) / len(pts_all), sum(p[1] for p in pts_all) / len(pts_all)) if pts_all else (0, 0))
    # legs and splays (thin, the survey's colour, splays paler); the layout is the 3D model's
    # x and y moved, so a splay ends at its station's place plus its plan offset
    from .roofs import Splays, SQL
    sp = Splays.from_database(PROJECT.path(SQL))
    for d, col, pale in ((old, 'k', '0.6'), (new, '#06f', '#8bf')):
        tag = '@' + d.survey
        for a, bs in sp.legs.items():
            pa = layout.find(a.split('@')[0], d.survey) if a.endswith(tag) else None
            if not pa or math.dist(pa[0], c) > 2 * R:
                continue
            for b in bs:
                pb = layout.find(b.split('@')[0], d.survey) if b.endswith(tag) and a < b else None
                if pb:
                    ax.plot([pa[0][0], pb[0][0]], [pa[0][1], pb[0][1]], color=col, lw=0.8, zorder=3)
            for dx, dy in sp.ends.get(a, ()):
                ax.plot([pa[0][0], pa[0][0] + dx], [pa[0][1], pa[0][1] + dy], color=pale, lw=0.5, zorder=2)
    for (n, sv), ps in layout.by_name.items():
        if sv in (new.survey, old.survey) and math.dist(ps[0], c) < R:
            col = '#06f' if sv == new.survey else 'k'
            ax.plot(*ps[0], '+', color=col)
            ax.annotate(f"{n}@{sv}", ps[0], fontsize=7, color=col)
    ax.set_xlim(c[0] - R, c[0] + R)
    ax.set_ylim(c[1] - R, c[1] + R)
    ax.set_aspect('equal')
    where = f"{at[0]}@{at[1]}" if at else "(no equate)"
    ax.set_title(f"{new.survey} (blue) joining {old.survey} (black, kept) at {where}\n"
                 f"red: {old.survey}'s walls deleted; thin: legs, pale: splays", fontsize=10)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.savefig(out, dpi=80)
    plt.close(fig)


def main(argv):
    p = argparse.ArgumentParser(prog='python3 -m tools.sketch2therion joins')
    p.add_argument('surveys', nargs='*', help='new surveys (default: those of 2026)')
    p.add_argument('--write', action='store_true', help="change the earlier surveys' plan files")
    p.add_argument('--pictures', default='review/joins', help='where the pictures go')
    p.add_argument('--radius', type=float, default=7.0, help='m round the join shown')
    p.add_argument('--only', nargs='*', default=None, help='earlier surveys to change (with --write)')
    a = p.parse_args(argv)
    layout = register.Layout(PROJECT.path(PROJECT.build['layout_plan']))
    folder = PROJECT.path(PROJECT.cave['folder'])
    every = sorted(d for d in os.listdir(folder) if os.path.exists(PROJECT.path(PROJECT.survey_file(d))))
    surveys = a.surveys or [s for s in every if _date(s).startswith('2026')]
    todo = {}
    for new, old, at in equated_joins(surveys):
        if new in surveys and plan_file(new) and plan_file(old):
            todo.setdefault(old, []).append((new, at))
    drawings = {}
    get = lambda s: drawings.setdefault(s, Drawing(s, layout))
    # only equated joins: a passage overlapping another with no equate is one passing over or
    # under it (FairyChimneys 38 to 40 over RoundTheBend by 135), both drawn whole (log row 160)
    for old, joins in sorted(todo.items()):
        cuts_all = []
        for new, at in joins:
            cuts = runs_to_cut(get(new), get(old), at, layout)
            n = sum(len(r) for *_, r in cuts)
            where = f"{at[0]}@{at[1]}" if at else "(no equate)"
            print(f"{new} joins {old} at {where}: {n} stretch(es) of {old}'s walls to delete"
                  + "".join(f", {r[4]:.1f} m at ({r[5][0]:.1f}, {r[5][1]:.1f})" for si, oi, rs in cuts for r in rs))
            picture(get(new), get(old), cuts, at, layout,
                    os.path.join(a.pictures, f"{new}-{old}-{at[0] if at else 'noequate'}.png"), a.radius)
            cuts_all += cuts
        if a.write and cuts_all and (a.only is None or old in a.only):
            merged = {}
            for si, oi, runs in cuts_all:
                merged.setdefault((si, oi), []).extend(runs)
            text = apply(get(old), [(si, oi, r) for (si, oi), r in merged.items()])
            open(get(old).path, 'w', encoding='utf-8', newline='').write(text)
            print(f"  wrote {get(old).path}")
