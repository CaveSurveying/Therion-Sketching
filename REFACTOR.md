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

## Steps (one commit each)

1. `geom.py`: the small geometry helpers (a stroke's length, its span)
   in one place instead of copies in seven modules.
2. One test for a closed loop and one for a curl, with the limits each
   caller uses today as parameters.
3. One place for the size of a boulder (plans measure it across,
   elevations round), next to `scale.factor`.
4. The steps the plan and elevation conversions share (slips of the pen
   cut out, the sketch split, the local scale set, notation, presumed
   walls, flowstone marks) in one function each, called by both.
5. Strokes classified once (`reading.py`): boulders, rubble, mud, rock
   edges, notation, dashed lines, water, formations, for each
   projection; plans and elevations then use what they need.
6. The output of boulders, areas and wall subtypes from one place.

Steps 5 and 6 may stop short where the two conversions really differ;
the list says where.

## Disagreements to settle

Kept as they are; each changes drawings when settled.

(Filled in as the steps go.)
