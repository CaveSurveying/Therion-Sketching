# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see tools/LICENSE.
"""Therion's 3D model of a survey, as Loch shows it.

Therion 6.4 writes the passage walls it builds from the splays only to
its Loch file (`export model -fmt loch -enable walls -wall-source splays`);
its VRML, DXF and 3DMF exports carry the centreline alone. The Loch file
is a run of chunks, each a header of four uint32 (type, bytes of records,
number of records, bytes of data), the records, then the data the
records point into (lxFile in Therion's source):

    1 survey   id, name (pos, size), title (pos, size), parent
    2 station  id, survey, name, comment, flags, x y z (double)
    3 shot     from, to, two sections, flags, type, survey, threshold
    4 scrap    id, survey, points (n, pos, size), triangles (n, pos, size)

    model = read(path)          # .stations {name: (x, y, z)}, .legs [(a, b)], .triangles [((x,y,z)*3)]
    model = export(th, survey)  # runs therion on the survey alone
"""
import os
import struct
import subprocess
import tempfile


class Model:
    def __init__(self):
        self.stations = {}      # name -> (x, y, z), metres: x east, y north, z up
        self.legs = []          # [(name, name)]
        self.triangles = []     # [((x, y, z), (x, y, z), (x, y, z))]


def read(path):
    raw = open(path, 'rb').read()
    m = Model()
    names, by_id = {}, {}
    i = 0
    while i + 16 <= len(raw):
        typ, rsize, rcount, dsize = struct.unpack_from('<4I', raw, i)
        rec = raw[i + 16:i + 16 + rsize]
        data = raw[i + 16 + rsize:i + 16 + rsize + dsize]
        i += 16 + rsize + dsize
        if not rcount:
            continue
        step = rsize // rcount
        text = lambda pos, size: data[pos:pos + size].split(b'\0')[0].decode('utf-8', 'replace')
        for k in range(rcount):
            r = rec[k * step:(k + 1) * step]
            if typ == 1:                                # survey
                sid, npos, nsize = struct.unpack_from('<3I', r)
                names[sid] = text(npos, nsize)
            elif typ == 2:                              # station
                sid, surv, npos, nsize = struct.unpack_from('<4I', r)
                x, y, z = struct.unpack_from('<3d', r, step - 24)
                n = text(npos, nsize)
                by_id[sid] = n
                m.stations[n] = (x, y, z)
            elif typ == 3:                              # shot
                a, b = struct.unpack_from('<2I', r)
                m.legs.append((a, b))
            elif typ == 4:                              # scrap: points and triangles
                _sid, _surv, npts, ppos, psize, ntri, tpos, tsize = struct.unpack_from('<8I', r)
                pts = [struct.unpack_from('<3d', data, ppos + 24 * j) for j in range(npts)]
                for j in range(ntri):
                    a, b, c = struct.unpack_from('<3I', data, tpos + 12 * j)
                    if max(a, b, c) < npts:
                        m.triangles.append((pts[a], pts[b], pts[c]))
    real = lambda n: n and n not in ('-', '.')     # splay ends are unnamed
    m.legs = [(by_id[a], by_id[b]) for a, b in m.legs if real(by_id.get(a)) and real(by_id.get(b))]
    m.stations = {n: p for n, p in m.stations.items() if real(n)}
    return m


def export(th, survey=None):
    """The model of a .th file (a survey on its own), walls from its splays."""
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, 'm.lox')
        with open(os.path.join(tmp, 'm.thcfg'), 'w', encoding='utf-8') as f:
            f.write(f"encoding  utf-8\nsource {os.path.abspath(th)}\n"
                    f"export model -fmt loch -enable walls -wall-source splays -o m.lox\n")
        subprocess.run(['therion', '-l', 'm.log', 'm.thcfg'], cwd=tmp, capture_output=True)
        if not os.path.exists(out):
            raise RuntimeError(f"therion made no model of {th}")
        return read(out)
