# Ported from caves-mendip-swildons, tools/sketch2therion (commit 198bf46,
# https://github.com/paperclipmonkey/caves-mendip-swildons). GPLv3: see tools/LICENSE.
"""Floor steps, climbs and gradients for the plan, from the side view.

The floor along each leg is read off the extended-elevation sketch: the
highest sketch line within a few metres below the leg. Where it drops by
0.7 m or more within 0.6 m of passage, and stays down, that's a step (a
`line floor-step` across the passage in the plan, labelled C1m, C1.5m...
from 1 m). A leg whose floor slopes steadily by 8-35 degrees gets a
gradient arrow.
"""
import math
import statistics

from shapely.geometry import LineString, Point


def chains(legs):
    """Split the leg network into runs of stations between junctions and ends."""
    nb = {}
    for a, b in legs:
        if a != b:
            nb.setdefault(a, []).append(b)
            nb.setdefault(b, []).append(a)
    done = set()
    out = []
    ends = [n for n, v in nb.items() if len(v) != 2] or list(nb)[:1]
    for s in ends:
        for t in nb[s]:
            if frozenset((s, t)) in done:
                continue
            run = [s, t]
            done.add(frozenset((s, t)))
            while len(nb[run[-1]]) == 2:
                nxt = [x for x in nb[run[-1]] if frozenset((run[-1], x)) not in done]
                if not nxt:
                    break
                done.add(frozenset((run[-1], nxt[0])))
                run.append(nxt[0])
            out.append(run)
    return out


def profile(chain, pos, lines, below=4.0, dx=0.1):
    """Floor height along a chain in the side view: [(x, floor|None, (a, b, frac))]."""
    segs = [(a, b) for pp in lines for a, b in zip(pp, pp[1:]) if abs(b[0] - a[0]) > 1e-6]
    out = []
    for sa, sb in zip(chain, chain[1:]):
        (xa, ya), (xb, yb) = pos[sa], pos[sb]
        if abs(xb - xa) < 0.05:
            continue
        n = max(1, int(abs(xb - xa) / dx))
        for i in range(n):
            fr = i / n
            x = xa + (xb - xa) * fr
            y = ya + (yb - ya) * fr
            best = None
            for (x1, y1), (x2, y2) in segs:
                if min(x1, x2) <= x <= max(x1, x2):
                    yy = y1 + (y2 - y1) * (x - x1) / (x2 - x1)
                    if y - below <= yy <= y + 0.3 and (best is None or yy > best):
                        best = yy
            out.append((x, best, (sa, sb, fr)))
    return out


def _steps(prof, min_drop, run):
    pts = [p for p in prof if p[1] is not None]
    out = []
    i = 0
    while i < len(pts):
        x0, f0, where = pts[i]
        j = i
        best = None
        while j + 1 < len(pts) and abs(pts[j + 1][0] - x0) <= run:
            j += 1
            drop = f0 - pts[j][1]
            if drop >= min_drop and (best is None or drop > best[0]):
                best = (drop, j)
        if best:
            out.append({'d': best[0], 'xa': x0, 'xb': pts[best[1]][0], 'a': where, 'b': pts[best[1]][2]})
            i = best[1] + 1
        else:
            i += 1
    return out


def climbs(prof, min_drop=0.7, run=0.6, merge=1.0, min_net=0.7, side=1.5):
    """Steps in the floor that stay down: the floor either side differs by min_net.
    The side view may run either way, so drops in both directions count."""
    out = []
    for sign in (1, -1):
        p = [(x, None if f is None else sign * f, w) for x, f, w in prof]
        st = []
        for s in _steps(p, min_drop, run):
            if st and s['xa'] - st[-1]['xb'] <= merge:
                st[-1]['d'] += s['d']
                st[-1]['xb'] = s['xb']
            else:
                st.append(s)
        pts = [(x, f) for x, f, _ in p if f is not None]
        for c in st:
            lo, hi = sorted((c['xa'], c['xb']))
            up = [f for x, f in pts if lo - side <= x <= lo - 0.2]
            dn = [f for x, f in pts if hi + 0.2 <= x <= hi + side]
            if up and dn and statistics.median(up) - statistics.median(dn) >= min_net:
                out.append(c)
    return out


def gradients(prof, steps, min_deg=8, max_deg=35, min_h=2.0):
    """Legs whose floor slopes steadily, without a step on them: [(a, b, degrees)],
    a being the upper end."""
    with_step = {(c['a'][0], c['a'][1]) for c in steps} | {(c['b'][0], c['b'][1]) for c in steps}
    by = {}
    for x, f, (a, b, fr) in prof:
        if f is not None:
            by.setdefault((a, b), []).append((x, f))
    out = []
    for (a, b), v in by.items():
        if (a, b) in with_step or len(v) < 5:
            continue
        h = abs(v[-1][0] - v[0][0])
        if h < min_h:
            continue
        n = max(1, len(v) // 5)
        drop = statistics.median(f for x, f in v[:n]) - statistics.median(f for x, f in v[-n:])
        deg = math.degrees(math.atan2(abs(drop), h))
        if min_deg <= deg <= max_deg:
            out.append((a, b, round(deg, 1)) if drop > 0 else (b, a, round(deg, 1)))
    return out


def analyse(elevation, colours=('BLACK', 'BROWN', 'GRAY')):
    """Climbs and gradients from an extended-elevation Sketch:
    {'climbs': [(a, b, frac, height)], 'gradients': [(upper, lower, degrees)]}."""
    # The floor profile: every colour that can draw a floor (black rock,
    # brown mud, grey steps), whatever the cave's wall colours are.
    pos = elevation.positions()
    lines = [pp for c, pp in elevation.lines if c in colours and len(pp) > 1]
    legs = [(a, b) for a, b, *_ in elevation.legs()]
    res = {'climbs': [], 'gradients': []}
    for ch in chains(legs):
        if pos[ch[-1]][0] < pos[ch[0]][0]:
            ch = ch[::-1]           # read every run left to right
        prof = profile(ch, pos, lines)
        st = climbs(prof)
        res['climbs'] += [(c['a'][0], c['a'][1], c['a'][2], round(c['d'], 2)) for c in st]
        res['gradients'] += gradients(prof, st)
    return res


# -- drawing them on the plan -------------------------------------------------

def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _label(h):
    from .settings import SETTINGS
    if SETTINGS['climb_whole']:       # whole metres, half up (1.5 -> 2, 2.5 -> 3)
        return "C%dm" % max(1, math.floor(h + 0.5))
    r = round(h * 2) / 2
    return "C%dm" % r if r == int(r) else "C%.1fm" % r


def th2(data, stations, passage, px, placed=None, notation=()):
    """th2 lines for the floor steps, climb labels and gradient arrows on a plan scrap.
    stations: plan positions; passage: the scrap's outline polygon;
    notation: step lines read from the plan sketch (LineStrings, m). With
    [convert] elevation_step_min set, a climb gets a guessed step line only
    if no notation step is near and it is at least that high."""
    from .settings import SETTINGS
    guess_min = SETTINGS['elevation_step_min']
    placed = [] if placed is None else placed
    o = []
    for a, b, fr, d in data.get('climbs', []):
        if a not in stations or b not in stations:
            continue
        A, B = stations[a], stations[b]
        p = _lerp(A, B, fr)
        noted = any(n.distance(Point(p)) < 2.5 for n in notation)
        draw = not noted and d >= guess_min
        L = math.dist(A, B) or 1
        u = ((B[0] - A[0]) / L, (B[1] - A[1]) / L)
        left = (-u[1], u[0])
        cut = LineString([(p[0] + left[0] * 8, p[1] + left[1] * 8),
                          (p[0] - left[0] * 8, p[1] - left[1] * 8)]).intersection(passage)
        parts = [cut] if cut.geom_type == 'LineString' else list(getattr(cut, 'geoms', []))
        parts = [g for g in parts if g.geom_type == 'LineString' and g.length > 0.1]
        if not parts:
            continue
        seg = min(parts, key=lambda g: g.distance(Point(p))).intersection(Point(p).buffer(1.75))
        if seg.is_empty or seg.geom_type != 'LineString':
            continue
        q = list(seg.coords)
        q = [_lerp(q[0], q[-1], 0.04), _lerp(q[0], q[-1], 0.96)]
        if (q[0][0] - p[0]) * left[0] + (q[0][1] - p[1]) * left[1] < 0:
            q = q[::-1]
        if guess_min > 0:             # keep the guess off the walls
            q = [_lerp(q[0], q[-1], 0.08), _lerp(q[0], q[-1], 0.92)]
        if draw:
            head = "line pit" if guess_min > 0 and d >= SETTINGS['pitch_min'] else "line floor-step"
            o += [head] + ["  %.2f %.2f" % px(v) for v in q] + ["endline", ""]
        if d >= 0.95:
            lp = None
            for k in (1.0, 2.0, -1.0, 3.0, -2.0):
                c = (p[0] + u[0] * k, p[1] + u[1] * k)
                if passage.contains(Point(c)) and all(math.dist(c, z) > 2.5 for z in placed):
                    lp = c
                    break
            lp = lp or (p[0] + u[0], p[1] + u[1])
            placed.append(lp)
            o += ['point %.2f %.2f label -text "%s" -scale s' % (*px(lp), _label(d)), ""]
    for a, b, deg in data.get('gradients', []):
        if a not in stations or b not in stations:
            continue
        A, B = stations[a], stations[b]
        m = _lerp(A, B, 0.5)
        if not passage.contains(Point(m)):
            continue
        brg = math.degrees(math.atan2(B[0] - A[0], B[1] - A[1])) % 360
        o += ["point %.2f %.2f gradient -orientation %.1f" % (*px(m), brg), ""]
    return o
