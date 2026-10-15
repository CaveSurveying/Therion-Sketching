# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see tools/LICENSE.
"""A plan xvi re-exported with its cross sections linked, as SexyTopo now does.

    python3 -m tools.sketch2therion stxvi X [--xvi PATH] [--out PATH]

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

The rest of the xvi is kept as it is. Coordinates are SexyTopo's sketch
ones (metres, y down) times the xvi's scale, with y flipped.
"""
import argparse
import json
import math
import os
import re
import sys

from .. import project as _project
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
    p.add_argument('--xvi', help='the plan xvi (default: X/XVI/X.plan.xvi, X/X.plan.xvi, X/Notes/X.plan.xvi or X/Notes/XP.xvi)')
    p.add_argument('--out', help='where to write it (default: in place)')
    a = p.parse_args(argv)
    folder = os.path.dirname(PROJECT.path(PROJECT.survey_file(a.survey)))
    first = lambda names: next((q for q in names if os.path.exists(q)), None)
    path = a.xvi or first([os.path.join(folder, 'XVI', f'{a.survey}.plan.xvi'),
                           os.path.join(folder, f'{a.survey}.plan.xvi'),
                           os.path.join(folder, 'Notes', f'{a.survey}.plan.xvi'),
                           os.path.join(folder, 'Notes', f'{a.survey}P.xvi')])
    if not path:
        sys.exit(f"{a.survey}: no plan xvi found")
    # the SexyTopo files sit beside the .th, or in Notes/ (the 2025 surveys)
    plan_json = first([os.path.join(folder, f'{a.survey}.plan.json'), os.path.join(folder, 'Notes', f'{a.survey}.plan.json')])
    if not plan_json:
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
