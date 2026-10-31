# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""The local scale of a drawing: how long the survey legs are around a point.

Whoever draws or checks a scrap zooms so that the legs fit the screen,
so how closely a line needs to follow the sketch, and how many control
points it needs, goes with the length of the legs nearby rather than a
fixed distance ([convert] wall_tol_rel and line_tol_rel).

    from . import scale
    scale.use([((x1, y1), (x2, y2)), ...], K, stations)   # legs, in drawing units; K units per metre
    scale.at((x, y))                              # metres: mean length of the 3 nearest legs, or None

With [convert] tol_by_size, the scale for tolerances is the size the
sketch was zoomed to fit instead (as `size` below, from the passage at
the stations given to `use`).

Sizes of marks in a sketch (boulders, dashes and the gaps between them)
go with the size the sketch was zoomed to fit instead ([convert] size_ref):

    scale.use_splays(sketch)                      # passage size at each station (splays), and the legs
    scale.factor((x, y))                          # limits in metres are multiplied by this

The size is the geometric mean of the passage (splays) and the legs nearby.

(Not tried yet: the size of the strokes drawn nearby, which shows the zoom
directly, but is less sure where little is drawn.)
"""
import math
import statistics

from shapely.geometry import LineString, Point

NEAREST = 3

_legs = []          # [(LineString, length in drawing units)]
_K = 1.0
_stations = []      # [((x, y), passage size in metres)], in drawing units (use)
_sizes = []         # [((x, y), passage size in metres)], in sketch metres
_leg_lens = []      # [(LineString, length in metres)], the sketch's legs
FACTOR_MAX = 4.0    # marks are drawn at most this many times their size in a small passage


def use(legs, K=1.0, stations=()):
    """Set the legs (pairs of points) in the units the drawing uses, K per metre,
    and the passage size at stations [((x, y), metres)] in the same units."""
    global _legs, _K, _stations
    _legs = [(LineString([a, b]), LineString([a, b]).length) for a, b in legs if a != b]
    _K = K or 1.0
    _stations = list(stations)


def clear():
    use([])


def at(p):
    """Mean length, in metres, of the NEAREST legs closest to point p, or None without legs."""
    if not _legs:
        return None
    q = Point(p)
    near = sorted(_legs, key=lambda l: l[0].distance(q))[:NEAREST]
    return sum(L for _, L in near) / len(near) / _K


def passage_sizes(sketch):
    """{station: passage size in metres} of a sketch (xvi.Sketch): twice the
    median length of its splays as drawn."""
    lens = {}
    for n, p, end in sketch.splays():
        lens.setdefault(n, []).append(math.dist(p, end))
    return {n: 2 * statistics.median(v) for n, v in lens.items()}


def passages(sketch):
    """[((x, y), passage size in metres)] at the stations of a sketch, in its metres."""
    pos = sketch.positions()
    return [(pos[n], s) for n, s in passage_sizes(sketch).items() if n in pos]


def use_splays(sketch=None):
    """Passage size at each station of a sketch (xvi.Sketch, in metres) and
    the length of its legs. None clears them."""
    global _sizes, _leg_lens
    _sizes, _leg_lens = [], []
    if sketch is None:
        return
    _sizes = passages(sketch)
    _leg_lens = [(LineString([a, b]), math.dist(a, b)) for _, _, a, b in sketch.legs() if a != b]


def _passage(p, sizes=None):
    sizes = _sizes if sizes is None else sizes
    if not sizes:
        return None
    near = sorted(sizes, key=lambda s: math.dist(s[0], p))[:NEAREST]
    return sum(s for _, s in near) / len(near)


def _leg(p):
    if not _leg_lens:
        return None
    q = Point(p)
    near = sorted(_leg_lens, key=lambda l: l[0].distance(q))[:NEAREST]
    return sum(L for _, L in near) / len(near)


def size(p):
    """The size, in metres, the sketch at p was zoomed to fit: the geometric
    mean of the passage (splays at the NEAREST stations) and the legs nearby
    (passage size varies 5 to 15 times along a sketch, the legs about twice;
    passage or legs alone, the max or the plain mean did worse on Golgotha
    and Trident, 2026-10-30). None without either."""
    a, b = _passage(p), _leg(p)
    if a is None or b is None:
        return a or b
    return math.sqrt(a * b)


def factor(p):
    """How many times bigger than in a passage of [convert] size_ref the marks
    at p are drawn (the sketcher zooms to fit): 1 to FACTOR_MAX, 1 when off or
    without splays."""
    from .settings import SETTINGS
    s = size(p) if SETTINGS['size_ref'] else None
    return min(FACTOR_MAX, max(1.0, s / SETTINGS['size_ref'])) if s else 1.0


def tol(p, rel, absolute):
    """`rel` times the scale at p (metres), or `absolute` if rel is 0 or there
    are no legs. The scale is the legs nearby (`at`), or with [convert]
    tol_by_size the geometric mean of those and the passage at the nearest
    stations (as `size`)."""
    from .settings import SETTINGS
    s = at(p) if rel else None
    a = _passage(p, _stations) if s and SETTINGS['tol_by_size'] else None
    if a:
        s = math.sqrt(a * s)
    return rel * s if s else absolute


def use_scrap(objs, path, survey, K):
    """`use` the legs between the stations drawn in a scrap (tidy.parse_scrap
    objects) and the passage at them, from the sketch of the drawing at `path`
    (roofs.Splays), in its units (K per metre). Returns the legs."""
    import re
    from .roofs import Splays
    splays = Splays.from_drawing(path, survey)
    st = {}
    for o in objs:
        m = re.match(r'point (\S+) (\S+) station\b.*-name (\S+)', o.head) if o.kind == 'point' else None
        if m:
            n = m.group(3)
            st[n if '@' in n else f'{n}@{survey}'] = (float(m.group(1)), float(m.group(2)))
    legs = []
    for a, xy in st.items():
        for b in sorted(splays.legs.get(a, ())):     # (a set: the same order every run)
            if b in st and a < b:
                legs.append((xy, st[b]))
    use(legs, K, [(xy, splays.size[n]) for n, xy in st.items() if n in splays.size])
    return legs
