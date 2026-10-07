# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see tools/LICENSE.
"""Scraps chosen by hand: which stations each plan scrap holds.

Where a survey goes from one passage into another that overlaps it in
plan (a leg dropping into a passage below, or two passages that only come
close together), one scrap would join them up and turn the walls between
them into borders. [scraps] in tools/project.toml lists the stations of
each scrap instead, e.g.

    [scraps]
    GoSouth = ["1-16", "17-29"]

A leg between two scraps is in neither. Each sketch stroke goes to the
scrap of its nearest leg; a stroke running past more than one passage is
cut where its nearest scrap changes, each piece ending where the next
begins, so the wall between two passages becomes a wall of each.
"""
import math
import re

from shapely.geometry import LineString, Point

from .register import natural

MIN_PIECE = 0.5     # m: a shorter piece of a stroke stays with its neighbours' scrap


def parse(specs, stations):
    """[[station, ...] per scrap] from specs like "1-16" or "19, 21-23".
    Ranges are numeric and take only the stations that exist. Stations
    listed nowhere join a scrap they share a leg with (see `complete`)."""
    out = []
    names = set(stations)
    for spec in specs:
        g = []
        for part in re.split(r'[\s,]+', spec.strip()):
            if not part:
                continue
            m = re.fullmatch(r'(\d+)-(\d+)', part)
            if m:
                lo, hi = int(m.group(1)), int(m.group(2))
                g += [n for n in stations if n.isdigit() and lo <= int(n) <= hi]
            elif part in names:
                g.append(part)
            else:
                raise ValueError(f"[scraps]: no station {part} in the sketch")
        out.append(g)
    seen = {}
    for i, g in enumerate(out):
        for n in g:
            if n in seen and seen[n] != i:
                raise ValueError(f"[scraps]: station {n} is in more than one scrap")
            seen[n] = i
    return out


def complete(groups, stations, legs):
    """Stations in no group join the group of a station they share a leg
    with (repeatedly, so a run of unlisted stations follows on)."""
    member = {n: i for i, g in enumerate(groups) for n in g}
    grew = True
    while grew:
        grew = False
        for a, b in legs:
            for x, y in ((a, b), (b, a)):
                if x in member and y not in member:
                    member[y] = member[x]
                    groups[member[x]].append(y)
                    grew = True
    lost = [n for n in stations if n not in member]
    if lost:
        raise ValueError(f"[scraps]: stations {' '.join(sorted(lost, key=natural))} are in no scrap")
    return groups


def _closed(pp):
    return len(pp) > 3 and math.dist(pp[0], pp[-1]) < 0.1


def assign(lines, groups, pos, legs):
    """[(scrap index, colour, points)]: each stroke with the scrap of its
    nearest leg (legs within a scrap only; a lone station counts as a leg),
    long open strokes cut where that changes (see `meet_ends`)."""
    member = {n: i for i, g in enumerate(groups) for n in g}
    segs = [(member[a], LineString([pos[a], pos[b]])) for a, b in legs
            if a in member and member.get(b) == member[a] and pos[a] != pos[b]]
    have = {i for i, _ in segs}
    segs += [(i, Point(pos[n])) for n, i in member.items() if i not in have]
    if not segs:
        return [(0, c, pp) for c, pp in lines]

    def nearest(p):
        q = Point(p)
        return min(segs, key=lambda s: s[1].distance(q))[0]

    out = []
    for c, pp in lines:
        if not pp:
            continue
        if len(pp) < 3 or _closed(pp):
            mid = pp[len(pp) // 2] if not _closed(pp) else (
                sum(p[0] for p in pp) / len(pp), sum(p[1] for p in pp) / len(pp))
            out.append((nearest(mid), c, pp))
            continue
        tags = [nearest(p) for p in pp]
        runs = []                     # [scrap, first index, last index]
        for k, t in enumerate(tags):
            if runs and runs[-1][0] == t:
                runs[-1][2] = k
            else:
                runs.append([t, k, k])
        # short pieces go with a neighbour, so a stroke wavering along a boundary is not chopped up
        length = lambda r: LineString(pp[r[1]:r[2] + 1]).length if r[2] > r[1] else 0.0
        changed = True
        while changed and len(runs) > 1:
            changed = False
            for k, r in enumerate(runs):
                if length(r) < MIN_PIECE:
                    n = runs[k - 1] if k > 0 else runs[k + 1]
                    n[1], n[2] = min(n[1], r[1]), max(n[2], r[2])
                    del runs[k]
                    merged = []
                    for x in runs:
                        if merged and merged[-1][0] == x[0]:
                            merged[-1][2] = x[2]
                        else:
                            merged.append(x)
                    runs = merged
                    changed = True
                    break
        for t, a, b in runs:
            piece = pp[max(0, a - 1):b + 1]       # starts where the previous piece ended
            if len(piece) > 1:
                out.append((t, c, piece))
    return out



def meet_ends(text, near):
    """th2 text where a wall ending within `near` (drawing units) of a wall
    end in another scrap ends where that one does (both moved to their
    midpoint): one wall cut between two scraps, or drawn as two strokes
    that nearly meet, which the converter's tidying leaves apart."""
    lines = text.split("\n")
    ends = []                       # (scrap, line index of the row, (x, y))
    scrap = None
    i = 0
    while i < len(lines):
        if lines[i].startswith("scrap "):
            scrap = lines[i].split()[1]
        if lines[i].startswith("line wall") and "-subtype invisible" not in lines[i]:
            j = i + 1
            while j < len(lines) and lines[j].strip() != "endline":
                j += 1
            rows = [k for k in range(i + 1, j) if re.match(r"^\s*-?\d", lines[k])]
            for k in (rows[:1] + rows[-1:]) if rows else []:
                v = lines[k].split()
                ends.append((scrap, k, (float(v[-2]), float(v[-1]))))
            i = j
        i += 1
    done = set()
    for a in range(len(ends)):
        best = None
        for b in range(len(ends)):
            if ends[a][0] == ends[b][0] or a in done or b in done:
                continue
            d = math.dist(ends[a][2], ends[b][2])
            if 0 < d < near and (best is None or d < best[0]):
                best = (d, b)
        if best:
            b = best[1]
            m = ((ends[a][2][0] + ends[b][2][0]) / 2, (ends[a][2][1] + ends[b][2][1]) / 2)
            for k in (ends[a][1], ends[b][1]):
                v = lines[k].split()
                lines[k] = "  " + " ".join(v[:-2] + ["%.2f" % m[0], "%.2f" % m[1]])
            done |= {a, b}
    return "\n".join(lines)
