# Ported from caves-mendip-swildons, tools/sketch2therion (commit 198bf46,
# https://github.com/paperclipmonkey/caves-mendip-swildons). GPLv3: see LICENSE.
"""Extended-elevation fill from the splay shots.

Where the sketch has no roof or floor drawn, the converter had to guess
how far the passage goes up and down: it reached for the nearest sketch
line (which could belong to another passage, giving rectangles of fill),
and closed the rest up round the legs (giving round bites). The splays
measured the roof and floor at each station, so this redraws the fill
of each converted elevation scrap from them:

- along each leg, the passage goes from the floor to the roof, both
  taken from the splays at its two stations and interpolated between
  them;
- where a drawn wall is near that roof or floor (within 75 cm beyond
  it), the fill goes to the wall instead, so drawn walls still win;
- where a station has no splay up (or down), the nearest drawn wall
  within `reach` is used, else 1 m.

The walls then become the outline again exactly as in tidy.py.

The splays are the drawing's own sketch's (its backdrop .xvi).

    python3 -m tools.sketch2therion roofs FILE.th2 [...]
"""
import functools
import math
import os
import re
import sqlite3
from collections import defaultdict

from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from . import project as _project
from . import tidy
from .survey import survey_of as _survey_of
from .tidy import Obj, bezier_points, parse_scrap, scale_of

SQL = _project.load().build['sql']      # exported by tools/layout.thcfg (Splays.from_database)
STEEP = 40          # a splay at least this steep (degrees) measures the roof or floor
NEAR = 1.5         # m: a drawn wall this far beyond the splay roof/floor still counts
NEAR_PLAN = 0.4     # m: in plan the splay ends are the walls
DEFAULT = 1.0       # m: roof/floor where nothing tells us
REACH = 5.0         # m: how far to look for a drawn wall when the splays don't say


def sql_text(text):
    """Therion's SQL export with bare nan values (it writes them for some
    projected-elevation maps) made NULL, which SQLite can read."""
    return re.sub(r'(?<=[,(])(\s*)-?nan(?=\s*[,)])', r'\1NULL', text)


class Splays:
    """A survey's legs, station positions and splays: `pos` {station: (x, y)}
    and `ends` {station: [(dx, dy) of each splay end]} in plan, `up` and
    `down` {station: metres} from the steep splays, `legs` {station: {next}}.
    Stations are `name@survey`."""

    def __init__(self):
        self.ends = defaultdict(list)
        self.up, self.down = {}, {}
        self.pos = {}
        self.legs = defaultdict(set)

    @classmethod
    def from_drawing(cls, th2, survey=None):
        """From the sketch a drawing links as its backdrop (the first .xvi
        found): plan ends from a plan sketch, up and down from an elevation."""
        return _drawing_splays(os.path.abspath(th2), survey)

    @classmethod
    def from_sketch(cls, sketch, survey, elevation):
        self = cls()
        key = lambda n: n if '@' in n else f'{n}@{survey}'
        for n, p in sketch.positions().items():
            self.pos[key(n)] = p
        for a, b, *_ in sketch.legs():
            self.legs[key(a)].add(key(b))
            self.legs[key(b)].add(key(a))
        for n, p, end in sketch.splays():
            dx, dy = end[0] - p[0], end[1] - p[1]
            if not elevation:
                self.ends[key(n)].append((dx, dy))
            elif math.degrees(math.atan2(abs(dy), abs(dx))) >= STEEP:
                table = self.up if dy > 0 else self.down
                table[key(n)] = max(table.get(key(n), 0.0), abs(dy))
        return self

    @classmethod
    def from_database(cls, path=SQL):
        """From Therion's database export, in the cave's coordinates (for
        work across surveys: joins, projected)."""
        self = cls()
        db = sqlite3.connect(':memory:')
        db.executescript(sql_text(open(path, encoding='utf-8', errors='replace').read()))
        surveys = {i: n for i, n in db.execute('select ID, NAME from SURVEY')}
        st = {}
        xyz = {}
        for i, name, sv, x, y, z in db.execute('select ID, NAME, SURVEY_ID, X, Y, Z from STATION'):
            st[i] = (f'{name}@{surveys.get(sv, "")}', z)
            xyz[i] = (x, y, z)
        spl = {s for s, f in db.execute('select SHOT_ID, FLAG from SHOT_FLAG') if f == 'spl'}
        self.pos = {st[i][0]: xyz[i][:2] for i in st}
        for sid, a, b, grad in db.execute('select ID, FROM_ID, TO_ID, GRADIENT from SHOT'):
            if a not in st or b not in st:
                continue
            (na, za), (nb, zb) = st[a], st[b]
            if sid in spl:
                # the named end is the station
                if na.startswith(('-@', '.@')):
                    na, za, zb, grad = nb, zb, za, -grad
                    a, b = b, a
                self.ends[na].append((xyz[b][0] - xyz[a][0], xyz[b][1] - xyz[a][1]))
                dz = zb - za
                if grad >= STEEP:
                    self.up[na] = max(self.up.get(na, 0.0), dz)
                elif grad <= -STEEP:
                    self.down[na] = max(self.down.get(na, 0.0), -dz)
            else:
                self.legs[na].add(nb)
                self.legs[nb].add(na)
        return self


@functools.lru_cache(maxsize=None)
def _drawing_splays(th2, survey):
    from . import xvi
    from .reviewzip import backdrops
    if not os.path.exists(th2):                 # a drawing not written yet: no survey data
        return Splays()
    text = open(th2, encoding='utf-8', errors='replace').read()
    survey = survey or _survey_of(th2)
    elevation = re.search(r'(?m)^scrap \S+.*-projection (extended|elevation|\[)', text) is not None
    for rel in backdrops(text):
        f = os.path.join(os.path.dirname(th2), rel)
        if rel.lower().endswith('.xvi') and os.path.exists(f):
            return Splays.from_sketch(xvi.read(f), survey, elevation)
    return Splays()


def _wall_lines(objs):
    out = []
    for o in objs:
        if o.kind == 'line' and o.head.startswith('line wall') and '-subtype invisible' not in o.head:
            pts = bezier_points(o.segments())
            if len(pts) > 1:
                out.append(pts)
    return out


def splay_fill(objs, K, splays, survey):
    """The passage as the splays and nearby walls have it, or None."""
    stations = {}
    for o in objs:
        m = re.match(r'point (\S+) (\S+) station\b.*-name (\S+)', o.head) if o.kind == 'point' else None
        if m:
            n = m.group(3)
            stations[n if '@' in n else f'{n}@{survey}'] = (float(m.group(1)), float(m.group(2)))
    if len(stations) < 2:
        return None
    walls = _wall_lines(objs)
    segs = [(a, b) for w in walls for a, b in zip(w, w[1:]) if abs(b[0] - a[0]) > 1e-6]

    def walls_at(x):
        return [a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0])
                for a, b in segs if min(a[0], b[0]) <= x <= max(a[0], b[0])]

    def side(n, table):
        return table.get(n)

    boxes, beyond = [], []
    legs = {tuple(sorted((a, b))) for a in stations for b in splays.legs.get(a, ()) if b in stations}
    for a, b in legs:
        A, B = stations[a], stations[b]
        if abs(B[0] - A[0]) < 0.05 * K:
            continue
        upA, upB = side(a, splays.up), side(b, splays.up)
        dnA, dnB = side(a, splays.down), side(b, splays.down)
        n = max(1, int(abs(B[0] - A[0]) / (0.2 * K)))
        above, below = [], []
        for i in range(n + 1):
            t = i / n
            x = A[0] + (B[0] - A[0]) * t
            y = A[1] + (B[1] - A[1]) * t
            ys = walls_at(x)

            def reach(lo, hi, known):
                return [v for v in ys if lo <= v <= hi], known

            # up
            ups = [u for u in (upA if t < 1 else None, upB if t > 0 else None) if u is not None]
            if ups:
                r = (upA if upA is not None else upB) * (1 - t) + (upB if upB is not None else upA) * t
                cand = [v for v in ys if y < v <= y + (r + NEAR) * K]
                top = min(cand) if cand else y + r * K
            else:
                cand = [v for v in ys if y < v <= y + REACH * K]
                top = min(cand) if cand else y + DEFAULT * K
            # down
            dns = [u for u in (dnA if t < 1 else None, dnB if t > 0 else None) if u is not None]
            if dns:
                r = (dnA if dnA is not None else dnB) * (1 - t) + (dnB if dnB is not None else dnA) * t
                cand = [v for v in ys if y - (r + NEAR) * K <= v < y]
                bot = max(cand) if cand else y - r * K
            else:
                cand = [v for v in ys if y - REACH * K <= v < y]
                bot = max(cand) if cand else y - DEFAULT * K
            boxes.append(box(x - 0.12 * K, bot, x + 0.12 * K, top))
            # what the splays rule out: well above the roof and below the floor
            if ups:
                above.append((x, top + NEAR * K))
            if dns:
                below.append((x, bot - NEAR * K))
        for edge, far in ((above, 50 * K), (below, -50 * K)):
            if len(edge) > 1:
                edge.sort()
                beyond.append(Polygon(edge + [(edge[-1][0], edge[-1][1] + far), (edge[0][0], edge[0][1] + far)]).buffer(0))
    if not boxes:
        return None
    band = unary_union(boxes).buffer(0.25 * K, join_style=1).buffer(-0.25 * K, join_style=1)
    # and whatever the walls close in on their own
    closed = unary_union([LineString(w) for w in walls]).buffer(0.6 * K, join_style=1).buffer(-0.6 * K, join_style=1)
    g = unary_union([band, closed]).buffer(0)
    parts = sorted(getattr(g, 'geoms', [g]), key=lambda p: -p.area)
    return (parts[0], unary_union(beyond)) if parts else None


def redo_scrap(header, body, splays, survey, map_scale=200):
    K = scale_of(header)
    objs = parse_scrap(body)
    old = [o for o in objs if o.kind == 'line' and o.head.startswith('line wall') and '-subtype invisible' in o.head]
    if not old:
        return None
    old_poly = None
    try:
        ring = []
        for o in objs:
            if o.kind == 'line' and o.head.startswith('line wall') and '-outline none' not in o.head:
                ring.append(LineString(bezier_points(o.segments())))
        from shapely.ops import polygonize
        faces = list(polygonize(unary_union(ring)))
        old_poly = max(faces, key=lambda f: f.area) if faces else None
    except Exception:
        old_poly = None
    got = splay_fill(objs, K, splays, survey)
    if got is None or got[0].is_empty:
        return None
    band, beyond = got
    if old_poly is not None:
        # keep the drawing's own fill where the splays allow it, cut what
        # they rule out (the reach boxes), and fill the bites from the band
        F = unary_union([old_poly.difference(beyond), band]).buffer(0)
        if F.geom_type != 'Polygon':
            F = max(F.geoms, key=lambda g: g.area)
    else:
        F = band
    # back to the converter's form: walls with no outline and one closed fill line
    rest = []
    for o in objs:
        if o.kind == 'line' and o.head.startswith('line wall'):
            if '-subtype invisible' in o.head:
                continue
            if '-outline none' not in o.head:
                o.head = 'line wall -outline none'
        rest.append(o)
    ring_obj = Obj('line', 'line wall -subtype invisible -close on', [])
    ring_obj.set_segments([[x, y] for x, y in list(F.exterior.coords)[:-1]])
    rest = rest[:1] + [ring_obj] + rest[1:]
    return tidy.tidy_scrap(header, '\n'.join(o.text() for o in rest), map_scale, True)


def redo_file(path, splays=None, map_scale=200):
    raw = open(path, 'rb').read()
    t = raw.decode('utf-8').replace('\r\n', '\n')
    survey = _survey_of(path)
    splays = splays or Splays.from_drawing(path, survey)
    out, pos, done = [], 0, []
    for m in re.finditer(r'^(scrap (\S+)[^\n]*)\n(.*?)^endscrap', t, re.S | re.M):
        header, name, body = m.group(1), m.group(2), m.group(3)
        if '-projection extended' not in header:
            continue
        new = redo_scrap(header, body, splays, survey, map_scale)
        if new is None:
            continue
        out.append(t[pos:m.start(3)] + new.rstrip('\n') + '\n')
        pos = m.end(3)
        done.append(name)
    out.append(t[pos:])
    t = ''.join(out)
    if b'\r\n' in raw:
        t = t.replace('\n', '\r\n')
    open(path, 'wb').write(t.encode('utf-8'))
    return done


# -- plan ---------------------------------------------------------------------------

def plan_redo_scrap(header, body, splays, survey, map_scale=500):
    """The same for a plan scrap: the passage along each leg is the hull of
    its two stations and their splay ends. Fill well outside that is cut
    where it is a guess (mostly bounded by invisible outline, not walls),
    and the hull fills in where the fill falls short of it across
    invisible outline."""
    from shapely.geometry import MultiPoint, Point
    from shapely.ops import polygonize
    from .survey import fit as _fit
    K = scale_of(header)
    objs = parse_scrap(body)
    if not any(o.kind == 'line' and o.head.startswith('line wall') and '-subtype invisible' in o.head for o in objs):
        return None
    stations = {}
    for o in objs:
        m = re.match(r'point (\S+) (\S+) station\b.*-name (\S+)', o.head) if o.kind == 'point' else None
        if m:
            n = m.group(3)
            stations[n if '@' in n else f'{n}@{survey}'] = (float(m.group(1)), float(m.group(2)))
    pairs = [(xy, splays.pos[n]) for n, xy in stations.items() if n in splays.pos]
    if len(pairs) < 2:
        return None
    to_scrap = _fit([(b, a) for a, b in pairs])
    hulls = []
    for a in stations:
        for b in splays.legs.get(a, ()):
            if b not in stations or a > b:
                continue
            pts = [stations[a], stations[b]]
            for n in (a, b):
                g = splays.pos.get(n)
                if g is None:
                    continue
                for dx, dy in splays.ends.get(n, ()):
                    pts.append(to_scrap((g[0] + dx, g[1] + dy)))
            h = MultiPoint(pts).convex_hull
            if h.geom_type == 'Polygon':
                hulls.append(h)
    if not hulls:
        return None
    band = unary_union(hulls).buffer(0.2 * K, join_style=1).buffer(-0.2 * K, join_style=1)
    outline = [LineString(bezier_points(o.segments())) for o in objs
               if o.kind == 'line' and o.head.startswith('line wall') and '-outline none' not in o.head
               and len(o.segments()) > 1]
    faces = list(polygonize(unary_union(outline)))
    if not faces:
        return None
    old_poly = max(faces, key=lambda f: f.area)
    walls = unary_union([LineString(bezier_points(o.segments())) for o in objs
                         if o.kind == 'line' and o.head.startswith('line wall') and '-subtype invisible' not in o.head
                         and len(o.segments()) > 1]).buffer(0.05 * K)

    def walled(piece, other):
        """How much of what `piece` shares with `other` is drawn wall."""
        shared = piece.boundary.intersection(other.boundary.buffer(0.02 * K))
        return shared.intersection(walls).length / shared.length if shared.length else 1.0

    F = old_poly
    extra = old_poly.difference(band.buffer(NEAR_PLAN * K, join_style=1)).buffer(0)
    for c in getattr(extra, 'geoms', [extra]):
        if c.is_empty or c.area < (0.2 * K) ** 2:
            continue
        rest = F.difference(c).buffer(0)
        if walled(c, rest) < 0.3 and c.boundary.intersection(walls).length < 0.3 * c.boundary.length:
            F = rest
    if F.geom_type != 'Polygon':
        F = max(F.geoms, key=lambda g: g.area)
    more = band.difference(F).buffer(0)
    for c in getattr(more, 'geoms', [more]):
        if c.is_empty or c.area < (0.2 * K) ** 2:
            continue
        if c.distance(F) < 0.02 * K and walled(c, F) < 0.3:
            F = unary_union([F, c]).buffer(0)
    if F.geom_type != 'Polygon':
        F = max(F.geoms, key=lambda g: g.area)
    rest = []
    for o in objs:
        if o.kind == 'line' and o.head.startswith('line wall'):
            if '-subtype invisible' in o.head:
                continue
            if '-outline none' not in o.head:
                o.head = 'line wall -outline none'
        rest.append(o)
    ring_obj = Obj('line', 'line wall -subtype invisible -close on', [])
    ring_obj.set_segments([[x, y] for x, y in list(F.exterior.coords)[:-1]])
    rest = rest[:1] + [ring_obj] + rest[1:]
    return tidy.tidy_scrap(header, '\n'.join(o.text() for o in rest), map_scale, False)


def plan_redo_file(path, splays=None, only=None, map_scale=500):
    raw = open(path, 'rb').read()
    t = raw.decode('utf-8').replace('\r\n', '\n')
    survey = _survey_of(path)
    splays = splays or Splays.from_drawing(path, survey)
    out, pos, done = [], 0, []
    for m in re.finditer(r'^(scrap (\S+)[^\n]*)\n(.*?)^endscrap', t, re.S | re.M):
        header, name, body = m.group(1), m.group(2), m.group(3)
        if '-projection plan' not in header or (only and name not in only):
            continue
        new = plan_redo_scrap(header, body, splays, survey, map_scale)
        if new is None:
            continue
        out.append(t[pos:m.start(3)] + new.rstrip('\n') + '\n')
        pos = m.end(3)
        done.append(name)
    out.append(t[pos:])
    t = ''.join(out)
    if b'\r\n' in raw:
        t = t.replace('\n', '\r\n')
    open(path, 'wb').write(t.encode('utf-8'))
    return done
