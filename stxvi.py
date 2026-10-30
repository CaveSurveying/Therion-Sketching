# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""A plan xvi re-exported with its cross sections linked, as SexyTopo now does.

    python3 -m tools.sketch2therion stxvi X [--xvi PATH] [--out PATH]
    python3 -m tools.sketch2therion stxvi X --export plan|ee --out PATH

SexyTopo before 1.12 (TickleWest: 1.8.3) wrote a plan xvi without linking
its cross sections to the plan: the section's strokes are there, but not
the station drawn again at the section, its splays, or the `connect` line
from the station on the plan to the section. The converter finds a
section by that connect line. This adds, for each cross section in the
survey's `X.plan.json`, what the current exporter writes (the web version,
paperclipmonkey/sexytopo, kmp/shared/.../io/export/Xvi.kt):

- the station again at the section's place;
- its splays as a star, turned so the section's bearing points north and
  seen across it: across the passage is x, height is y
  (`CrossSection.getProjection`, `Projection2D.CROSS_SECTION`);
- `connect` from the station on the plan to the section's place.

The rest of the xvi is kept as it is. With --export, a whole xvi is written
from the SexyTopo files instead, the stations and shots laid out as SexyTopo
does (Space3DTransformer, and ...ForElevation for an extended elevation):
for an xvi exported before a leg was corrected (Century 46-47). Coordinates are SexyTopo's sketch
ones (metres, y down) times the xvi's scale, with y flipped.
"""
import argparse
import json
import math
import os
import re
import sys

from . import project as _project
from . import xvi

PROJECT = _project.load()


def _num(v):
    return f"{v + 0.0:.2f}"


def section_rows(plan, data, positions, scale):
    """(station rows, shot rows, connect rows) to add, one set per cross section."""
    splays = {}
    for st in data.get('stations', []):
        splays[st['name']] = [l for l in st.get('legs', []) if l.get('destination') == '-']
    stations, shots, connects = [], [], []
    for x in plan.get('x-sections', []):
        n = str(x['station-id'])
        px, py = x['location']['x'], x['location']['y']
        cx, cy = px * scale, -py * scale                      # the section's place in the xvi
        stations.append(f"\t {{{_num(cx)} {_num(cy)} {n}}}\n")
        angle = float(x.get('angle', 0.0))
        for leg in splays.get(n, []):
            d, az, inc = leg['distance'], math.radians(leg['azimuth'] - angle), math.radians(leg['inclination'])
            across, up = d * math.cos(inc) * math.sin(az), d * math.sin(inc)
            shots.append(f"\t {{{_num(cx)} {_num(cy)} {_num(cx + across * scale)} {_num(cy + up * scale)}}}\n")
        at = positions.get(n)
        if at is None:
            print(f"station {n}: not on the plan, no connect line", file=sys.stderr)
            continue
        connects.append(f"\t {{connect {_num(at[0])} {_num(at[1])} {_num(cx)} {_num(cy)}}}\n")
    return stations, shots, connects


def relink(text, plan, data):
    """The xvi text with the cross sections linked (unchanged if it already has connect lines)."""
    if re.search(r'\{\s*connect\b', text, re.I):
        return text, 0
    k = xvi.scale_of(text)
    stations = {}
    for e in xvi._entries(xvi._block(text, 'XVIstations')):
        if len(e) >= 3:
            stations.setdefault(e[2], []).append((float(e[0]), float(e[1])))
    positions = {n: ps[0] for n, ps in stations.items()}
    add_st, add_sh, add_cn = section_rows(plan, data, positions, k)
    for name, rows in (('XVIsketchlines', add_cn), ('XVIshots', add_sh), ('XVIstations', add_st)):
        span = xvi.block_span(text, name)
        if span is None:
            sys.exit(f"no {name} block in the xvi")
        end = span[1]
        text = text[:end] + ''.join(rows) + text[end:]
    return text, len(plan.get('x-sections', []))


def main(argv):
    p = argparse.ArgumentParser(prog='python3 -m tools.sketch2therion stxvi')
    p.add_argument('survey')
    p.add_argument('--xvi', help="the plan xvi (default: the backdrop of X's plan drawing)")
    p.add_argument('--out', help='where to write it (default: in place)')
    p.add_argument('--export', choices=('plan', 'ee'),
                   help='write a whole new xvi from the SexyTopo files instead (needs --out)')
    a = p.parse_args(argv)
    from .survey import survey_sketch
    th = PROJECT.path(PROJECT.survey_file(a.survey))
    plan_xvi = survey_sketch(th, 'plan')
    # SexyTopo writes its files beside its sketches: beside the plan xvi, else the .th
    where = next((d for d in (os.path.dirname(a.xvi or plan_xvi or th), os.path.dirname(th))
                  if os.path.exists(os.path.join(d, f'{a.survey}.data.json'))), None)
    if a.export:
        if not a.out:
            sys.exit('--export needs --out')
        if not where:
            sys.exit(f"{a.survey}: no {a.survey}.data.json")
        data = load_json(os.path.join(where, f'{a.survey}.data.json'))
        sketch = load_json(os.path.join(where, f'{a.survey}.{"plan" if a.export == "plan" else "ext-elevation"}.json'))
        open(a.out, 'w', encoding='utf-8', newline='').write(export(sketch, data, a.export))
        print(f"wrote {a.out}: the {a.export} from {a.survey}'s SexyTopo files")
        return
    path = a.xvi or plan_xvi
    if not path:
        sys.exit(f"{a.survey}: no plan drawing in {th} with an xvi as its backdrop (or give --xvi)")
    plan_json = os.path.join(where, f'{a.survey}.plan.json') if where else None
    if not plan_json or not os.path.exists(plan_json):
        sys.exit(f"{a.survey}: no {a.survey}.plan.json")
    plan = json.load(open(plan_json, encoding='utf-8'))
    data = json.load(open(plan_json.replace('.plan.json', '.data.json'), encoding='utf-8'))
    text = open(path, encoding='utf-8', newline='').read()
    out, n = relink(text, plan, data)
    if out is text:
        print(f"{path}: already has connect lines, left as it is")
        return
    target = a.out or path
    open(target, 'w', encoding='utf-8', newline='').write(out)
    print(f"wrote {target}: {n} cross sections linked to the plan")


# -- a whole xvi from the SexyTopo files (as the current exporter writes it) -------------------

def _cart(at, d, az, inc):
    """SexyTopo's toCartesian: (east, north, up) from a leg's distance, azimuth and inclination."""
    az, inc = math.radians(az), math.radians(inc)
    return (at[0] + d * math.cos(inc) * math.sin(az), at[1] + d * math.cos(inc) * math.cos(az),
            at[2] + d * math.sin(inc))


def layout(data, view):
    """(stations {name: (x, y)}, shots [((x, y), (x, y))]) in metres, y up, for view 'plan' or
    'ee', walked from the first station as SexyTopo's Space3DTransformer and
    Space3DTransformerForElevation do (an extended elevation unrolls each leg right, left or
    upright by its destination's eeDirection, and turns the splays with it)."""
    by = {st['name']: st for st in data['stations']}
    root = data['stations'][0]['name']
    pts, shots = {}, []
    pending = [(root, (0.0, 0.0, 0.0), 0.0)]
    to2d = (lambda c: (c[1], c[2])) if view == 'ee' else (lambda c: (c[0], c[1]))
    while pending:
        name, at, rot = pending.pop()
        if name in pts:
            continue
        pts[name] = to2d(at)
        for leg in reversed(by.get(name, {}).get('legs', [])):
            d, az, inc = leg['distance'], leg['azimuth'], leg['inclination']
            dest = leg['destination']
            if dest != '-':
                if view == 'ee':
                    paz = {'right': 0.0, 'left': 180.0, 'vertical': 90.0}.get(
                        str(by.get(dest, {}).get('eeDirection', 'right')).lower(), 0.0)
                    end = _cart(at, d, paz, inc)
                    pending.append((dest, end, paz - az))
                else:
                    end = _cart(at, d, az, inc)
                    pending.append((dest, end, 0.0))
            else:
                end = _cart(at, d, az + rot, inc)
            shots.append((to2d(at), to2d(end)))
    return pts, shots


def export(sketch, data, view, scale=78.74016):
    """A whole xvi: stations, shots (legs and splays), the sketch's strokes, and each cross
    section's station, splays and connect line. Labels and symbols are not drawn."""
    pts, shots = layout(data, view)
    px = lambda p: (p[0] * scale, p[1] * scale)
    st = [f"\t {{{_num(px(p)[0])} {_num(px(p)[1])} {n}}}\n" for n, p in pts.items()]
    sh = [f"\t {{{_num(px(a)[0])} {_num(px(a)[1])} {_num(px(b)[0])} {_num(px(b)[1])}}}\n" for a, b in shots]
    sl = []
    for path in sketch.get('paths', []):
        v = []
        for q in path['points']:
            v += [_num(q['x'] * scale), _num((-q['y'] + 0.0) * scale)]
        sl.append(f"\t {{{path['colour']} {' '.join(v)}}}\n")
    a_st, a_sh, a_cn = section_rows(sketch, data, {n: px(p) for n, p in pts.items()}, scale)
    xs = [x for p in pts.values() for x in (p[0],)] or [0.0]
    ys = [p[1] for p in pts.values()] or [0.0]
    left, bottom = (math.floor(min(xs)) - 5) * scale, (math.floor(min(ys)) - 5) * scale
    nx, ny = int(max(xs) - min(xs)) + 11, int(max(ys) - min(ys)) + 11
    return ("set XVIgrids {1 m}\n"
            "set XVIstations {\n" + "".join(st + a_st) + "}\n"
            "set XVIshots {\n" + "".join(sh + a_sh) + "}\n"
            "set XVIsketchlines {\n" + "".join(sl + a_cn) + "}\n"
            f"set XVIgrid {{{left:.4f} {bottom:.4f} {scale} 0.0 0.0 {scale} {nx}.0 {ny}.0}}\n")


def load_json(path):
    """A SexyTopo JSON file; anything after its closing brace (a longer file's leftover tail,
    Century.ext-elevation.json) is ignored, with a warning."""
    text = open(path, encoding='utf-8').read()
    obj, end = json.JSONDecoder().raw_decode(text)
    if text[end:].strip():
        print(f"{path}: {len(text[end:].strip())} characters after the JSON ignored (a damaged save?)", file=sys.stderr)
    return obj
