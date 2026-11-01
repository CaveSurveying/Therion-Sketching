# Ported from caves-mendip-swildons, tools/sketch2therion (commit 198bf46,
# https://github.com/paperclipmonkey/caves-mendip-swildons). GPLv3: see LICENSE.
"""Therion's own layout of the survey, read from its XVI export.

Therion lays the survey out itself, closing loops and (in an extended
elevation) breaking them where its extend flags say, so its station
positions are not the sketch's. A drawing keeps the sketch's positions
(Therion morphs each scrap onto its stations); Therion's are used only
to name the survey's stations (`check`) and to put the cave's drawings
in one frame (`joins`, `sections`, `review`).

Therion's layout comes from `tools/layout.thcfg`, which writes
output/layout-plan.xvi and output/layout-extended.xvi.
"""
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


def natural(n):
    return [int(x) if x.isdigit() else x for x in re.split(r'(\d+)', n)]


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
