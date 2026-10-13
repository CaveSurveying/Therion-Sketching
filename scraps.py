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


def leg_owner(groups, legs):
    """{leg: scrap}: a leg with both stations in one scrap is that scrap's;
    a leg between two scraps with a junction (three legs or more) at one
    end only goes with the scrap at its other end (the passage beyond the
    junction); others are in neither."""
    member = {n: i for i, g in enumerate(groups) for n in g}
    degree = {}
    for a, b in legs:
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1
    out = {}
    for a, b in legs:
        if a not in member or b not in member:
            continue
        if member[a] == member[b]:
            out[(a, b)] = member[a]
        elif (degree[a] > 2) != (degree[b] > 2):
            out[(a, b)] = member[b] if degree[a] > 2 else member[a]
    return out


def junction_joins(groups, legs):
    """[(scrap, junction, other station)]: a scrap with one leg only at a
    junction where another scrap has legs too: a branch, its passage
    starting at the junction, its walls on a line up through it (Style.md,
    Scraps: each scrap a passage; Trident 10, the ramp to 12 a branch off
    the passage through 10)."""
    own = leg_owner(groups, legs)
    at = {}
    for l, i in own.items():
        for n in l:
            at.setdefault(n, {}).setdefault(i, []).append(l)
    out = []
    for j, by in at.items():
        if len(by) < 2:
            continue
        for i, ls in by.items():
            if len(ls) == 1:
                o = ls[0][1] if ls[0][0] == j else ls[0][0]
                out.append((i, j, o))
    return out


def assign(lines, groups, pos, legs, share=False, placed=None, marks=None):
    """[(scrap index, colour, points)]: each stroke with the scrap of its
    nearest leg (legs within a scrap only; a lone station counts as a leg;
    a leg between scraps starting at a junction goes with the scrap at its
    other end), long open strokes cut where that changes (see `meet_ends`)."""
    member = {n: i for i, g in enumerate(groups) for n in g}
    own = leg_owner(groups, legs)
    segs = [(i, LineString([pos[a], pos[b]])) for (a, b), i in own.items()
            if a in pos and b in pos and pos[a] != pos[b]]
    branches = branches_at(groups, pos, legs) if share else []
    have = {i for i, _ in segs}
    segs += [(i, Point(pos[n])) for n, i in member.items() if i not in have]
    if marks:
        # a station's splays straight up and down are part of its tube: a wall they reach is
        # nearest that tube. A junction a branch holds is in the tube of the passage through it
        # (the scrap with most of its legs): FairyChimneys 9, the chimney over it, not 9 to 12
        tube = dict(member)
        for n in member:
            at = [i for l, i in own.items() if n in l]
            if len(at) > 2:
                most = max(set(at), key=at.count)
                if at.count(most) >= 2:
                    tube[n] = most
        segs += [(tube[n], LineString([pos[n], e])) for n, ends in marks.items()
                 if n in tube and n in pos for e in ends if math.dist(pos[n], e) > 0.05]
        member = tube
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
        # a branch's piece in the middle of a wall of the passage through the junction is
        # that passage's (Trident: the roof over 10 to 13 runs close by 12)
        small = {bi for _, bi, _, _ in branches}
        for k in range(1, len(runs) - 1):
            if runs[k][0] in small and runs[k - 1][0] == runs[k + 1][0] != runs[k][0]:
                runs[k][0] = runs[k - 1][0]
        for t, a, b in runs:
            piece = pp[max(0, a - 1):b + 1]       # starts where the previous piece ended
            if len(piece) > 1:
                out.append((t, c, piece))
                decided = None
                if share and c in ('BLACK', 'BROWN'):
                    decided = by_direction(piece, t, branches)
                    if decided is not None:
                        if decided != t and placed is not None:
                            placed.add((tuple(piece[0]), tuple(piece[-1])))     # by its direction: kept there
                        t = decided
                        out[-1] = (t, c, piece)
                # the floor or ceiling a scrap's stations' splays end on is that scrap's (Connection
                # left of 13, user: the splays say which floor and ceiling is which)
                hits = splay_hits(piece, marks, member) if marks and c in ('BLACK', 'BROWN') else {}
                if hits and decided is None:
                    if t not in hits:
                        t = max(hits, key=hits.get)
                        out[-1] = (t, c, piece)
                    for k in hits:                    # splays of two scraps on it: a wall of each
                        if k != t:
                            out.append((k, c, piece))
                    continue
                # the wall between two scraps' passages: each draws it (not one a junction's branch decided)
                u = shared_with(piece, t, segs) if share and c in ('BLACK', 'BROWN') and decided is None else None
                if u is not None:                 # the wall between two scraps' passages: each draws it
                    out.append((u, c, piece))
    if not share and SIDE_BY_SIDE:
        out = side_by_side(out, segs)
    return out


BRANCH_REACH = 1.5  # m: a wall starting this near a junction (along the passage) may be the branch's
BRANCH_HEIGHT = 2.0  # m: and within this above or below it
BRANCH_TURN = 5.0   # degrees: the branch's when this much nearer its leg's direction than the passage's


def branches_at(groups, pos, legs):
    """[(junction, branch scrap, its leg's far end, [(scrap, far end) of
    the other legs at the junction])] for `by_direction`."""
    own = leg_owner(groups, legs)
    out = []
    for bi, j, o in junction_joins(groups, legs):
        if j not in pos or o not in pos:
            continue
        rest = [(i, l[1] if l[0] == j else l[0]) for l, i in own.items() if j in l and i != bi]
        out.append((pos[j], bi, pos[o], [(i, pos[n]) for i, n in rest if n in pos]))
    return out


def by_direction(piece, t, branches):
    """The scrap of a wall starting at a junction, by the leg it runs along:
    the branch's when it heads off as the branch's leg does, else the
    passage through the junction's (Trident 10: the ramp's floor up to 12
    runs past 13 in the extended elevation, nearer 10 to 13 than 10 to 12).
    None for a wall not starting at a junction."""
    if len(piece) < 2 or LineString(piece).length < 1.0:
        return None
    ang = lambda a, b: math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    turn = lambda a, b: abs((a - b + 180) % 360 - 180)
    for j, bi, o, rest in branches:
        for e, f in ((piece[0], piece[-1]), (piece[-1], piece[0])):
            if abs(e[0] - j[0]) > BRANCH_REACH or abs(e[1] - j[1]) > BRANCH_HEIGHT:
                continue
            side = 1 if o[0] > j[0] else -1
            if (f[0] - e[0]) * side <= 0:
                continue                          # heads the other way from the branch
            a = ang(e, f)
            same = [(turn(a, ang(j, n)), i) for i, n in rest if (n[0] - j[0]) * side > 0]
            if not same:
                continue
            through, ti = min(same)
            if turn(a, ang(j, o)) + BRANCH_TURN < through:
                return bi
            return ti if t == bi else t
    return None


SPLAY_HIT = 0.3     # m: a splay end this near a wall stroke ends on it


def splay_hits(piece, marks, member):
    """{scrap: splay ends on the piece} from marks {station: [(x, y) splay
    ends]} (in an elevation, the ends straight up and down)."""
    line = LineString(piece)
    out = {}
    for n, ends in marks.items():
        if n not in member:
            continue
        k = sum(1 for e in ends if line.distance(Point(e)) < SPLAY_HIT)
        if k:
            out[member[n]] = out.get(member[n], 0) + k
    return out


SIDE_BY_SIDE = True
PAIR_GAP = 0.6      # m: two walls this close, side by side, are the walls of two passages
PAIR_REACH = 3.0    # m: the other scrap's legs within this of the outer one of them
PAIR_MIN = 2.0      # m: walls at least this long (short pieces where passages cross are left as they are)
PAIR_TURN = 30.0    # degrees: both passages' legs within this of the walls' direction


def side_by_side(pieces, segs):
    """Two walls of one scrap running side by side close together, between
    this scrap's passage and another's: the one on the other passage's side
    (that passage's leg beyond it, this scrap's leg and the other wall on
    the near side) is the other scrap's wall (GoSouth 16 to 21, hand edit:
    the lower of the two lines is the wall of the passage from 17, not of
    13 to 16)."""
    out = [list(p) for p in pieces]
    walls = [k for k, (t, c, pp) in enumerate(out) if c == 'BLACK' and len(pp) > 1 and LineString(pp).length > PAIR_MIN]

    def side(line, q):                            # +1 left of the line at its nearest part, -1 right
        d = line.project(q)
        a, b = line.interpolate(max(0.0, d - 0.1)), line.interpolate(min(line.length, d + 0.1))
        return 1 if (b.x - a.x) * (q.y - a.y) - (b.y - a.y) * (q.x - a.x) > 0 else -1
    moves = {}
    for i in walls:
        for j in walls:
            if i == j or out[i][0] != out[j][0]:
                continue
            x, y = LineString(out[i][2]), LineString(out[j][2])
            if sum(y.distance(x.interpolate(k / 10, normalized=True)) < PAIR_GAP for k in range(11)) < 7:
                continue                              # not side by side along most of x
            t = out[i][0]
            mid = x.interpolate(0.5, normalized=True)
            mine = [g for k, g in segs if k == t and isinstance(g, LineString)]
            theirs = [(k, g) for k, g in segs if k != t and isinstance(g, LineString)]
            if not mine or not theirs:
                continue
            gm = min(mine, key=lambda g: g.distance(mid))
            kt, gt = min(theirs, key=lambda kg: kg[1].distance(mid))
            if gt.distance(mid) > PAIR_REACH:
                continue

            def along(g):                             # the leg runs alongside x (not across, as where passages cross)
                (x0, y0), (x1, y1) = x.coords[0], x.coords[-1]
                (u0, v0), (u1, v1) = g.coords[0], g.coords[-1]
                c = abs((x1 - x0) * (u1 - u0) + (y1 - y0) * (v1 - v0)) / ((x.length or 1) * (g.length or 1))
                return c > math.cos(math.radians(PAIR_TURN))
            if not (along(gm) and along(gt)):
                continue
            from shapely.ops import nearest_points
            pm = nearest_points(gm, mid)[0]
            pt = nearest_points(gt, mid)[0]
            py = nearest_points(y, mid)[0]
            if side(x, pt) != side(x, pm) and side(x, py) == side(x, pm):
                moves[i] = kt
    for i, k in moves.items():
        out[i][0] = k
    return [tuple(p) for p in out]


SHARED = 1.5        # m: a wall between two passages this near it, one either side, is a wall of each


def shared_with(piece, t, segs):
    """The other scrap whose passage is on the far side of this wall piece,
    as near it as scrap t's (Style.md, Scraps: each scrap a passage, the
    wall between two of them drawn in both), or None."""
    line = LineString(piece)
    if line.length < 1.0:
        return None
    mid = line.interpolate(0.5, normalized=True)
    a, b = line.interpolate(0.45, normalized=True), line.interpolate(0.55, normalized=True)

    def side(g):                                  # by the leg's end furthest from the wall (a leg may cross it)
        ends = [Point(g.coords[0]), Point(g.coords[-1])]
        q = max(ends, key=lambda e: line.distance(e))
        return (b.x - a.x) * (q.y - a.y) - (b.y - a.y) * (q.x - a.x) > 0
    best = {}
    for k, g in segs:
        d = g.distance(mid)
        if k not in best or d < best[k][0]:
            best[k] = (d, g)
    if t not in best:
        return None
    dt, gt = best[t]
    beside = lambda g: isinstance(g, LineString) and 0 < g.project(mid) < g.length    # alongside it, not past its end
    for k, (d, g) in sorted(best.items(), key=lambda x: x[1][0]):
        if k != t and d < SHARED and d < 2 * dt + 0.3 and side(g) != side(gt) and beside(g):
            return k
    return None


BRIDGE = 3.0         # m: a run of wall pieces this long or less between two of another scrap's is that scrap's
BRIDGE_MEET = 0.3    # m: pieces whose ends are this close are joined end to end
BRIDGE_TURN = 45.0   # degrees: and carry on in line, turning less than this at each join


def carried_through(pieces, colours):
    """Pieces with a short run of wall strokes (BRIDGE m or less) joined end
    to end at both ends to one other scrap's walls, and to none of its own
    scrap's, moved to that scrap: the floor carries on (FairyChimneys 9: the
    floor under it, from 8 to the crawl, drawn where the branch 20 to 21 is
    nearer)."""
    key = lambda pp: (tuple(pp[0]), tuple(pp[-1]), len(pp))
    geo, owners = {}, {}
    for k, c, pp in pieces:
        if c in colours and len(pp) > 1:
            geo[key(pp)] = pp
            owners.setdefault(key(pp), set()).add(k)
    ends = {g: (pp[0], pp[-1]) for g, pp in geo.items()}
    length = {g: LineString(pp).length for g, pp in geo.items()}

    def touching(g, e):
        return [h for h in geo if h != g and min(math.dist(e, ends[h][0]), math.dist(e, ends[h][1])) < BRIDGE_MEET]

    def heading(g, e):
        """Direction of piece g leaving its end nearest e (over its first BRIDGE_MEET m)."""
        pp = geo[g] if math.dist(e, geo[g][0]) <= math.dist(e, geo[g][-1]) else geo[g][::-1]
        q = next((p for p in pp if math.dist(p, pp[0]) >= BRIDGE_MEET), pp[-1])
        return math.atan2(q[1] - pp[0][1], q[0] - pp[0][0])

    def straight_on(g, h, e):
        """g and h meeting at e carry on in line (one leaves the way the other arrives)."""
        d = abs((heading(g, e) - heading(h, e) + math.pi) % (2 * math.pi) - math.pi)
        return d > math.pi - math.radians(BRIDGE_TURN)

    move = {}
    for g in geo:
        if len(owners[g]) != 1 or g in move:
            continue
        mine = next(iter(owners[g]))
        chain, hits = [g], []
        for e in ends[g]:
            cur, at = g, e
            while True:
                nxt = [h for h in touching(cur, at) if h not in chain]
                # the same stroke carrying on (cut there when shared out) before any other meeting it
                same = [h for h in nxt if min(math.dist(at, ends[h][0]), math.dist(at, ends[h][1])) < 1e-6]
                nxt = same or nxt
                own = [h for h in nxt if mine in owners[h]]
                theirs = [h for h in nxt if mine not in owners[h]]
                if theirs and not own:              # the run ends on another scrap's wall, carrying on in line
                    ks = set.intersection(*[owners[h] for h in theirs])
                    ok = len(ks) == 1 and any(straight_on(cur, h, at) for h in theirs)
                    hits.append(next(iter(ks)) if ok else None)
                    break
                if len(own) != 1 or theirs or len(nxt) != 1:
                    hits.append(None)               # a free end, or a junction of walls: not a bridge
                    break
                h = own[0]
                if owners[h] != {mine} or not straight_on(cur, h, at):
                    hits.append(None)
                    break
                chain.append(h)
                if sum(length[x] for x in chain) > BRIDGE:
                    hits.append(None)
                    break
                far = ends[h][1] if math.dist(ends[h][0], at) < BRIDGE_MEET else ends[h][0]
                cur, at = h, far
        if len(hits) == 2 and hits[0] is not None and hits[0] == hits[1] \
                and sum(length[x] for x in chain) <= BRIDGE:
            for x in chain:
                move[x] = hits[0]
    return [(move.get(key(pp), k) if c in colours and len(pp) > 1 else k, c, pp) for k, c, pp in pieces]


BEHIND_NEAR = 1.0    # m: a wall this close behind another of the scrap's walls, seen from its stations,
BEHIND_SHARE = 0.5   # over more than this share of its length, is a second wall on that side
BEHIND_RUN = 1.0     # m: and this much of it at least


def one_wall_each_side(pieces, groups, pos, colours):
    """Pieces without a wall stroke that is also another scrap's where, in
    this scrap, it and another of its walls lie one behind the other, seen
    from its nearest station (Style.md, hard rule 2: one outer wall each
    side of the passage; FairyChimneys 13 to 20: the crawl's floor and roof,
    drawn by the branch over it)."""
    key = lambda pp: (tuple(pp[0]), tuple(pp[-1]), len(pp))
    owners = {}
    for k, c, pp in pieces:
        if len(pp) > 1:
            owners.setdefault(key(pp), set()).add(k)
    drop = set()
    for k, g in enumerate(groups):
        st = [pos[n] for n in g if n in pos]
        walls = [(i, LineString(pp)) for i, (k2, c, pp) in enumerate(pieces)
                 if k2 == k and c in colours and len(pp) > 1 and LineString(pp).length >= 0.5]
        if not st:
            continue
        shared = lambda i: len(owners[key(pieces[i][2])]) > 1
        for i, a in walls:
            n = max(2, int(a.length / 0.1) + 1)
            by = {}
            for q in range(n):
                p = a.interpolate(q / (n - 1), normalized=True)
                s_ = min(st, key=lambda x: math.dist(x, (p.x, p.y)))
                sight = LineString([(p.x, p.y), s_])
                for j, b in walls:
                    if j != i and b.distance(p) < BEHIND_NEAR and b.intersects(sight) \
                            and b.intersection(sight).distance(p) > 0.05:
                        by[j] = by.get(j, 0) + 1
            # not one carrying on from the other's end (a continuation, not a second wall)
            ends = lambda x: [Point(x.coords[0]), Point(x.coords[-1])]
            by = {j: c for j, c in by.items()
                  if not any(e.distance(f) < 0.1 for e in ends(a) for f in ends(dict(walls)[j]))}
            if not by:
                continue
            j = max(by, key=by.get)
            if by[j] > BEHIND_SHARE * n and by[j] * a.length / (n - 1) >= BEHIND_RUN:
                # two walls on one side: the one that is also another scrap's goes (the one behind
                # if both are); if neither is, the judging decides which is the wall
                if shared(i):
                    drop.add(i)
                elif shared(j):
                    drop.add(j)
    return [x for i, x in enumerate(pieces) if i not in drop]


def other_ends(lines, scrap):
    """Indices of the first and last point rows of the lines other than
    walls in one scrap of th2 text (as a list of lines)."""
    out, cur, i = [], None, 0
    while i < len(lines):
        if lines[i].startswith("scrap "):
            cur = lines[i].split()[1]
        if cur == scrap and lines[i].startswith("line ") and not lines[i].startswith("line wall"):
            j = i + 1
            while j < len(lines) and lines[j].strip() != "endline":
                j += 1
            rows = [k for k in range(i + 1, j) if re.match(r"^\s*-?\d", lines[k])]
            out += rows[:1] + rows[-1:]
            i = j
        i += 1
    return out


def meet_ends(text, near, within=False):
    """th2 text where a wall ending within `near` (drawing units) of a wall
    end in another scrap ends where that one does (both moved to their
    midpoint): one wall cut between two scraps, or drawn as two strokes
    that nearly meet, which the converter's tidying leaves apart. With
    `within`, two walls of one scrap too (Style.md, Walls: wall ends that
    nearly meet are one point; TridentLeft 5 and 10, hand edit)."""
    lines = text.split("\n")
    ends = []                       # (scrap, line index of the row, (x, y))
    scrap, section = None, False
    i = 0
    while i < len(lines):
        if lines[i].startswith("scrap "):
            scrap = lines[i].split()[1]
            section = "-projection none" in lines[i]      # a cross-section joins no other scrap
        if lines[i].startswith("line wall") and "-subtype invisible" not in lines[i] and "-close on" not in lines[i] \
                and not section:
            j = i + 1
            while j < len(lines) and lines[j].strip() != "endline":
                j += 1
            rows = [k for k in range(i + 1, j) if re.match(r"^\s*-?\d", lines[k])]
            for k in (rows[:1] + rows[-1:]) if rows else []:
                v = lines[k].split()
                ends.append((scrap, k, (float(v[-2]), float(v[-1])), i))
            i = j
        i += 1
    done = set()
    for a in range(len(ends)):
        best = None
        for b in range(len(ends)):
            if a in done or b in done or ends[a][3] == ends[b][3] or (ends[a][0] == ends[b][0] and not within):
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
            # a line of another kind (a step, a border) ending on either end moves with it (lint end-on-node)
            old = {("%.2f" % ends[x][2][0], "%.2f" % ends[x][2][1]) for x in (a, b)}
            for k in other_ends(lines, ends[a][0]):
                v = lines[k].split()
                if tuple(v[-2:]) in old:
                    lines[k] = "  " + " ".join(v[:-2] + ["%.2f" % m[0], "%.2f" % m[1]])
            done |= {a, b}
    return "\n".join(lines)


def _walls_of(lines):
    """[(scrap, header index, [numeric row indices])] of the walls in th2 lines,
    cross-sections left out: a section joins no other scrap (TridentLeft PX6
    was joined to the plan's wall beside it)."""
    out, scrap, section, i = [], None, False, 0
    while i < len(lines):
        if lines[i].startswith("scrap "):
            scrap = lines[i].split()[1]
            section = "-projection none" in lines[i]
        if lines[i].startswith("line wall") and "-subtype invisible" not in lines[i] and "-close on" not in lines[i] \
                and not section:
            j = i + 1
            while j < len(lines) and lines[j].strip() != "endline":
                j += 1
            rows = [k for k in range(i + 1, j) if re.match(r"^\s*-?\d", lines[k])]
            if len(rows) >= 2:
                out.append((scrap, i, rows))
            i = j
        i += 1
    return out


def _cubic(p0, r):
    """The segment from p0 to row r as four control points (a straight row as a cubic)."""
    if len(r) == 6:
        return [p0, (r[0], r[1]), (r[2], r[3]), (r[4], r[5])]
    q = (r[0], r[1])
    return [p0, (p0[0] + (q[0] - p0[0]) / 3, p0[1] + (q[1] - p0[1]) / 3),
            (p0[0] + 2 * (q[0] - p0[0]) / 3, p0[1] + 2 * (q[1] - p0[1]) / 3), q]


def _at(c, t):
    a = [(c[k][0] + (c[k + 1][0] - c[k][0]) * t, c[k][1] + (c[k + 1][1] - c[k][1]) * t) for k in range(3)]
    b = [(a[k][0] + (a[k + 1][0] - a[k][0]) * t, a[k][1] + (a[k + 1][1] - a[k][1]) * t) for k in range(2)]
    m = (b[0][0] + (b[1][0] - b[0][0]) * t, b[0][1] + (b[1][1] - b[0][1]) * t)
    return a, b, m


def meet_on_walls(text, near):
    """th2 text where a wall ending within `near` (drawing units) of another
    scrap's wall, along it, ends on it at a node of it: the other wall gets
    a node there (Style.md, Scraps: where a scrap's walls join another
    scrap's they meet at a node; FairyChimneys, user)."""
    lines = text.split("\n")
    for _ in range(200):
        walls = _walls_of(lines)
        row = lambda k: [float(v) for v in lines[k].split()]
        best = None
        ends_all = [(sa, tuple(row(k)[-2:])) for sa, ha, ra in walls for k in (ra[0], ra[-1])]
        for wa, (sa, ha, ra) in enumerate(walls):
            for ek in (ra[0], ra[-1]):
                e = tuple(row(ek)[-2:])
                if any(sb != sa and math.dist(e, f) < near for sb, f in ends_all):
                    continue                             # meets another scrap's wall end: meet_ends
                if any(sb != sa and math.dist(e, tuple(row(k)[-2:])) < 0.01 for sb, hb, rb in walls for k in rb):
                    continue                             # on a node of another scrap's wall already
                for wb, (sb, hb, rb) in enumerate(walls):
                    if sb == sa:
                        continue
                    nodes = [tuple(row(k)[-2:]) for k in rb]
                    for s_ in range(1, len(rb)):
                        c = _cubic(nodes[s_ - 1], row(rb[s_]))
                        for q in range(1, 40):
                            m = _at(c, q / 40)[2]
                            d = math.dist(e, m)
                            if d < near and (best is None or d < best[0]):
                                best = (d, ek, rb[s_], q / 40, c, len(row(rb[s_])) == 6)
        if best is None:
            break
        d, ek, k, t, c, curved = best
        a, b, m = _at(c, t)
        split = True
        for n_ in (c[0], c[3]):                         # a node of it in reach: end there, no split
            if math.dist(n_, tuple(row(ek)[-2:])) < near:
                m, split = n_, False
                break
        # the other wall split at m: two segments meeting there
        if curved:
            first = "  %.2f %.2f %.2f %.2f %.2f %.2f" % (a[0][0], a[0][1], b[0][0], b[0][1], m[0], m[1])
            second = "  %.2f %.2f %.2f %.2f %.2f %.2f" % (b[1][0], b[1][1], a[2][0], a[2][1], c[3][0], c[3][1])
        else:
            first, second = "  %.2f %.2f" % m, "  %.2f %.2f" % c[3]
        m = (round(m[0], 2), round(m[1], 2))
        # the wall end moved onto it (with its control point, keeping the curve's shape)
        v = row(ek)
        dx, dy = m[0] - v[-2], m[1] - v[-1]
        old = ("%.2f" % v[-2], "%.2f" % v[-1])
        if len(v) == 6:
            v[2] += dx
            v[3] += dy
        v[-2:] = list(m)
        lines[ek] = "  " + " ".join("%.2f" % x for x in v)
        first_row = any(ek == ra[0] for _, _, ra in walls)
        if first_row and re.match(r"^\s*-?\d", lines[ek + 1]):   # the next segment's first control point too
            w = [float(x) for x in lines[ek + 1].split()]
            if len(w) == 6:
                w[0] += dx
                w[1] += dy
                lines[ek + 1] = "  " + " ".join("%.2f" % x for x in w)
        scrap = next(sa for sa, ha, ra in walls if ek in ra)
        for o in other_ends(lines, scrap):            # a step or border ending there moves with it
            u = lines[o].split()
            if tuple(u[-2:]) == old:
                lines[o] = "  " + " ".join(u[:-2] + ["%.2f" % m[0], "%.2f" % m[1]])
        if split:
            lines[k:k + 1] = [first, second]
    return "\n".join(lines)


def drop_slivers(text, least):
    """th2 text without walls shorter than `least` (drawing units) along
    their points: a slip, not a drawn wall (lint node-gap; FairyChimneys)."""
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        if lines[i].startswith("line wall"):
            j = i + 1
            while j < len(lines) and lines[j].strip() != "endline":
                j += 1
            pts = [tuple(float(v) for v in lines[k].split()[-2:]) for k in range(i + 1, j)
                   if re.match(r"^\s*-?\d", lines[k])]
            if len(pts) >= 2 and sum(math.dist(a, b) for a, b in zip(pts, pts[1:])) < least:
                i = j + 1
                continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)

