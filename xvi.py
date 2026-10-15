# Ported from caves-mendip-swildons, tools/sketch2therion (commit 198bf46,
# https://github.com/paperclipmonkey/caves-mendip-swildons). GPLv3: see tools/LICENSE.
"""XVI sketch files: xTherion's backdrop format, written by SexyTopo, PocketTopo
and Therion itself.

An XVI file has four lists:

    set XVIgrids {1.0 m}                      the size of one grid cell
    set XVIstations { {x y name} ... }        station positions
    set XVIshots { {x1 y1 x2 y2} ... }        legs and splays
    set XVIsketchlines { {colour x y x y ...} ... }
    set XVIgrid {x0 y0 dx1 dy1 dx2 dy2 nx ny} the grid, which gives the scale

Coordinates are in drawing units with y pointing up (north on a plan). The
units per metre differ: PocketTopo writes 39.37, SexyTopo 78.74 and Therion
19.685 at its default scale. They are read here from XVIgrid and everything
is converted to metres.

Cross sections: both SexyTopo and PocketTopo draw a cross section in the same
file as the sketch, list its station a second time at the cross section, and
join the two with a `connect` sketch line. Which end of the connect line is
the station depends on the program, so `Sketch.sections()` works it out from
the legs.
"""
import math
import re
from dataclasses import dataclass, field


@dataclass
class Sketch:
    stations: dict            # name -> [(x, y), ...] in metres
    shots: list               # [((x1, y1), (x2, y2))]
    lines: list               # [(COLOUR, [(x, y), ...])], colour upper case
    connects: list = field(default_factory=list)   # [((x1, y1), (x2, y2))]
    scale: float = 39.37007874                      # file units per metre
    path: str = ''

    # -- stations ----------------------------------------------------------
    def legs(self):
        """Shots joining two different stations, as (name_a, name_b, pa, pb)."""
        at = self._index()
        out = []
        for a, b in self.shots:
            na, nb = at.get(_key(a)), at.get(_key(b))
            if na and nb and na != nb:
                out.append((na, nb, a, b))
        return out

    def splays(self):
        """Shots from a station that don't end at one: [(name, (x, y), end)]."""
        at = self._index()
        out = []
        for a, b in self.shots:
            na, nb = at.get(_key(a)), at.get(_key(b))
            if na and not nb:
                out.append((na, a, b))
            elif nb and not na:
                out.append((nb, b, a))
        return out

    def _index(self):
        return {_key(p): n for n, ps in self.stations.items() for p in ps}

    def positions(self):
        """Each station's place in the sketch: name -> (x, y). A station listed
        twice (once more at its cross section) is taken where its legs are."""
        leg_ends = {}
        at = self._index()
        for a, b in self.shots:
            na, nb = at.get(_key(a)), at.get(_key(b))
            if na and nb and na != nb:
                leg_ends.setdefault(na, set()).add(_key(a))
                leg_ends.setdefault(nb, set()).add(_key(b))
        out = {}
        for n, ps in self.stations.items():
            if len(ps) == 1:
                out[n] = ps[0]
                continue
            on_legs = [p for p in ps if _key(p) in leg_ends.get(n, ())]
            out[n] = on_legs[0] if on_legs else ps[0]
        return out

    def sections(self):
        """Cross sections drawn in this sketch: [(station, station_pos, centre)]."""
        pos = self.positions()
        out = []
        for a, b in self.connects:
            hit = None
            for n, p in pos.items():
                if math.dist(p, a) < 0.05:
                    hit = (n, p, b)
                elif math.dist(p, b) < 0.05:
                    hit = (n, p, a)
                if hit:
                    break
            if hit:
                out.append(hit)
        return out

    def flipped(self):
        """The same sketch upside down (y negated)."""
        f = lambda p: (p[0], -p[1])
        return Sketch({n: [f(p) for p in ps] for n, ps in self.stations.items()},
                      [(f(a), f(b)) for a, b in self.shots],
                      [(c, [f(p) for p in pp]) for c, pp in self.lines],
                      [(f(a), f(b)) for a, b in self.connects], self.scale, self.path)


def _key(p):
    return (round(p[0], 2), round(p[1], 2))


# -- reading -----------------------------------------------------------------

def block_span(txt, name):
    """(start, end) of the text inside `set NAME { ... }`, braces matched; None if absent."""
    m = re.search(r'set\s+' + name + r'\s*\{', txt)
    if not m:
        return None
    i = m.end()
    depth = 1
    j = i
    while j < len(txt) and depth:
        if txt[j] == '{':
            depth += 1
        elif txt[j] == '}':
            depth -= 1
        j += 1
    return i, j - 1


def _block(txt, name):
    """The text inside `set NAME { ... }`, braces matched."""
    span = block_span(txt, name)
    return txt[span[0]:span[1]] if span else ''


def _entries(block):
    return [e.split() for e in re.findall(r'\{([^{}]*)\}', block)]


def scale_of(txt):
    """Drawing units per metre, from XVIgrids and XVIgrid."""
    cell = 1.0
    m = re.search(r'set\s+XVIgrids\s*\{\s*([-\d.]+)\s*(\w*)\s*\}', txt)
    if m:
        cell = float(m.group(1))
        unit = m.group(2).lower()
        cell *= {'m': 1, 'cm': 0.01, 'ft': 0.3048, 'feet': 0.3048, 'in': 0.0254}.get(unit, 1)
    g = re.search(r'set\s+XVIgrid\s*\{([^}]*)\}', txt)
    if g:
        v = [float(x) for x in g.group(1).split()]
        if len(v) >= 4 and math.hypot(v[2], v[3]) > 0:
            return math.hypot(v[2], v[3]) / cell
    return 39.37007874 / cell


def _colour_map():
    """[convert] colour_map: purple read as black (a wall where passages overlap), red and orange
    as grey (Style.md, Sketching in SexyTopo)."""
    from .settings import SETTINGS
    return SETTINGS.get('colour_map') or {}


def read(path):
    txt = open(path, encoding='utf-8', errors='replace').read()
    s = scale_of(txt)
    m = lambda x: float(x) / s
    stations = {}
    for e in _entries(_block(txt, 'XVIstations')):
        if len(e) >= 3:
            stations.setdefault(e[2], []).append((m(e[0]), m(e[1])))
    shots = []
    for e in _entries(_block(txt, 'XVIshots')):
        if len(e) >= 4:
            shots.append(((m(e[0]), m(e[1])), (m(e[2]), m(e[3]))))
    lines, connects = [], []
    for e in _entries(_block(txt, 'XVIsketchlines')):
        if len(e) < 3:
            continue
        colour = e[0].upper()
        colour = {'GREY': 'GRAY'}.get(colour, colour)
        colour = _colour_map().get(colour, colour)
        try:
            v = [m(x) for x in e[1:]]
        except ValueError:
            continue
        pts = list(zip(v[0::2], v[1::2]))
        if colour == 'CONNECT':
            if len(pts) >= 2:
                connects.append((pts[0], pts[-1]))
        elif len(pts) >= 1:
            lines.append((colour, pts))
    return Sketch(stations, shots, lines, connects, s, path)


# -- writing -----------------------------------------------------------------

def write(sketch, path, scale=39.37007874):
    """Write a sketch as XVI. Cross sections are written the SexyTopo way: the
    station again at the cross section, and a connect line station -> section."""
    f = lambda v: f"{v * scale:.2f}"
    o = ["set XVIgrids {1.0 m}", "set XVIstations {"]
    for n, ps in sketch.stations.items():
        o += [f"  {{{f(x)} {f(y)} {n}}}" for x, y in ps]
    o += ["}", "set XVIshots {"]
    o += [f"  {{{f(a[0])} {f(a[1])} {f(b[0])} {f(b[1])}}}" for a, b in sketch.shots]
    o += ["}", "set XVIsketchlines {"]
    for c, pp in sketch.lines:
        o.append("  {" + c + "  " + "  ".join(f"{f(x)} {f(y)}" for x, y in pp) + "}")
    for a, b in sketch.connects:
        o.append(f"  {{CONNECT  {f(a[0])} {f(a[1])}  {f(b[0])} {f(b[1])}}}")
    pts = [p for _, pp in sketch.lines for p in pp] + \
          [p for ps in sketch.stations.values() for p in ps] or [(0, 0)]
    x0 = math.floor(min(p[0] for p in pts)) - 1
    y0 = math.floor(min(p[1] for p in pts)) - 1
    nx = math.ceil(max(p[0] for p in pts)) + 1 - x0
    ny = math.ceil(max(p[1] for p in pts)) + 1 - y0
    o += ["}", f"set XVIgrid {{{x0 * scale:.2f} {y0 * scale:.2f} {scale} 0.0 0.0 {scale} {nx} {ny}}}", ""]
    open(path, 'w', newline='\n').write("\n".join(o))
