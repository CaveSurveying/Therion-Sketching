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
