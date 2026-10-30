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

The converter's output depends on Python's string hashing (the order sets
are gone through), so runs are compared with `PYTHONHASHSEED=0`.

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

Not done: the rest of sharing the reading of a sketch (boulder sizes, one
stroke classifier, notation, the output of boulders and areas) cannot be
done without changing drawings, because the copies disagree. Each is in
the list below; once a disagreement is settled, the shared code follows
and the drawings change as that decision says.

## Disagreements to settle

Kept as they are. Recommended choice first; each changes drawings.

1. **Closed loop.** Plans (and water pools): ends within 0.15 m or 20%
   of its length, at least 0.2 m long. Elevations: 0.15 m times the local
   factor, or 15%. Scraps and formation rings: 0.1 m. Cross section rocks,
   floor marks, green walls, symbols' boulders: 0.15 m. Recommend 0.15 m
   times the local factor, or 20% of the length, everywhere.
2. **Boulder size.** Plans: a closed loop 0.3 m across or more is a
   boulder, smaller is debris, under 0.15 m dirt (`boulder_min`,
   `mark_max`). Elevations: a closed stroke up to 1.5 m round (times the
   factor) is a boulder in a row along the floor, with no lower limit
   (`BOULDER_MAX`). Symbols: a blob 0.2 to 2.5 m across, or a closed
   loop under 3 m round. Recommend the plans' rule everywhere (across,
   0.3 m boulder, 0.15 m dirt), and no upper limit for a boulder in a
   row (a large one is still a boulder).
3. **Ticks.** Plans (`notation.ticks_of`): 0.06 to 0.45 m (times the
   factor), within 0.15 m of the line, at 45 degrees or more to it.
   Elevations (`elevation._overhangs`): 0.08 to 0.45 m (not scaled),
   within 0.12 m, leaving the line across. The meaning differs by
   projection (a ticked line is a step in plan, an overhang in an
   elevation), but finding the ticks need not. Recommend one tick
   finder (the plans'), scaled, with the meaning left to each projection.
4. **Curls.** Plans (`marks.is_curl`): a stroke curled round on itself,
   a loop not quite closed (a boulder). Elevations (`elevation.is_curl`):
   a short squiggle under 1.5 m across (times the factor), rubble; and
   `_curled`, any mark that bends back on itself. Recommend keeping the
   two meanings but naming them apart (`curled_round` for an unclosed
   loop, `squiggle` for rubble), shared by both projections.
5. **Dash gap.** Plans 0.55 m, elevations 1.2 m; both now times the
   local factor, which covers the big chambers the 1.2 m was for.
   Recommend one gap (0.55 m times the factor), checked on FairyChimneys
   and Connection, the cases the 1.2 m came from.
6. **Tolerances on legs.** How closely lines follow the sketch
   (`wall_tol_rel`, `line_tol_rel`, `node_gap_rel`,
   `wall_ends_meet_rel`) still goes with the length of the legs
   (`scale.at`), not `scale.factor`. Recommend moving them to the factor.
7. **Output depends on string hashing.** Converting the same sketch
   twice gave different drawings in three cases (TridentLeft and Trident
   plans, TritonSouth elevation) until `PYTHONHASHSEED` was fixed: sets
   of names are gone through in hash order somewhere. Recommend finding
   it and sorting, so each run gives the same drawing.
8. **Blocks.** Not settled (green means flowstone, not blocks; blocks can
   be of flowstone). There may be no good rule; left for changes by hand
   after the script.
