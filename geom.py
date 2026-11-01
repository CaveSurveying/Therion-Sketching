# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""Small geometry helpers on strokes (lists of (x, y) points), shared by
every projection (REFACTOR.md)."""
import math


def length(pp):
    """Length along the stroke."""
    return sum(math.dist(a, b) for a, b in zip(pp, pp[1:]))


def span(pp, sample=None):
    """Greatest distance between two of its points (0 for none); with
    `sample`, from about that many of them, for speed."""
    if sample:
        pp = pp[::max(1, len(pp) // sample)] + [pp[-1]]
    return max((math.dist(a, b) for a in pp for b in pp), default=0.0)


def closed(pp, gap=0.15, share=0.0, least=0.0, points=2):
    """A closed loop: at least `points` points and `least` long, its ends
    closer than `gap` (or `share` of its length, if more). Callers keep
    their own limits for now (REFACTOR.md, disagreements)."""
    if len(pp) < points:
        return False
    L = length(pp)
    return L >= least and math.dist(pp[0], pp[-1]) < max(gap, share * L)


def cluster(geoms, near):
    """Groups of indices of geometries each within `near` of another in its
    group (`near` may be a function of the index), in the order they join."""
    groups = []
    for i, g in enumerate(geoms):
        d = near(i) if callable(near) else near
        hit = [grp for grp in groups if any(g.distance(geoms[j]) < d for j in grp)]
        for grp in hit:
            groups.remove(grp)
        groups.append(sum(hit, []) + [i])
    return groups


def view_direction(n, legs, pos, fallback=None):
    """Which way a cross section at station n is seen (Style.md, Cross
    sections): along the survey from n towards the next station, else on
    from the one before. legs [(from, to)], pos {station: (x, y)}; stations
    under 0.3 m away are passed over. `fallback` if neither is known."""
    P = pos[n]
    ahead = [b for a, b in legs if a == n and b in pos and math.dist(P, pos[b]) > 0.3]
    if ahead:
        return (pos[ahead[0]][0] - P[0], pos[ahead[0]][1] - P[1])
    behind = [a for a, b in legs if b == n and a in pos and math.dist(P, pos[a]) > 0.3]
    if behind:
        return (P[0] - pos[behind[0]][0], P[1] - pos[behind[0]][1])
    return fallback
