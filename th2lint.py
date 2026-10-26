# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""Check Therion scraps (.th2) against the [lint] rules in tools/sketch2therion/Style.md.

Each check has the id of the `[lint: id]` tag in Style.md. Findings
already listed in the baseline file (existing drawings) are reported
but do not fail; new findings fail, and baseline entries that no
longer occur are reported so they can be removed.

    python3 -m tools.sketch2therion.th2lint --from LongwoodValleySink/Plan_only.thcfg
    python3 -m tools.sketch2therion.th2lint some/file.th2 other/file.th2
    python3 -m tools.sketch2therion.th2lint --from ... --update-baseline
"""

import argparse
import os
import math
import re
import sys
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
STYLE = os.path.join(HERE, "Style.md")
BASELINE = os.path.join(REPO, "tools", "th2lint-baseline.txt")   # the cave's drawings

LABEL_SCALES = {"xl", "l", "m", "s", "xs"}
CLIMB_WITH_UNITS = re.compile(r"^\s*[CP]\s*\d+(?:\.\d+)?\s*m(?:etres?)?\s*$", re.IGNORECASE)
LINT_TAG = re.compile(r"\[lint: ([a-z0-9-]+)\]")


@dataclass
class Obj:
    kind: str                   # point, line or area
    type: str                   # e.g. wall, rock-border, label
    options: list               # words after the type
    line: int                   # line number of the header
    comment_before: bool        # the previous non-blank line is a # comment
    coords: list = field(default_factory=list)  # lines of numbers (lines only)
    ids: list = field(default_factory=list)     # referenced ids (areas only)
    subtypes: list = field(default_factory=list)  # `subtype X` among a line's points

    def opt(self, name, default=None):
        """The value of option `-name`, or `default`."""
        words = self.options
        for i, w in enumerate(words):
            if w == "-" + name and i + 1 < len(words):
                return words[i + 1]
        return default

    def text(self):
        """The `-text` value, brackets and quotes removed."""
        m = re.search(r"-text\s+(\[[^\]]*\]|\"[^\"]*\"|\S+)", " ".join(self.options))
        return m.group(1).strip('[]"') if m else ""


@dataclass
class Scrap:
    id: str
    options: list
    line: int
    objects: list = field(default_factory=list)


@dataclass
class Finding:
    path: str
    scrap: str
    rule: str
    line: int
    message: str
    n: int = 0                  # occurrence of this rule in this scrap

    def key(self):
        """Stable across edits elsewhere in the file (no line number)."""
        return f"{self.path}\t{self.scrap}\t{self.rule}\t{self.n}"


def parse(text):
    """Scraps and their objects from a .th2 file."""
    scraps, scrap, obj = [], None, None
    prev_comment = False
    for n, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            prev_comment = True
            continue
        words = raw.split("#", 1)[0].split()
        head = words[0]
        if head == "scrap" and len(words) > 1:
            scrap = Scrap(words[1], words[2:], n)
            scraps.append(scrap)
        elif head == "endscrap":
            scrap = None
        elif scrap is not None and head in ("point", "line", "area"):
            if head == "point" and len(words) >= 4:
                scrap.objects.append(Obj("point", words[3], words[4:], n, prev_comment))
            elif head in ("line", "area") and len(words) >= 2:
                obj = Obj(head, words[1], words[2:], n, prev_comment)
                scrap.objects.append(obj)
        elif head in ("endline", "endarea"):
            obj = None
        elif obj is not None:
            if obj.kind == "line" and _numbers(words):
                obj.coords.append([float(w) for w in words])
            elif obj.kind == "line" and head == "subtype" and len(words) > 1:
                obj.subtypes.append(words[1])
            elif obj.kind == "area":
                obj.ids.append(head)
        prev_comment = False
    return scraps


def _numbers(words):
    try:
        [float(w) for w in words]
        return True
    except ValueError:
        return False


# --- checks: each takes a Scrap and yields (rule, line, message) ---

def check_scrap_author_copyright(scrap):
    opts = scrap.options
    if "-author" not in opts or "-copyright" not in opts:
        yield "scrap-author-copyright", scrap.line, "scrap has no -author or -copyright"


def check_wall_invisible(scrap):
    for o in scrap.objects:
        if o.kind == "line" and o.type.split(":")[0] == "wall" and \
                ("invisible" in (o.opt("subtype") or "") or o.type == "wall:invisible"):
            yield "wall-invisible", o.line, "invisible wall: leave the gap, Therion closes the outline"


def check_wall_outline_none(scrap):
    for o in scrap.objects:
        if o.kind == "line" and o.type.split(":")[0] == "wall" and o.opt("outline") == "none":
            yield "wall-outline-none", o.line, "wall with -outline none"


def check_no_clay(scrap):
    for o in scrap.objects:
        sub = [o.opt("subtype") or "", o.type.split(":")[1] if ":" in o.type else ""] + o.subtypes
        if (o.kind == "area" and o.type == "clay") or (o.kind == "line" and "clay" in sub):
            yield "no-clay", o.line, "clay: mud and sand are both sand"


def check_line_points(scrap):
    for o in scrap.objects:
        if o.kind == "line" and len(o.coords) < 2:
            yield "line-points", o.line, "line with fewer than 2 points"


def check_section_direction(scrap):
    for o in scrap.objects:
        if o.kind == "line" and o.type.split(":")[0] == "section" and not o.opt("direction"):
            yield "section-direction", o.line, "section line with no -direction (prefer both)"


def check_clip_off_reason(scrap):
    for o in scrap.objects:
        if o.opt("clip") == "off" and not o.comment_before:
            yield "clip-off-reason", o.line, "-clip off without a # comment on the line before"


def check_climb_units(scrap):
    for o in scrap.objects:
        if o.type == "label" and CLIMB_WITH_UNITS.match(o.text()):
            yield "climb-units", o.line, f"climb label with units: {o.text()!r} (write C2, P5)"


def check_draught_date(scrap):
    draughts = [o for o in scrap.objects if o.kind == "point" and o.type == "air-draught"]
    if draughts and not any(o.kind == "point" and o.type == "date" for o in scrap.objects):
        yield "draught-date", draughts[0].line, "air-draught with no point date in the scrap"


def check_label_scale(scrap):
    for o in scrap.objects:
        if o.type == "label":
            scale = o.opt("scale")
            if scale is not None and scale not in LABEL_SCALES:
                yield "label-scale", o.line, f"label -scale {scale} (use xl, l, m, s or xs)"


def check_rock_closed(scrap):
    for o in scrap.objects:
        if o.kind == "line" and o.type == "rock-border" and o.opt("close") != "on":
            yield "rock-closed", o.line, "rock-border without -close on"


def check_close_on_first_point(scrap):
    for o in scrap.objects:
        if o.kind == "line" and o.opt("close") == "on" and o.coords:
            first, last = o.coords[0][-2:], o.coords[-1][-2:]
            if len(o.coords) < 2 or first != last:
                yield "close-on-first-point", o.line, "-close on line does not end on its first point"


NODE_GAP = 0.05    # m: nodes closer than this cannot be told apart and picked when editing


def check_node_gap(scrap):
    """No two neighbouring nodes of a line closer than NODE_GAP (lint has no
    survey legs, so this is the fixed minimum; the converter also keeps to
    a share of the nearby legs' length)."""
    K = scrap_scale(scrap)
    if not K:
        return
    for o in scrap.objects:
        if o.kind != "line" or o.opt("subtype") == "invisible" and not o.opt("id"):
            continue
        pts = [(c[-2], c[-1]) for c in o.coords]
        close = sum(1 for a, b in zip(pts, pts[1:]) if math.dist(a, b) < NODE_GAP * K)
        if close:
            yield "node-gap", o.line, f"{o.type} has {close} node(s) within {NODE_GAP} m of the one before"


def check_rock_not_smooth(scrap):
    for o in scrap.objects:
        if o.kind == "line" and o.type == "rock-border" and any(len(c) == 6 for c in o.coords):
            yield "rock-not-smooth", o.line, "rock-border with curve control points"


def check_ceiling_step(scrap):
    for o in scrap.objects:
        if o.kind == "line" and o.type == "ceiling-step":
            yield "ceiling-step", o.line, "use line overhang, not ceiling-step"


def check_water_border(scrap):
    border_ids = {o.opt("id") for o in scrap.objects
                  if o.kind == "line" and o.type == "border" and o.opt("id")}
    for o in scrap.objects:
        if o.kind == "area" and o.type == "water":
            if not o.ids or any(i not in border_ids for i in o.ids):
                yield "water-border", o.line, "area water does not refer to a line border -id in the scrap"


def scrap_scale(scrap):
    """Drawing units per metre, from the scrap's -scale, or None."""
    m = re.search(r"-scale\s*\[([^\]]*)\]", " ".join(scrap.options))
    if not m:
        return None
    v = m.group(1).split()
    try:
        x1, y1, x2, y2, X1, Y1, X2, Y2 = (float(w) for w in v[:8])
    except ValueError:
        return None
    real = math.hypot(X2 - X1, Y2 - Y1)
    if len(v) > 8 and v[8] not in ("m", "meter", "meters", "metre", "metres"):
        return None
    return math.hypot(x2 - x1, y2 - y1) / real if real else None


END_TYPES = ("border", "floor-step", "pit", "overhang", "rimstone-dam", "ceiling-step")


def check_end_on_node(scrap):
    """A line ending at a wall (within 0.15 m) ends on a node of the wall."""
    K = scrap_scale(scrap)
    if not K:
        return
    wall_objs = [o for o in scrap.objects
                 if o.kind == "line" and o.type.split(":")[0] == "wall" and o.opt("subtype") != "invisible"
                 and len(o.coords) > 1]
    if not wall_objs:
        return
    walls = [_curve(o.coords) for o in wall_objs]
    nodes = [(c[-2], c[-1]) for o in wall_objs for c in o.coords]
    for o in scrap.objects:
        if o.kind != "line" or o.type.split(":")[0] not in END_TYPES or len(o.coords) < 2:
            continue
        if o.opt("close") == "on" or o.opt("subtype") == "invisible":
            continue
        for c in (o.coords[0], o.coords[-1]):
            end = (c[-2], c[-1])
            near = min(_seg_dist(end, a, b) for w in walls for a, b in zip(w, w[1:]))
            on = min(math.dist(end, p) for p in nodes)
            if near <= 0.15 * K and on > 0.005 * K:
                yield "end-on-node", o.line, f"{o.type} ends {near / K:.2f} m from a wall, not on a node"


def _curve(coords, n=12):
    """Points along a line, following its Bezier segments."""
    pts = [(coords[0][-2], coords[0][-1])]
    for c in coords[1:]:
        p0, p3 = pts[-1], (c[-2], c[-1])
        if len(c) == 6:
            c1, c2 = (c[0], c[1]), (c[2], c[3])
            for k in range(1, n + 1):
                t = k / n
                u = 1 - t
                pts.append((u ** 3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p3[0],
                            u ** 3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p3[1]))
        else:
            pts.append(p3)
    return pts


def _seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.dist(p, (a[0] + t * dx, a[1] + t * dy))


CHECKS = {name[len("check_"):].replace("_", "-"): fn
          for name, fn in globals().items() if name.startswith("check_")}


def lint_text(text, path=""):
    findings = []
    for scrap in parse(text):
        counts = {}
        for check in CHECKS.values():
            for rule, line, message in check(scrap):
                counts[rule] = counts.get(rule, 0) + 1
                findings.append(Finding(path, scrap.id, rule, line, message, counts[rule]))
    return sorted(findings, key=lambda f: (f.path, f.line, f.rule))


def style_rules(style_text):
    """The rule ids tagged in Style.md."""
    return set(LINT_TAG.findall(style_text)) - {"id"}


def read_baseline(path):
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {line.rstrip("\n") for line in f if line.strip() and not line.startswith("#")}


def write_baseline(path, findings):
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Existing th2lint findings, not failing CI. Remove a line when it is fixed.\n")
        f.write("# Regenerate with: python3 -m tools.sketch2therion.th2lint --from ... --update-baseline\n")
        for key in sorted({x.key() for x in findings}):
            f.write(key + "\n")


def files_from(thcfg, root=REPO):
    """The .th2 files a config file builds."""
    if REPO not in sys.path:
        sys.path.insert(0, REPO)
    from tools.sketch2therion import deps
    res = deps.walk(root, os.path.normpath(thcfg))
    return [f for f in res.files if f.endswith(".th2")]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="*", help=".th2 files, relative to the repository root")
    ap.add_argument("--from", dest="thcfg", help="lint every .th2 this config file builds")
    ap.add_argument("--root", default=REPO)
    ap.add_argument("--baseline", default=BASELINE)
    ap.add_argument("--update-baseline", action="store_true")
    a = ap.parse_args(argv)
    files = list(a.files) + (files_from(a.thcfg, a.root) if a.thcfg else [])
    findings = []
    for rel in files:
        with open(os.path.join(a.root, rel), encoding="utf-8", errors="replace") as f:
            findings += lint_text(f.read(), rel.replace(os.sep, "/"))
    if a.update_baseline:
        write_baseline(a.baseline, findings)
        print(f"{len(findings)} findings written to {a.baseline}")
        return 0
    baseline = read_baseline(a.baseline)
    new = [f for f in findings if f.key() not in baseline]
    linted = {f.replace(os.sep, "/") for f in files}
    stale = sorted(k for k in baseline - {f.key() for f in findings} if k.split("\t")[0] in linted)
    for f in new:
        print(f"{f.path}:{f.line}: [{f.rule}] {f.message} (scrap {f.scrap})")
    for k in stale:
        print(f"fixed, remove from baseline: {k.replace(chr(9), ' ')}")
    print(f"{len(files)} files, {len(findings)} findings, {len(new)} new, "
          f"{len(findings) - len(new)} in baseline, {len(stale)} baseline entries fixed")
    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main())
