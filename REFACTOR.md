# Refactor: one way of reading a sketch

Plans, extended elevations and cross sections each grew their own ways of
reading what a stroke means (a closed loop, a curl, a boulder, a dash), so
fixes made for one went out of step with the others. This refactor brings
the common parts together, so a rule is written once and used by every
projection. What really differs between projections stays apart.

## How it is checked

Every step must leave the drawings the same. Before the refactor, every
LongwoodValleySink plan and extended elevation and the Golgotha
(Reservoir) elevation is converted from its sketch with main, through the
same steps as by hand (`extended` or `plan`, then `roofs`, `details` for
plans, `smooth`). After each step they are converted again and compared,
comment lines left out. Cheddar's tests must pass too.

Each step is also run under different `PYTHONHASHSEED` values: the
output must not depend on the order sets are gone through (item 7).

Where two copies of a rule disagree, the step keeps each one's behaviour
(as a parameter of the shared code) and the disagreement goes in the list
below, to be settled separately: settling it changes drawings.

## Steps

Done, each a commit that leaves every drawing the same:

1. `geom.py`: one copy of a stroke's length and span (there were copies
   in eight modules).
2. `geom.closed`: one test for a closed loop, called from nine places,
   each still with its own limits.
3. `_converting` and `_start` in `convert.py`: what the plan and extended
   conversions share at the start (slips of the pen, the split, the local
   scale, cross sections taken out). Plans now skip `[glitches]` boxes
   too (none is set for a plan, so nothing changed).
4. `notation.ticks_of` and `notation.tick_strokes`: elevations find an
   overhang's ticks with the plans' code (item 3 below).

Not done: the rest of sharing the reading of a sketch (boulder sizes, one
stroke classifier, notation, the output of boulders and areas) cannot be
done without changing drawings, because the copies disagree. Each is in
the list below; once a disagreement is settled, the shared code follows
and the drawings change as that decision says.

## Disagreements to settle

Each was tried against every drawing (2026-10-30). Two were settled;
the rest are kept as they are because settling them made drawings worse
or is a matter of judgement.

1. **Closed loop: keep apart.** Plans (and water pools): ends within
   0.15 m or 20% of its length, at least 0.2 m long. Elevations: 0.15 m
   times the local factor, or 15%. Scraps and formation rings: 0.1 m.
   Cross section rocks, floor marks, green walls, symbols' boulders:
   0.15 m. One rule (0.15 m times the factor, or 20%) changed 14
   drawings: Golgotha and RoundTheBend lost debris floors, a flowstone
   mark in FairyChimneys became a stalagmite, the default settings no
   longer matched the Swildons converter, and the plans' 0.2 m least
   length lost the pebbles of cross sections. The limits suit what each
   caller looks for; they stay as parameters of `geom.closed`.
2. **Boulder size: keep apart.** Plans: a closed loop 0.3 m across or
   more is a boulder, smaller debris, under 0.15 m dirt. Elevations: up to
   1.5 m round (times the factor) is a boulder in a row along the floor.
   Symbols: a blob 0.2 to 2.5 m across, or a loop under 3 m round. With no
   upper limit in elevations 15 drawings changed: passage outlines were
   taken for boulders and Golgotha lost its debris floors. A better rule
   needs a way to tell a large boulder from a small piece of passage.
3. **Ticks: settled.** Ticks are found one way (`notation.ticks_of`):
   sized by the local factor, starting on the line and leaving it at 45
   degrees or more. No drawing changed. What the ticks mean stays with
   each projection, and so do three limits: elevations take a tick at
   least 0.08 m long, its ends 0.7 of its length apart and starting
   within 0.12 m of its line (plans 0.06 m, 0.6, 0.15 m). With the plans'
   limits CJS gained an overhang by 109 from formations hanging under
   the roof, which the filed drawing does not have.
4. **Curls: names only.** `marks.is_curl` (a loop not quite closed, a
   boulder) and `elevation.is_curl` (a short squiggle, rubble) mean
   different things under one name. Renaming them means changing
   Cheddar's tests too; left for when those tests move here.
5. **Dash gap: keep apart.** One gap (0.55 m times the factor) lost the
   presumed walls of Golgotha, CJPitch, Connection and FairyChimneys:
   elevations draw roofs more sparsely, so they keep 1.2 m.
6. **Tolerances on legs: to discuss.** How closely lines follow the
   sketch (`wall_tol_rel` and the others) goes with the legs' length
   (`scale.at`), not `scale.factor`. Moving them changes every drawing's
   smoothing, a visual judgement; not tried.
7. **Output depended on string hashing: fixed.** The legs of a scrap
   were read from sets of station names; now sorted. Every drawing is the
   same whatever `PYTHONHASHSEED` is.
8. **Blocks: by hand.** Green means flowstone, not blocks (blocks can be
   of flowstone). There may be no good rule; changed by hand after the
   script.
