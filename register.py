# Ported from caves-mendip-swildons, tools/sketch2therion (commit 198bf46,
# https://github.com/paperclipmonkey/caves-mendip-swildons). GPLv3: see LICENSE.
"""Therion's own layout of the survey, read from its database export or
an XVI export of a map.

Therion lays the survey out itself, closing loops and (in an extended
elevation) breaking them where its extend flags say, so its station
positions are not the sketch's. A drawing keeps the sketch's positions
(Therion morphs each scrap onto its stations); Therion's are used only
to put the cave's drawings in one frame (`joins`, `sections`,
`review`).

The cave's layout is Therion's database, which `tools/layout.thcfg`
exports (`build.sql` in tools/project.toml): `cave_layout()`.
"""
import os
import re
import statistics
import sys

from . import database, xvi


class Layout:
    """Therion's station positions in plan, in metres: from its database
    export (.sql) or an XVI export (stations named name@survey.parent...)."""

    def __init__(self, path):
        self.path = path
        self.by_name = {}          # (name, survey) -> [(x, y)]
        if path.lower().endswith('.sql'):
            for _, name, survey, x, y, _ in database.stations(database.connect(path)):
                if name not in ('-', '.', ''):          # splay ends
                    self.by_name.setdefault((name, survey), []).append((x, y))
            return
        for full, ps in xvi.read(path).stations.items():
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


def cave_layout():
    """The cave's layout, from Therion's database of the whole cave."""
    from . import project
    p = project.load()
    path = p.path(p.build['sql'])
    if not os.path.exists(path):
        sys.exit(f"{path} not found: run  therion -l output/therion-layout.log tools/layout.thcfg  first"
                 " (with the trip tied into the cave)")
    return Layout(path)


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
