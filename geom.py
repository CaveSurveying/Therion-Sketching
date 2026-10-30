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
