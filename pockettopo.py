# Ported from caves-mendip-swildons, tools/sketch2therion (commit 198bf46,
# https://github.com/paperclipmonkey/caves-mendip-swildons). GPLv3: see tools/LICENSE.
"""PocketTopo files: the binary .top and the Therion export (_th.txt).

Both are turned into a `Sketch` (see xvi.py), so PocketTopo sketches go
through the same conversion as SexyTopo ones. Cross sections become connect
lines from the station to the middle of the drawing, as SexyTopo writes them.
"""
import datetime
import math
import re
import struct

from .xvi import Sketch

COLOURS = {1: 'BLACK', 2: 'GRAY', 3: 'BROWN', 4: 'BLUE', 5: 'RED', 6: 'GREEN', 7: 'ORANGE'}


# -- the .top binary format --------------------------------------------------

class _Reader:
    def __init__(self, path):
        self.b = open(path, 'rb').read()
        if self.b[:3] != b'Top':
            raise ValueError(f"{path} is not a PocketTopo .top file")
        self.o = 4

    def rd(self, fmt):
        v = struct.unpack_from('<' + fmt, self.b, self.o)
        self.o += struct.calcsize('<' + fmt)
        return v if len(v) > 1 else v[0]

    def string(self):
        n = s = 0
        while True:
            c = self.b[self.o]
            self.o += 1
            n |= (c & 0x7f) << s
            s += 7
            if not c & 0x80:
                break
        t = self.b[self.o:self.o + n].decode('latin-1')
        self.o += n
        return t


def _station_id(v):
    if v == 0x80000000:
        return None
    if v & 0x80000000:
        return str(v & 0x7fffffff)
    return f"{v >> 16}.{v & 0xffff}"


def read_top(path):
    """{'trips': [(date, comment, declination)], 'shots': [(from, to, tape,
    compass, clino, flipped, trip, comment)], 'drawings': [plan, elevation]}.
    Each drawing is {'lines': [(COLOUR, pts)], 'sections': [(station, x, y)]}
    in metres with y down, as PocketTopo stores them."""
    r = _Reader(path)
    trips = []
    for _ in range(r.rd('i')):
        t = r.rd('q')
        c = r.string()
        d = r.rd('h')
        trips.append(((datetime.datetime(1, 1, 1) + datetime.timedelta(microseconds=t / 10)).date(),
                      c, d * 360 / 65536))
    shots = []
    for _ in range(r.rd('i')):
        f, t = r.rd('i') & 0xffffffff, r.rd('i') & 0xffffffff
        dist = r.rd('i') / 1000
        az = r.rd('H') * 360 / 65536
        inc = r.rd('h') * 360 / 65536
        flags = r.rd('B')
        r.rd('B')
        trip = r.rd('h')
        com = r.string() if flags & 2 else ''
        shots.append((_station_id(f), _station_id(t), dist, az, inc, bool(flags & 1), trip, com))
    for _ in range(r.rd('i')):          # references (fixed points)
        r.rd('I'); r.rd('q'); r.rd('q'); r.rd('i'); r.string()
    r.rd('i'); r.rd('i'); r.rd('i')    # overview mapping
    drawings = []
    for _ in range(2):
        r.rd('i'); r.rd('i'); r.rd('i')
        lines, sections = [], []
        while True:
            t = r.rd('B')
            if t == 0:
                break
            if t == 1:
                n = r.rd('i')
                pts = [(r.rd('i') / 1000, r.rd('i') / 1000) for _ in range(n)]
                lines.append((COLOURS.get(r.rd('B'), 'BLACK'), pts))
            elif t == 3:
                x, y = r.rd('i') / 1000, r.rd('i') / 1000
                sid = r.rd('I')
                r.rd('i')
                sections.append((_station_id(sid), x, y))
            else:
                raise ValueError(f"unknown drawing element {t} in {path}")
        drawings.append({'lines': lines, 'sections': sections})
    return {'trips': trips, 'shots': shots, 'drawings': drawings}


def average(shots):
    """Legs with repeat and back-sighted shots averaged, as PocketTopo's own
    export does: [('leg'|'splay', from, to, tape, compass, clino, flipped, comment)]."""
    out, idx = [], {}
    for f, t, d, az, inc, flip, trip, com in shots:
        if t is None:
            out.append(['splay', f, None, [(d, az, inc)], flip, com])
            continue
        key = frozenset((f, t))
        if key not in idx:
            idx[key] = len(out)
            out.append(['leg', f, t, [], flip, com])
        e = out[idx[key]]
        e[3].append((d, az, inc) if (f, t) == (e[1], e[2]) else (d, (az + 180) % 360, -inc))
        if com and not e[5]:
            e[5] = com
    res = []
    for kind, f, t, r, flip, com in out:
        d = sum(x[0] for x in r) / len(r)
        sx = sum(math.sin(math.radians(x[1])) for x in r)
        cx = sum(math.cos(math.radians(x[1])) for x in r)
        az = math.degrees(math.atan2(sx, cx)) % 360 if d > 0 else 0.0
        res.append((kind, f, t, d, az, sum(x[2] for x in r) / len(r), flip, com))
    return res


def _layout(legs, start, step):
    pos = {start: (0.0, 0.0)}
    changed = True
    while changed:
        changed = False
        for _, f, t, d, az, inc, flip, _c in legs:
            dx, dy = step(d, az, inc, flip)
            if f in pos and t not in pos:
                pos[t] = (pos[f][0] + dx, pos[f][1] + dy)
                changed = True
            elif t in pos and f not in pos:
                pos[f] = (pos[t][0] - dx, pos[t][1] - dy)
                changed = True
    return pos


def _plan_step(d, az, inc, flip):
    h = d * math.cos(math.radians(inc))
    return h * math.sin(math.radians(az)), h * math.cos(math.radians(az))


def _ext_step(d, az, inc, flip):
    return d * math.cos(math.radians(inc)) * (-1 if flip else 1), d * math.sin(math.radians(inc))


def top_sketch(path, view='plan'):
    """A PocketTopo .top drawing as a Sketch (y up). The sketch's origin is the
    first leg's from-station, which is where PocketTopo puts it."""
    top = read_top(path)
    rows = average(top['shots'])
    legs = [r for r in rows if r[0] == 'leg']
    if not legs:
        raise ValueError(f"{path} has no legs")
    start = legs[0][1]
    step = _plan_step if view == 'plan' else _ext_step
    pos = _layout(legs, start, step)
    shots = [(pos[f], pos[t]) for _, f, t, *_ in legs if f in pos and t in pos]
    for _, f, _t, d, az, inc, flip, _c in rows:
        if _ == 'splay' and f in pos:
            dx, dy = step(d, az, inc, flip)
            if view != 'plan':
                # a splay in the side view: its own direction along the passage
                dx = d * math.cos(math.radians(inc)) * (-1 if flip else 1)
            shots.append((pos[f], (pos[f][0] + dx, pos[f][1] + dy)))
    dr = top['drawings'][0 if view == 'plan' else 1]
    lines = [(c, [(x, -y) for x, y in pp]) for c, pp in dr['lines']]
    stations = {n: [p] for n, p in pos.items()}
    connects = []
    for n, x, y in dr['sections']:
        if n in pos:
            c = (x, -y)
            stations[n].append(c)
            connects.append((pos[n], c))
    return Sketch(stations, shots, lines, connects, path=path)


# -- the Therion export (_th.txt) ---------------------------------------------

def _section(lines, name):
    i = lines.index(name)
    end = len(lines)
    for j in range(i + 1, len(lines)):
        if lines[j] in ('ELEVATION', 'PLAN'):
            end = j
            break
    st, shots, polys = {}, [], []
    mode = cur = None
    for l in lines[i + 1:end]:
        l = l.strip()
        if not l:
            continue
        if l == 'STATIONS':
            mode = 'st'
            continue
        if l == 'SHOTS':
            mode = 'sh'
            continue
        if l.startswith('POLYLINE'):
            mode = 'pl'
            cur = (l.split()[1].upper(), [])
            polys.append(cur)
            continue
        p = l.split()
        if mode == 'st':
            st[p[2]] = (float(p[0]), float(p[1]))
        elif mode == 'sh':
            shots.append(((float(p[0]), float(p[1])), (float(p[2]), float(p[3]))))
        elif mode == 'pl':
            cur[1].append((float(p[0]), float(p[1])))
    return st, shots, polys


def th_txt_sketch(path, view='plan'):
    """A PocketTopo Therion export as a Sketch. In its ELEVATION section a
    cross section's station is listed at the cross section, and the CONNECT
    line runs back to where it is on the profile; in PLAN the station is in
    place and the CONNECT line runs out to the cross section."""
    lines = open(path, encoding='latin-1').read().replace('\r', '').splitlines()
    st, shots, polys = _section(lines, 'PLAN' if view == 'plan' else 'ELEVATION')
    stations = {n: [p] for n, p in st.items()}
    connects = []
    for c, pp in polys:
        if c != 'CONNECT' or len(pp) != 2:
            continue
        for n, p in st.items():
            for a, b in ((0, 1), (1, 0)):
                if math.dist(p, pp[a]) < 0.05:
                    real, centre = (p, pp[b]) if view == 'plan' else (pp[b], p)
                    stations[n] = [real, centre]
                    connects.append((real, centre))
    # in the side view, shots were listed from the moved station: put them back
    if view != 'plan':
        moved = {centre: real for real, centre in connects}
        fix = lambda q: next((r for c, r in moved.items() if math.dist(c, q) < 0.05), q)
        shots = [(fix(a), fix(b)) for a, b in shots]
    return Sketch(stations, shots, [(c, pp) for c, pp in polys if c != 'CONNECT' and pp],
                  connects, path=path)


def th_txt_extend(path):
    """Each leg's extended-elevation direction from a PocketTopo export:
    {(from, to): 'left'|'right'}."""
    out = {}
    txt = open(path, encoding='latin-1').read().replace('\r', '').split('\nPLAN')[0]
    for l in txt.splitlines():
        q = [x.strip() for x in l.split('\t')]
        if len(q) >= 6 and re.match(r'^\S+\.\S+$', q[0]) and re.match(r'^\S+\.\S+$', q[1]) \
                and q[5] in ('<', '>'):
            out.setdefault((q[0], q[1]), 'left' if q[5] == '<' else 'right')
    return out


def sketch(path, view='plan'):
    if path.lower().endswith('.top'):
        return top_sketch(path, view)
    return th_txt_sketch(path, view)
