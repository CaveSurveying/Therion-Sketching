# Ported from caves-mendip-swildons, tools/sketch2therion (commit 198bf46,
# https://github.com/paperclipmonkey/caves-mendip-swildons). GPLv3: see tools/LICENSE.
"""Command line: python3 -m tools.sketch2therion <command> ...

  check       how well a sketch fits the survey, before converting it
  plan        a plan sketch -> th2 (plan scraps and cross-sections)
  extended    an extended-elevation sketch -> th2 (elevation scraps,
              cross-sections, and a plan scrap placing the cross-sections)
  xvi         a PocketTopo .top or _th.txt -> XVI, to use as a backdrop
  extend      copy PocketTopo's left/right leg directions into a .th file
  tidy        redraw converted th2 files the conventional Therion way (the
              conversions above already do this): walls as the outline with
              the passage on their left, no -clip off, C/P labels outside
              the passage, ... (see tidy.py)
  roofs       redraw converted extended elevations' fill from the splay
              shots where no roof or floor was sketched (after a build)
  details     plan details: interior lines -> floor steps, cleaner
              boulders (after a build)
  smooth      refit converted walls with fewer, smooth points (last, after
              roofs and details)
  review      check a drawing against the sketch with someone who knows the
              cave: split-screen pictures, outline gaps, outline checks
  place       file a converted plan into its survey and the cave's plan map
  zip         a survey's drawing, sketches and review files, for review elsewhere

Sketches can be SexyTopo or PocketTopo .xvi files, PocketTopo .top files or
PocketTopo Therion exports (_th.txt). Run from the top of the repository,
after `therion -l output/therion-layout.log tools/layout.thcfg`. Cave
names, paths and drawing settings come from tools/project.toml.
"""
import argparse
import os
import re
import sys

from .. import project as _project
from . import convert, pockettopo, register, tidy, xvi

PROJECT = _project.load()
PLAN_LAYOUT = PROJECT.build['layout_plan']
EXT_LAYOUT = PROJECT.build['layout_extended']


def load(path, view):
    if path.lower().endswith('.xvi'):
        return xvi.read(path)
    return pockettopo.sketch(path, view)


def layout(path, required=False):
    if path and os.path.exists(path):
        return register.Layout(path)
    msg = (f"{path} not found: run  therion -l output/therion-layout.log tools/layout.thcfg  first"
           " (with the new trip's .th already input)")
    if required:
        sys.exit(msg)
    print("warning: " + msg + "; converting without fitting to the survey", file=sys.stderr)
    return None


def write_th2(text, path, newline=None):
    # Line endings as the cave's drawings have them (tools/project.toml)
    text = text.replace('\r\n', '\n').replace('\n', newline or PROJECT.newline)
    open(path, 'wb').write(text.encode('utf-8'))


def cmd_check(a):
    view = 'elevation' if a.elevation else 'plan'
    sk = load(a.sketch, view)
    lay = layout(a.layout or (EXT_LAYOUT if a.elevation else PLAN_LAYOUT), required=True)
    pos = sk.positions()
    colours = {}
    for c, _ in sk.lines:
        colours[c] = colours.get(c, 0) + 1
    print(f"{a.sketch}: {'extended elevation' if a.elevation else 'plan'}, {sk.scale:.2f} units/m")
    print(f"  {len(pos)} stations, {len(sk.legs())} legs, {len(sk.splays())} splays, "
          f"{len(sk.sections())} cross-sections")
    print("  lines: " + ", ".join(f"{c.lower()} {n}" for c, n in sorted(colours.items(), key=lambda kv: -kv[1])))
    missing = [n for n in pos if not lay.find(n, a.survey)]
    if missing:
        print(f"  NOT IN THE SURVEY ({len(missing)}): {' '.join(sorted(missing, key=register.natural)[:30])}")
        print(f"    Is the trip's .th input in {PROJECT.cave['master']}, the layout re-exported,"
              " and --survey right?")
    sk2, offs, flipped = register.fit(sk, lay, a.survey)
    if flipped:
        print("  WARNING: the sketch only fits upside down; it has been flipped")
    sp = register.spread(offs)
    if sp is not None:
        print(f"  fit to Therion's layout: stations within {sp:.2f} m (median) of one shift")
    gs = register.groups(offs, a.tol)
    if len(gs) > 1:
        print(f"  {len(gs)} groups of stations fit with different shifts (more than {a.tol} m apart);"
              " each becomes its own scrap:")
        for g in gs:
            print(f"    {len(g):3d}: {' '.join(sorted(g, key=register.natural)[:12])}{' ...' if len(g) > 12 else ''}")
    d = register.line_distance(sk2, convert.WALLS)
    if d is not None:
        print(f"  stations to nearest wall line: {d:.2f} m (median)"
              + ("  <- the stations may not line up with the drawing" if d > 2.5 else ""))


def _opts(a):
    name = a.name or PROJECT.scrap_prefix(
        re.sub(r'[^A-Za-z0-9]', '', a.survey or os.path.splitext(os.path.basename(a.output))[0]))
    return convert.Options(name, a.survey, tuple(a.author) if a.author else None,
                           tuple(a.copyright) if a.copyright else None, a.qualify)


def cmd_plan(a):
    sk = load(a.sketch, 'plan')
    floor = None
    from .settings import SETTINGS
    if a.floor and not SETTINGS['elevation_data']:
        print("--floor ignored: tools/project.toml draws only what the plan sketch shows (elevation_data = false)")
    elif a.floor:
        from . import floor as fl
        floor = fl.analyse(load(a.floor, 'elevation'))
        print(f"floor: {len(floor['climbs'])} steps, {len(floor['gradients'])} gradients")
    text, scraps, sections = convert.plan(sk, _opts(a), a.output, layout(a.layout or PLAN_LAYOUT), floor, a.tol)
    write_th2(tidy.tidy_text(text, a.map_scale), a.output)
    print(f"wrote {a.output}: {len(scraps)} plan scraps, {len(sections)} cross-sections")
    _map_hint(a.survey, scraps, 'plan')


def cmd_extended(a):
    sk = load(a.sketch, 'elevation')
    text, scraps, sections, plan_scraps = convert.extended(
        sk, _opts(a), a.output, layout(a.layout or EXT_LAYOUT),
        layout(a.plan_layout or PLAN_LAYOUT), a.tol, a.floor_reach, a.roof_reach)
    write_th2(tidy.tidy_text(text, a.map_scale), a.output)
    print(f"wrote {a.output}: {len(scraps)} elevation scraps, {len(sections)} cross-sections")
    _map_hint(a.survey, scraps, 'extended')
    if plan_scraps:
        print("and, for the cross-sections:")
        _map_hint(a.survey, plan_scraps, 'plan')


def _map_hint(survey, scraps, view):
    survey = survey or '<survey>'
    if view == 'plan':
        smap = PROJECT.survey_plan_map(survey)
        print(f"Add to `map {smap}` in {PROJECT.survey_file(survey)}:")
        for s in scraps:
            print(f"  {s}")
        print(f"and {PROJECT.qualified(smap, survey)} to {PROJECT.cave['plan_map']} in {PROJECT.cave['plan_map_file']}.")
    else:
        print(f"Add to an extended-elevation map in {PROJECT.survey_file(survey)}:")
        for s in scraps:
            print(f"  {s}")


def cmd_tidy(a):
    for f in a.files:
        tidy.tidy_file(f, a.map_scale)
    for r in tidy.REPORT:
        name, kept, total = r[:3]
        note = '' if kept else '  (left as it was: the walls could not be made into an outline)'
        print(f"  {name}: {100 * kept / max(total, 1):.0f}% of the walls on the outline{note}")


def cmd_roofs(a):
    from . import roofs
    splays = roofs.Splays()
    for f in a.files:
        done = roofs.redo_file(f, splays, a.map_scale)        # elevation scraps
        done += roofs.plan_redo_file(f, splays, a.scrap, a.map_scale)
        print(f"  {f}: {', '.join(done) or 'nothing to redo'}")


def cmd_details(a):
    from . import details, roofs
    splays = roofs.Splays()
    for f in a.files:
        for name, steps, blocks in details.redo_file(f, splays, a.scrap):
            print(f"  {name}: {steps} floor steps, {blocks} boulders")


def cmd_smooth(a):
    from . import smooth
    for f in a.files:
        for name, before, after, dropped, borders, joined, stepped in smooth.redo_file(f, scraps=a.scrap):
            if before or dropped or borders or joined or stepped:
                print(f"  {name}: {joined} walls joined, {dropped} doubled or stray pieces gone, "
                      f"{borders} made borders, {stepped} wall steps joined or line ends put on wall nodes; wall points {before} -> {after}")


def cmd_xvi(a):
    sk = load(a.sketch, a.view)
    xvi.write(sk, a.output)
    print(f"wrote {a.output}: {len(sk.stations)} stations, {len(sk.lines)} lines")


def cmd_extend(a):
    flags = pockettopo.th_txt_extend(a.export)
    b = open(a.th, 'rb').read()
    crlf = b'\r\n' in b
    s = b.decode('latin-1').replace('\r\n', '\n')
    legs = set()
    for l in s.splitlines():
        p = l.split('#')[0].split()
        if len(p) >= 5 and p[1] != '-':
            legs.add((p[0], p[1]))
    out = []
    for (f, t), d in flags.items():
        if (f, t) in legs:
            out.append((f, t, d))
        elif (t, f) in legs:
            out.append((t, f, 'right' if d == 'left' else 'left'))
    marker = "    # Extended-elevation direction of each leg"
    if marker in s:
        # keep directions already there (from other exports) unless this one sets them
        k = s.index(marker)
        e = re.search(r'^[ \t]*endcent(re|er)line', s[k:], re.M)
        mine = {(f, t) for f, t, _ in out}
        for l in s[k:k + e.start()].splitlines():
            q = l.split()
            if len(q) == 4 and q[0] == 'extend' and (q[2], q[3]) not in mine:
                out.append((q[2], q[3], q[1]))
        s = s[:k] + s[k + e.start():]
    block = [marker + ", as set in PocketTopo", "    # (these only affect the extended elevation)"] + \
            [f"    extend {d} {f} {t}" for f, t, d in out]
    i = max(s.rfind("endcentreline"), s.rfind("endcenterline"))
    j = s.rindex("\n", 0, i) + 1
    s = s[:j] + "\n".join(block) + "\n" + s[j:]
    if crlf:
        s = s.replace('\n', '\r\n')
    open(a.th, 'wb').write(s.encode('latin-1'))
    print(f"{a.th}: {len(out)} legs, {sum(1 for x in out if x[2] == 'left')} left")


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ['review']:                 # its own sub-commands
        from . import review
        return review.main(args[1:])
    if args[:1] == ['place']:                  # filing a drawing into the survey
        from . import place
        return place.main(args[1:])
    if args[:1] == ['zip']:                    # a review zip
        from . import reviewzip
        return reviewzip.main(args[1:])
    p = argparse.ArgumentParser(prog='python3 -m tools.sketch2therion', description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)

    def common(q, tol):
        q.add_argument('sketch', help='.xvi (SexyTopo or PocketTopo), .top or _th.txt')
        q.add_argument('--survey', help="the trip's survey name in Therion, e.g. GoSouth")
        q.add_argument('--layout', help="Therion's layout XVI (default output/layout-*.xvi)")
        q.add_argument('--tol', type=float, default=tol,
                       help=f'metres two stations can disagree and stay in one scrap (default {tol})')

    def drawing(q):
        q.add_argument('-o', '--output', required=True, help='the th2 file to write')
        q.add_argument('--name', help='scrap name prefix (default from tools/project.toml, e.g. GoSouthS)')
        q.add_argument('--author', nargs=2, metavar=('DATE', 'NAME'), help='e.g. 2026.04.25 "Andrew Atkinson"')
        q.add_argument('--copyright', nargs=2, metavar=('YEAR', 'HOLDER'))
        q.add_argument('--qualify', action='store_true',
                       help='write stations as name@survey, for a th2 input outside the survey')
        q.add_argument('--map-scale', type=int, default=PROJECT.drawing['map_scale'],
                       help='scale of the sheet it will be printed at, for sizing labels (default from tools/project.toml)')

    q = sub.add_parser('check', help='how well a sketch fits the survey')
    common(q, 1.5)
    q.add_argument('--elevation', action='store_true', help='the sketch is an extended elevation')
    q.set_defaults(func=cmd_check)

    q = sub.add_parser('plan', help='plan sketch -> th2')
    common(q, 3.0)
    drawing(q)
    q.add_argument('--floor', metavar='ELEVATION',
                   help='the same trip\'s extended-elevation sketch, for floor steps and gradients')
    q.set_defaults(func=cmd_plan)

    q = sub.add_parser('extended', help='extended-elevation sketch -> th2')
    common(q, 1.5)
    drawing(q)
    q.add_argument('--plan-layout', help="Therion's plan layout, for placing cross-sections")
    q.add_argument('--floor-reach', type=float, default=3.0,
                   help='fill down to a floor line up to this far below the legs (default 3 m)')
    q.add_argument('--roof-reach', type=float, default=5.0,
                   help='and up to a roof line this far above them (default 5 m; more for big chambers)')
    q.set_defaults(func=cmd_extended)

    q = sub.add_parser('tidy', help='redraw converted th2 files the conventional Therion way')
    q.add_argument('files', nargs='+')
    q.add_argument('--map-scale', type=int, default=PROJECT.drawing['map_scale'],
                   help='scale of the sheet the drawing is printed at, for sizing labels and arrows (default 500)')
    q.set_defaults(func=cmd_tidy)

    q = sub.add_parser('roofs', help="elevation fill from the splays where no roof or floor was sketched")
    q.add_argument('files', nargs='+')
    q.add_argument('--map-scale', type=int, default=PROJECT.drawing['map_scale'])
    q.add_argument('--scrap', nargs='+', help='only these plan scraps (default: every plan scrap with invisible walls)')
    q.set_defaults(func=cmd_roofs)

    q = sub.add_parser('details', help='floor steps, presumed walls and boulders in plan scraps')
    q.add_argument('files', nargs='+')
    q.add_argument('--scrap', nargs='+', help='only these scraps (default: every plan scrap)')
    q.set_defaults(func=cmd_details)

    q = sub.add_parser('smooth', help='refit converted walls with fewer, smooth points')
    q.add_argument('files', nargs='+')
    q.add_argument('--scrap', nargs='+', help="only these scraps (default: every scrap in the file; "
                   "name them in files with hand-drawn scraps too)")
    q.set_defaults(func=cmd_smooth)

    q = sub.add_parser('xvi', help='PocketTopo .top or _th.txt -> XVI')
    q.add_argument('sketch')
    q.add_argument('--view', choices=('plan', 'elevation'), default='plan')
    q.add_argument('-o', '--output', required=True)
    q.set_defaults(func=cmd_xvi)

    q = sub.add_parser('extend', help="PocketTopo's leg directions -> a .th file")
    q.add_argument('export', help='PocketTopo Therion export (_th.txt)')
    q.add_argument('th', help='the trip .th file to add them to')
    q.set_defaults(func=cmd_extend)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == '__main__':
    main()
