# Ported from caves-mendip-swildons, tools/sketch2therion (commit 198bf46,
# https://github.com/paperclipmonkey/caves-mendip-swildons). GPLv3: see tools/LICENSE.
"""Fitting a sketch onto Therion's own layout of the survey.

Therion lays the survey out itself, closing loops and (in an extended
elevation) breaking them where its extend flags say. A sketch from the
phone was drawn on the phone's layout, which agrees with Therion's except
for a shift, unless loop closure or a different loop break moves some
stations. So each station's offset sketch -> Therion is worked out, and
stations whose offsets agree are grouped. One group means the sketch fits
as it is; several mean it must be split, one scrap per group, or Therion
will stretch the drawing between stations that have moved apart.

Therion's layout comes from `tools/layout.thconfig`, which writes
output/layout-plan.xvi and output/layout-extended.xvi.
"""
import math
import re
import statistics

from . import xvi


class Layout:
    """Therion's XVI export: stations named name@survey.parent... in metres."""

    def __init__(self, path):
        sk = xvi.read(path)
        self.path = path
        self.shots = sk.shots
        self.by_name = {}          # (name, survey) -> [(x, y)]
        for full, ps in sk.stations.items():
            name, _, where = full.partition('@')
            survey = where.split('.')[0] if where else ''
            self.by_name.setdefault((name, survey), []).extend(ps)

    def find(self, name, survey=None):
        """A station's positions: name@survey, else name in any survey if
        that is unambiguous."""
        if survey and (name, survey) in self.by_name:
            return self.by_name[(name, survey)]
        hits = [k for k in self.by_name if k[0] == name]
        if len(hits) == 1:
            return self.by_name[hits[0]]
        return []

    def surveys_of(self, name):
        return sorted(s for n, s in self.by_name if n == name)


def offsets(sketch, layout, survey=None):
    """{station: (dx, dy)} sketch -> Therion, for stations Therion places
    exactly once (an extended elevation can place a station several times)."""
    out = {}
    for n, p in sketch.positions().items():
        ps = {(round(x, 2), round(y, 2)) for x, y in layout.find(n, survey)}
        if len(ps) == 1:
            t = next(iter(ps))
            out[n] = (t[0] - p[0], t[1] - p[1])
    return out


def natural(n):
    return [int(x) if x.isdigit() else x for x in re.split(r'(\d+)', n)]


def groups(offs, tol=1.5):
    """Stations whose offsets agree within `tol` metres, biggest group first."""
    gs = []
    for n, o in sorted(offs.items(), key=lambda kv: natural(kv[0])):
        for g in gs:
            if math.dist(g['o'], o) < tol:
                g['s'].append(n)
                break
        else:
            gs.append({'o': o, 's': [n]})
    return [g['s'] for g in sorted(gs, key=lambda g: -len(g['s']))]


def spread(offs):
    """Median distance of the offsets from their median: 0 for a perfect fit."""
    if not offs:
        return None
    mx = statistics.median(o[0] for o in offs.values())
    my = statistics.median(o[1] for o in offs.values())
    return statistics.median(math.dist(o, (mx, my)) for o in offs.values())


def fit(sketch, layout, survey=None):
    """The sketch the right way up, and its offsets. A sketch that fits far
    better upside down is flipped (with a warning from `check`)."""
    a = offsets(sketch, layout, survey)
    f = sketch.flipped()
    b = offsets(f, layout, survey)
    sa, sb = spread(a), spread(b)
    if sa is not None and sb is not None and sb < 0.5 * sa and sb < 1.0:
        return f, b, True
    return sketch, a, False


def line_distance(sketch, colours=('BLACK',)):
    """Median distance from each station to the nearest sketch line of these
    colours. A few metres means the stations don't line up with the drawing
    (PocketTopo exports sometimes don't)."""
    from shapely.geometry import LineString, Point
    lines = [LineString(pp) for c, pp in sketch.lines if c in colours and len(pp) > 1]
    if not lines:
        return None
    ds = [min(l.distance(Point(p)) for l in lines) for p in sketch.positions().values()]
    return statistics.median(ds) if ds else None
