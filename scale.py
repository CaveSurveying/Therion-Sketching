# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""The local scale of a drawing: how long the survey legs are around a point.

Whoever draws or checks a scrap zooms so that the legs fit the screen,
so how closely a line needs to follow the sketch, and how many control
points it needs, goes with the length of the legs nearby rather than a
fixed distance ([convert] wall_tol_rel and line_tol_rel).

    from . import scale
    scale.use([((x1, y1), (x2, y2)), ...], K)   # legs, in drawing units; K units per metre
    scale.at((x, y))                              # metres: mean length of the 3 nearest legs, or None
"""
from shapely.geometry import LineString, Point

NEAREST = 3

_legs = []          # [(LineString, length in drawing units)]
_K = 1.0


def use(legs, K=1.0):
    """Set the legs (pairs of points) in the units the drawing uses, K per metre."""
    global _legs, _K
    _legs = [(LineString([a, b]), LineString([a, b]).length) for a, b in legs if a != b]
    _K = K or 1.0


def clear():
    use([])


def at(p):
    """Mean length, in metres, of the NEAREST legs closest to point p, or None without legs."""
    if not _legs:
        return None
    q = Point(p)
    near = sorted(_legs, key=lambda l: l[0].distance(q))[:NEAREST]
    return sum(L for _, L in near) / len(near) / _K


def tol(p, rel, absolute):
    """`rel` times the scale at p (metres), or `absolute` if rel is 0 or there are no legs."""
    s = at(p) if rel else None
    return rel * s if s else absolute


def legs_of_scrap(objs, path, survey):
    """The legs between the stations drawn in a scrap (tidy.parse_scrap objects)
    of the drawing at `path`, in its own units, from its sketch (roofs.Splays)."""
    import re
    from .roofs import Splays
    splays = Splays.from_drawing(path, survey)
    st = {}
    for o in objs:
        m = re.match(r'point (\S+) (\S+) station\b.*-name (\S+)', o.head) if o.kind == 'point' else None
        if m:
            n = m.group(3)
            st[n if '@' in n else f'{n}@{survey}'] = (float(m.group(1)), float(m.group(2)))
    out = []
    for a, xy in st.items():
        for b in splays.legs.get(a, ()):
            if b in st and a < b:
                out.append((xy, st[b]))
    return out
