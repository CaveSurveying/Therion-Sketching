# Drawing Therion scraps in the Cheddar Catchment survey

How to draw or edit Therion scraps (`.th2`) and what to check afterwards.
It started from a Therion expert's review of converted drawings and is
kept up to date from each drawing session and review (see "Updating
this file"). `tools/sketch2therion` (`plan`, `tidy`, `sections`) follows
it; keep to it when editing by hand too.

Rules tagged **[lint: id]** are checked by `python3 -m tools.sketch2therion.th2lint`
under that id; every id here has a check there, and the reverse. The other rules
need a person to look at the render.

Examples are from LongwoodValleySink. For another cave, read
`<Cave>` for `LongwoodValleySink` and `<Cave>/Plan_only.thcfg` for its
plan-only config.

## Hard rules

These are never broken, by the converter or by hand. They are added,
removed or changed only with the user's confirmation; the rest of this
file is worked out from reviews and may be tuned.

1. Every outer line of the passage is a wall. Only in exceptional
   circumstances is it not, and then it has `-outline out`. Never
   `-outline none`.
2. A scrap has only one outer wall on each side of the passage: in an
   elevation one floor and one roof wherever it is cut across. A line
   along a wall inside the passage is a border, or not drawn (debris is
   a line with small rocks along it: the rocks are not a second wall).
3. A wall is never made a border to mend the outline; the drawing is
   mended instead.
4. In a plan, scraps never meet at a junction (a cut on the leg next to
   it keeps the junction whole: CJPitch, CJS, CrossRoads).
5. Legs and splays are inside the passage fill, except at passage ends
   not drawn yet (a splay crossing a wall by a little is a drawing
   error).
6. The converter never writes `-reverse on`: in every projection,
   cross sections included, walls are drawn with the passage on their
   left **[lint: wall-side]**. `-reverse on` is for hand edits only (the
   user, 2026-10-28: cross sections came out either way round).
7. A cross section is drawn over its sketch, wherever it is sketched
   (plan or elevation): its scrap (`-projection none`) is in the th2
   file of the xvi it is sketched in, at the coordinates it is sketched
   at, so xTherion shows it there. Its `line section` and
   `point section` are in the scrap that holds its station, and its own
   scrap is never in a map: the `point section` places it (the user,
   2026-10-28).

## Names and files

- New config files are named `name.thcfg` (e.g.
  `LongwoodValleySink/Plan_only.thcfg`). Older names (`thconfig`,
  `thconfig_A0plan`, SexyTopo's `X.thconfig`) stay as they are.
- A survey `X` lives in `<Cave>/X/`, in `X.th`. Its drawings are named
  by the survey and the view, as SexyTopo exports them (settings under
  "Sketching in SexyTopo"). The plan is `XP.th2`, the extended elevation
  `XEe.th2` (scraps `XSEe1`, …, in `map XMEe`; `XSE1` is an error, the
  user 2026-10-22) and a projected elevation `XE###.th2`, where `###` is
  the bearing looked towards in three digits (`XE000.th2`, `XE090.th2`,
  `XE315.th2`). Sketches are `X/Notes/XP.xvi` and `X/Notes/XEe.xvi`
  (the user, 2026-10-26). The tools find a drawing's sketch from its
  backdrop, never by these names (the user, 2026-10-30). Every drawing
  has these names, older ones renamed to them (`X.plan.th2`,
  `X.extended.th2`, `X.ee.th2`, `XE90.th2`; the user, 2026-10-29). An
  extended elevation is drawn as sketched: laid out with the survey's own `extend` flags,
  not as it falls in the whole cave.
- Plan scraps are `XSP1`, `XSP2`, …, cross sections `XPX<station>`; extended
  elevation scraps `XSEe1`, …; projected elevation scraps `XSE315_1`, ….
- `X.th` has a `map XMP` listing its plan scraps (and `map XME315` for
  the elevation). The cave's plan map, `LongwoodValleySinkMP` in
  `LongwoodValleySink.th`, lists `XMP@X`; `Maps.th` holds group maps
  such as `CyclopsMP` (which lists `CyclopsSP1@Cyclops`) that it can
  list instead.
- Filenames and `input` lines must match in letter case: CI runs on
  Linux, where `TickleWest.th` and `ticklewest.th` are different files.

## Licence and authorship

- Survey data and drawings have the cave's licence, set in
  `tools/project.toml` (`[drawing] licence`), e.g. CC BY-NC-SA 4.0 for
  the Cheddar Catchment and GPLv3.0+ for Swildons (the user,
  2026-10-26). The tools are GPLv3.
- Every new scrap has `-author <date> "<Name>"` and
  `-copyright <year> "<Name>, <licence>"`, the cave's licence
  (Swildons `-copyright 2026 "Andrew Atkinson, GPLv3.0+"`). Older Cheddar
  scraps give the licence only. **[lint: scrap-author-copyright]**
- Sheets print the licence and credits from `map-comment` in the
  layout, giving the cave's licence.

## Walls and the outline

- `line wall` has `-outline out` by default; do not set it.
- Walls are the scrap's outline. Draw each wall with the passage on its
  **left** (the side of xTherion's tick), in plans, elevations and cross
  sections alike, or add `-reverse on` if the passage is on its right.
- A wall round an internal pillar has `-outline in`.
- Do not bridge real gaps between walls with made-up lines: Therion
  closes the outline itself (but ends that nearly meet are one point,
  below). No invisible walls (`line wall -subtype invisible`)
  **[lint: wall-invisible]**.
- Every line has at least two points **[lint: line-points]**.
- Never use `-outline none` on a wall **[lint: wall-outline-none]**.
  Every outer line of the passage is drawn as a wall; a line inside the
  passage is not a wall (see below).
- The furthest drawn line out from the passage is the wall (the
  surveyor could only have drawn it by seeing it). Only in exceptional
  circumstances is it not a wall, and then it has `-outline out`, so it
  is still the edge of the passage (hard rule 1; the user, 2026-10-26).
- A sump keeps an opening in its wall about 1 m wide where the dive
  line goes on (from the Swildons drawings, where the sketch shows the
  line through the pool; the user, 2026-10-26).
- Outer or inner is decided by the line's own passage: the legs that
  see it (no other drawn line between), within 1.5 m of the nearest. A
  line is inner (a border) only with those legs' stations on both sides
  of it, or their splays crossing it and reaching more than 0.5 m past
  it (a splay crossing a wall by less is a drawing error; one from a
  station on the line doesn't count). A station whose nearest point on
  the line is within 1 m of its end doesn't say (the line hands over to
  the next wall there). With no station to say, the legs do, and if they
  tie, the leg along the line. Otherwise it is a wall, drawn with the
  passage on its left: draw it that way round, and keep `-reverse on`
  for hand edits.
- A wall is never made a border to mend the outline. Where the outline
  crosses itself the drawing is mended: a small loop at a sharp turn cut
  out, walls run on past a corner cut back to it, two wall pieces ending
  together joined into one, a stray wall mark (under 0.5 m, joined to no
  other wall) dropped; anything left is reported to check.
- Wall ends that nearly meet (under 0.3 m) are one point, in a scrap and
  across a scrap join; a step or border ending on such an end moves with
  it. A drawn line that joins two wall ends (to within 15 cm) is wall.
  Two free wall ends under 1 m apart, each the other's nearest, meet if
  each wall heads within 20 degrees of the other end (a gap in a wall:
  the walls run along it; at a continuation they are nearer square to
  it), where the outline is no worse.
- Lines of one kind (walls, borders, floor steps, pits, overhangs, the
  same subtype) that run on into each other are one line, whatever their
  length: floor steps above all, as their ticks look wrong at a break.
  Therion caps each line's ends, so pieces show as bumps where they
  meet, and a piece lying along another wall draws it twice. A new line
  starts only where the wall changes kind (wall to presumed) or turns a
  real corner (Swildons review).
  Ends too close to tell apart join whatever the angle (a sharp turn stays
  a corner); ends up to 0.3 m apart join if the line carries on, turning
  no more than 60 degrees. A wall, step, pitch or overhang is never turned
  round to fit; a border may be. Not joined: a line a `join` names by its
  id, where a third line of the kind ends (a junction), or where a wall's
  outline would be worse. 3 or 4 nodes is a preferred minimum for a line,
  not a length; a short line not running on into one of its kind just
  happens sometimes (the user, 2026-10-22; to be developed as we go;
  `join_runs`). A wall piece under
  5 cm on another wall's end is a slip, not drawn. A short piece running
  on from a border is a border (Connection 13 to 15). Merged lines are
  smooth through the joins: no corner is kept at a join unless the
  sketch has one there; pieces closing a loop make one `-close on` line,
  smooth all round (ConnectionSEe3's presumed `-outline in` wall, the
  user's edit).
- A station on a line: its splays reaching well out on both sides, across
  the line's length and into the drawn passage, make the line inner
  (Connection 15); splays into passage not drawn yet, or past the line's
  end, don't (TridentLeft 35).
- In an elevation, a passage seen across a line with nothing between is
  the passage below or above it, not one beyond: the line is inner, the
  floor of one and the roof of the other.
- In an elevation, a line two or more splays straight up or down end
  on, all from one side, with none from the other side reaching it, is
  that side's floor or roof: a wall (BoldStep 1 and 4: the floor of 0
  to 4, over the passage at 5 and 6).
- In an elevation the splays straight up and down say which floor and
  ceiling is which: a wall a scrap's station's splay ends on is that
  scrap's (both scraps' if splays of each end on it), and a grey line two
  or more splays end on is a wall, a floor or ceiling (Connection 22 to
  26).
- A splay crossing a line counts as passage beyond it only if it ends in
  the drawn passage (one up an aven doesn't: Connection 15 to 16).
- Walls round an outline all run the same way (a short piece by a
  junction is not drawn start to start with the wall beside it).
- Two walls side by side between two scraps' passages (both passages'
  legs along them): the one on the other passage's side is that scrap's
  wall (GoSouth 16 to 21).
- Hand edits used as examples are checked against these rules first
  (an edit can carry a mistake too: TridentLeft 27, a piece the wrong way
  round).
- Two walls drawn on past the corner where they meet (crossing near an
  end of each) are cut at the crossing and the ends past it go (Trident
  17, hand edit). The rock the fill's closing-up takes in (a tongue
  between two walls, round a passage end) is not passage, in elevations
  as in plans; a station within 0.1 m of a face's edge doesn't make it
  passage.
- An outer line ending on the middle of a wall (a T) is a wall there as
  a hand edit does it: the wall split at the T, and the piece of it
  then inside the passage a border, if its legs say it is inner.
- Only strokes in a wall colour (black in plans) can be outer lines. A
  grey or brown line inside the passage is a border whichever side the
  legs are on (a channel either side of the leg: TridentLeft 21 to 29).
- A black dashed line (no ticks) is a wall the surveyors could not see
  all of, where the passage carries on: `line wall -subtype presumed`.
  Each dash joins only its nearest dash ahead and behind (two dashed
  lines side by side stay two: FairyChimneys 12); in an elevation dashes
  up to 1.2 m apart are one line (a big chamber's roof is drawn
  sparsely: FairyChimneys 34 to 39). Dashed lines are found before the
  strokes are shared out between scraps.
- A short stroke (0.3 m or more) in a wall colour joined end to end to
  the wall at both ends is wall too (FairyChimneys 9: a floor drawn in
  short brown and green pieces).
- The outline must not cross itself, and no wall may loop back on
  itself. Otherwise Therion warns "invalid scrap outline" (no 3D model
  for the scrap) or MetaPost "scrap outline intersects itself".
- MetaPost also gives that warning for an outline that does not cross
  itself, when it miscounts its turns: where one wall ends on the next,
  Therion joins them with a line of no length, which MetaPost takes as
  pointing east, so walls running roughly west across the join can lose
  a whole turn. `mp_turning` in `smooth.py` counts as MetaPost does;
  making the two walls one line, or turning their ends slightly off due
  west, fixes it (`review check` shows it).
- Walls meet at exactly the same point: ends 0.3 units apart make a
  backwards step that crosses the outline.
- A curve fitted through a narrow tip can fold over itself: draw a tip
  through the sketch's corner points, with a sharp corner.
- Bays and alcoves, where the wall bends in and out, are wall: do not
  let Therion close a bend with a straight line.
- A pinch between two pools is a real narrowing of the walls.
- A line inside the passage (a ledge, the edge of another level) is a
  `line border`, not a wall.
- A passage that drops below another (a rift under the main passage)
  is drawn in its own scrap or alongside. Its edge under the upper
  passage is a `line floor-step`, and the upper passage's edge over it a
  `line overhang`, not walls: walls are only the cave's outer edges.
  Noses and fins of rock between passages are drawn; a scrap's closing
  line does not fill across them.
- Before taking `-outline out` off a line, check the `join`s in the map
  files: a scrap joined to another needs that edge.
- A new line has the same options (`-outline out`) as the neighbours it
  runs on into, or it is not merged with them.
- Passages that overlap in plan, or only come close together without
  joining, go in **different scraps**: one scrap would join them up and
  turn the walls between them into borders. A leg from one into the
  other (dropping into a passage below) is between the scraps. For the
  converter, list each scrap's stations under `[scraps]` in
  `tools/project.toml` (GoSouth: 15 to 17 drops into the passage beside;
  19 comes close to 10 and 11 but does not join them).
- One wall that runs from one scrap into the next is two walls that
  meet exactly: the last point of one is the first of the other.
- Where a passage was not sketched, walls may be drawn from the splays,
  as `line wall -subtype presumed`. Never guess a wall that neither the
  sketch nor the splays show.
- Where a new survey joins an earlier one's drawn plan at an equated
  station, the earlier plan's walls are cut back
  to where the new survey starts: its walls drawn on past the join,
  across the new passage's mouth or along a stretch the new survey
  surveyed again, go. The walls are not moved: a line is cut by adding a
  point on it (splitting the curve there), at the point nearest where a
  new wall starts. A scrap of wall left at a line's end in the new
  passage goes too (the user, 2026-10-13; `python3 -m
  tools.sketch2therion joins`, its pictures in `review/joins/`). Only
  equated joins: passages overlapping in plan with no equate pass over
  or under each other (their heights differ) and both stay whole
  (FairyChimneys 38 to 40 over RoundTheBend by 135; the user,
  2026-10-14).

## Symbols: general

- Default clipping normally gives the best result. Most symbols are
  clipped by the outer walls; use this for the best effect.
- `-clip off` only in exceptional cases, with a `#` comment on the line
  before saying why. **[lint: clip-off-reason]**
- Labels and cross sections must not overlap passage or each other,
  including when combined with other surveys on the same sheet.

## Symbols: points

- Slope arrows (`point gradient`) are inside the walls, do not cross
  steps or pitch edges, and are not in water.
- Water flow (`point water-flow`) is inside the walls.
- Climbs and pitches are labelled `C2`, `P5`: no units **[lint: climb-units]**,
  in whole metres, placed outside the passage.
- Draught arrows (`point air-draught -orientation N`) go beside the
  passage, not across it, with a `point x y date -value YYYY.MM.DD` in
  the same scrap for when the draught was seen. **[lint: draught-date]**
- Text sizes: labels use `-scale` `xl`, `l`, `m`, `s` or `xs` only
  **[lint: label-scale]**, in descending order of importance:

  | `-scale` | For | LongwoodValleySink example |
  |---|---|---|
  | `xl` | Area name | none yet |
  | `l` | Main passage | `[Triassic Tunnel]` (`Triassic/TriassicP.th2`) |
  | `m` | Minor passage | `Century` (`Century/Centry.plan.th2`) |
  | `s` | Feature | `[Dig Face May 2018]` (`Triassic2/Triassic2P.th2`) |
  | `xs` | Small note | `[Too Tight]` (`CyclopsEye/CyclopsEye.plan.th2`) |

## Symbols: lines

- Use the fewest points that follow the drawing, smooth in both
  directions.
- Rocks and boulders (`line rock-border`) are closed with `-close on`,
  ending exactly on the first point **[lint: rock-closed]**
  **[lint: close-on-first-point]**, and are not smoothed (no curve
  control points) **[lint: rock-not-smooth]**. A closed line that does not end
  on its first point gives xTherion's "no such element in array".
- Rocks are drawn in file order and clip each other.
- Large boulders get a `line rock-edge` inside them to look like 3D
  rocks.
- A group of boulders is an area (`area blocks`, or `area debris` if
  mostly small). A boulder on its own, or one large for the passage it
  is in (a quarter of the passage's narrowest width across it or more,
  also within a group), is drawn as a rock. Rocks in cross sections are
  drawn (closed brown loops there are rocks, not the section's outline).
- A rock is a simplified line drawing seen from above: its outline
  angular and roughly convex (the hull of the sketched loop cut to 5 to 8
  corners by size, corners at least 6 cm apart), its rock edges
  (`line rock-edge`, before the rock in the file: after it they are drawn
  under its fill and do not show, Slingtastic 2026-10-22) in one of three
  styles, picked for
  each rock (the same every run) so they don't all look alike:
  - a line across (about 35%), corner to a corner about opposite (two
    faces), on some rocks with a second line from another corner meeting
    it part-way;
  - pointed (about 25%): a peak towards the light;
  - a wedge (about 20%, long rocks more often): a ridge along its length;
  - a block (about 20%): the top face shrunk and moved towards the light
    (top left), its shadow side drawn.
  Every corner inside the rock where edges meet has at least three lines
  meeting there, as at a corner of a solid, usually going out to corners
  of the outline. Every end of a rock edge is on a point: a node of the
  rock's border or of another rock edge, never loose inside the rock (a
  ridge runs on to a corner; the user, 2026-10-22). Rocks lower on the page are drawn later, in front. Not
  copied from other drawings.
- Walls that are rock or debris keep their subtype
  (`line wall -subtype debris`, `-subtype blocks`): drawn rocks do not
  replace them.
- Rocks on the edge of a passage are best drawn going over the wall.
- A rock fully outside the walls is never drawn, nor one more than half
  outside (Connection extended, the user: the boulders across the floor
  below station 1, 14 to 37% inside, and one under the debris floor by
  11 removed).
- Rocks along a wall (floor) line are not drawn: the wall's subtype
  (`debris`, `blocks`) draws them in Therion's style. Only significant
  ones on a wall line are drawn (a boulder, about 0.3 m across or more).
  On a wall line is measured from the sketch's floor stroke as well as
  the drawn wall (ConnectionSEe4: a small rock 0.53 m from the drawn
  wall but on the sketched floor, removed by the user).
- Steps, by height:
  - significant boundaries and low steps under 20 cm: `line border`;
  - 20 cm to 2 m and easily climbed: `line floor-step`;
  - harder climbs and anything over 2 m: `line pit`.
- The low side is the left of the line's direction (see above).
  Existing LongwoodValleySink drawings use `line pit` both ways round
  (45 plain, 17 with `-reverse on`): check old ones when they are next
  edited.
- Use `line overhang`, not `line ceiling-step`, for ceiling steps and
  overhangs (dashed lines with a tick on each dash in the sketch).
  **[lint: ceiling-step]**
- Therion draws the ticks of `line floor-step` and `line pit`, and the
  teeth of `line overhang`, on the **left** of the line's direction
  (test render with the house symbols from `common_layout.th`,
  2026-10-07): draw the line with the low (or
  overhanging) side on its left. In the sketch these are lines with
  ticks on the low side; really small steps are plain solid lines and
  are drawn as `line border` (grey in rock, brown in mud).
- A line that ends at a wall (or another line) ends exactly on one of
  its nodes. **[lint: end-on-node]** (walls only so far)

## Symbols: areas

- No `clay`, as a wall subtype or an area: mud and sand are both
  `sand` (user, 2026-10-11) **[lint: no-clay]**.

- Water: a `line border -subtype invisible -id X -close on`, and an
  `area water` that refers to it by `X`. **[lint: water-border]** No other border on
  water.
- Water against an outer wall is best drawn with its border outside the
  wall.
- Areas can overlap to show a transition, or pebbles in water.
- No borders drawn over boulder or debris areas: the sketch's lines
  among the rocks are part of the rocks, which the area's symbols show.
- An area's border has few control points and is smooth (a spline):
  where it meets a wall, run it out over the wall and let the wall clip
  it, rather than following the wall point by point.
- Individually drawn rocks can be above or below the water; this needs
  careful ordering and use of clipping.

## Extended elevations

- In a pitch the passage reaches sideways from the legs to the walls on
  each side, as far as the side splays go: a shaft's walls are often
  drawn far from its legs (OIAS_V2, 2026-10-22; `pitch_fill`).
- Walls carry a subtype for what they are drawn as: `sand` (brown: mud
  or sand, never `clay`), `flowstone` (green, smooth or running down
  a step), `blocks` (rock on the floor: green boulders or a humpy line),
  `debris` (a floor with rubble: brown curls, or a line with boulders
  drawn along it), plain `line wall` for rock. Boulders along a line
  make it debris, not sand.
- A green stroke carrying a wall on, end to end, where no other line is
  drawn, is the wall there, `flowstone` (Trident 31 to the sand floor,
  FairyChimneys 34: the user).
- A line with short straight ticks hanging from it (three or more, on one
  side) is a `line overhang`, drawn with the ticks on its left (BoldStep
  by 4, TritonSouth by 6: the user). Brown curls under a floor are its
  rubble, not ticks.
- A closed black loop with the survey passing above and below it (a loop
  in the data) is a pillar, `line wall -outline in -close on`, not a rock
  (TritonSouth 13 to 21, `equate 13 21`: the user).
- A floor drawn only as a row of boulders or brown curls (no line under
  them) is still a floor: `line wall -subtype debris` through the tops of
  the rocks, smoothed over 1 m (BoldStep 12 to 11, user: the rocks are
  only drawn; imagine a line through their tops). Where a floor line is drawn under the row,
  through it or just over it (up to 0.5 m: FairyChimneys 25 to 28, small
  rocks drawn hanging under the line), the line is the floor and the row
  is only its debris: no second wall (hard rule 2). A row of straight brown dashes is mud
  marked on a floor drawn elsewhere, not a floor. The subtype goes on the line, `line wall -subtype sand`, never
  on a point (`subtype sand` among the points: Therion takes it, but it
  is hard to follow when editing), and does not change along a line: a
  wall that changes is drawn as one line per kind, meeting end to end.
  Colour is only a hint: shape decides.
- A line inside the passage is never a wall (no `-outline none`): every
  outer line is a wall, and inner lines are drawn as what they are
  (border, ledge, step, rock-border and so on).
- A pool is an `area water` in an invisible closed border whose first two
  points are its surface, the second with `adjust horizontal` so the
  surface is level. In an elevation, blue strokes meeting end to end are
  one surface, separate pools only where their levels clearly differ or
  a wall or boulder is between them. A floor drawn under a pool is its
  floor; where none is drawn, a wall 0.3 m under the surface is, the dry
  floor at each end carried on into the pool at its own angle down to
  it, the two joined where they meet first (the user, Tratmans
  2026-10-26).
- Water flow is a `water-flow` point just under the floor, pointing
  downhill along it.
- A curtain is a point `curtain`; a group of stalactites `stalactites`;
  no `flowstone` points (flowstone is a wall subtype). A rock in the
  passage is a `rock-border -close on`.

## Projected elevations (E315)

- Planned: Therion's database may help in making a projection, but the
  extended drawing's lines (its th2, from the extended xvi) must still
  decide it (the user, 2026-10-22). `projected`, `unfold` and `joins`
  still read the database for now.
- For now (walls parked): one scrap, `XSE315_1`, with the stations on the
  dots of `XE315.xvi`, laid out as `tools/ElevationsExx.py` does
  (xvi units, offset from the lowest station, the xvi as backdrop). The
  walls are drawn round them. The rules below are for when the walls are
  generated again.
- Generated walls (`projected X --walls --out DIR`, for review, not
  filed) are in the xvi's units, offset from its lowest station, as the
  stations-only scrap and the hand-drawn 315s are, so walls and stations
  sit on the backdrop's dots. Their scraps are the scrap chooser's for
  315 (set from the hand-drawn 315 splits, which keep larger overlaps in
  one scrap): GoSouth 3, not 7. The hand-drawn 315s are walls only, a
  few scraps each.
- Projected walls have their nodes as sparse as the plans' (about a
  metre apart, more on gentle curves): each is refitted with the same
  Bezier fit as the plans (`smooth`, within 0.1 m of the wall), not one
  node per projected point (the user, 2026-10-14).
- A survey with projected elevations but no extended one (older surveys
  with no elevation sketch) gets one unfolded from them (`unfold X`):
  each leg from the view that sees it most side on (a pitch from any
  view drawing it), its walls moved by their place along the leg and
  their height; a view with no angle (`-projection elevation`) is matched
  to its stations' 3D positions.
- The older surveys' extended drawings (`X.ee.th2`, stations only) get
  their walls drawn from the projected elevations (`unfold X --ee`) as a
  profile: along each leg, in the view seeing it most side on, the
  nearest wall above (roof) and below (floor) at their heights, drawn
  along the leg as unfolded (up to 15 m away: high roofs); a pitch takes
  the walls either side. Only walls nearest that leg or one meeting it
  count. Vertical walls away from a pitch (aven sides, passage ends) are
  not found: drawn by hand.
- Filed (`unfold X --file`; `unfold X --ee --file` for an X.ee.th2 as it
  is): `X.th` inputs the drawing with `map XMEe`, and `XMEe@X` (or
  `XMEe` with `-namespace off`, Entrance) is in `LongwoodValleySinkMEe`
  when the cave inputs the survey (not GoWest, TickleRift). The 2026
  315s are filed with `projected X --walls --file`. Generated drawings
  are filed for tidying by hand: the outline warnings they give are
  expected until then (the user, 2026-10-14).
- Learned from the hand-drawn 315s, 000s and 090s of the older surveys
  (log row 159):
  - heights carry from view to view: where two views both see a leg
    side on, roof and floor heights agree to a median 0.13 m. So a wall
    keeps its height above or below its leg when projected;
  - a view seeing a leg foreshortened draws the roof higher and the
    floor lower (median 0.23 m when nearly end on): it sees the whole
    width of the passage. The extended drawing does not hold this, and
    hiding the inner roof or floor (drawing only the outermost) did not
    match the hand drawings better, so walls are projected as they are;
  - the width of a pitch or a passage seen end on is not the plan's
    width across the view (it agrees at some, not most): it stays as the
    extended drawing has it.

- 315 is the direction the viewer faces (`-projection [elevation 315]`).
  A survey X has `X/XE315.th2` (scraps `XSE315_1`, ...) with the
  backdrop `XE315.xvi` (beside the extended elevation's sketch), Therion's
  centreline of X alone so projected; `X.th` inputs it with `map XME315`, and `XME315@X` is in
  `LongwoodValleySinkM315` (`LongwoodValleySink.th`).
- Walls only, drawn from the extended elevation
  (`python3 -m tools.sketch2therion projected X --file`): a wall point
  keeps its place along its nearest leg and its height above or below
  it; its offset along the passage is scaled by how much of the leg is
  seen across the view. A wall keeps its subtype; where the view mirrors
  the extended drawing the wall is reversed, so the passage stays on the
  same side of it.
- Scraps from the 3D model (Therion's walls from the splays, as Loch
  shows them): legs that do not meet but overlap in the view are passage
  drawn over passage, and go in different scraps; otherwise a scrap is
  as large as it can be. Judged on the PDF and iterated.
- No closing walls: Therion closes the outline (as for every scrap).

## Scraps

- Passages drawn over one another in a view go in separate scraps;
  otherwise a scrap is as large as it can be. Overlap is read from the
  3D model (as Loch shows it): `python3 -m tools.sketch2therion scraps X
  --view plan|extended|315`. Scraps listed in `[scraps]` or
  `[scraps_extended]` (project.toml) are used as they are.
- Order: plan scraps from the model built from the splays, before the
  plans are drawn; elevation scraps wait for the plans, from the model
  built from the drawn plans together with the splays. The plans are
  then checked against the model from the drawn plans (the feedback
  loop).
- Scraps meet where as few fill lines and points as possible are needed.
  In a plan: at simple, linear passage, never at a junction (a hard
  rule); near one, a leg or more down one of the passages. A split need
  not be far from the junction: on the leg next to it (CJPitch along the
  pitch leg, CJS a little back, CrossRoads) the junction is whole in one
  scrap, and that keeps the rule. In an
  elevation: near a junction most of the time, usually on a short piece
  of passage by it (WestPassage 57 to 59, CJPitch, CrossRoads), maybe on
  it, since that is where the split is needed (a rule still being
  developed).
- Examples to learn from are the pre-2026 hand drawings only; the 2026
  splits are ours.
- Two medium scraps are better than a short one and a very long one.
- Every scrap has at least two stations. They are inside the drawn
  passage, except at a continuation; in a short stubby scrap one may be
  outside it.
- Overlap: more than 70% of the smaller passage and at least 0.3 m2,
  with one leg more than 1 m beyond the other's walls (one passage in
  front of another, not the same space seen from two legs); in plan
  only passages one above the other. Set by `scraps --calibrate` from
  the splits made by hand.
- In an extended elevation an overlap of 2 m2 or more is a clash whatever
  share of the smaller passage it is (TritonSouth); the older 315
  drawings keep larger overlaps in one scrap, so not in 315.
- Where a scrap meets the next in an elevation, its walls end in line:
  a floor does not run on past the nearest end of the ceiling (or the
  next scrap's short bit of ceiling), and the other way round. Only
  where the scrap ends there: a branch joining part way along a passage
  leaves the passage's walls running on past it (TridentCentre: 3 to 4
  joins 3 to 7 from the side; its roof had been cut back to 4, the
  user).
- A wall with the scrap's own walls above and below it (for about half
  its length or more) is inside the scrap's passage, not its outer wall:
  it goes to another scrap whose legs it runs beside (within 1 m) and
  whose passage it is not inside (TridentCentre: the roof and floor of
  3 to 4 drawn inside the passage 3 to 7; Trident 10 to 12, the user).
  A short piece of the same stroke left behind goes with it.
- One sketch stroke is one wall: where a scrap has two walls on one side
  (hard rule 2) and the one behind is a piece of a stroke cut off when
  the strokes were shared out, carrying on in line in another scrap, it
  goes back to that scrap (TridentCentre: the floor rising through 4 to
  7, its start given to 3 to 4).
- A scrap holds the stations in or by its drawing; one left with fewer
  than two takes the rest of its group's stations too, even where no
  walls are drawn near them (TridentCentre 8 to 10, the user). Stations
  far from any drawing are otherwise left out (FairyChimneys 40,
  TritonSouth 1, TridentLeft 30, the user).
- Each scrap is a passage, in plan or elevation. At a junction the
  passage through it (the two ways on to the most passage) stays one
  scrap, its floor and roof running on past the junction; a branch drawn
  over it is its own scrap, holding the junction station (Trident, hand
  edit: 9-10-13 one scrap, the ramp 10 to 12 another with 10 in it). The
  branch's walls start on the through passage's walls, on a
  near-vertical line through the junction station: drawn on to it, or
  cut at it (only walls within about 2 m of the junction's height). A
  wall starting at the junction belongs to the passage whose leg it runs
  along, not the nearest (the ramp's floor runs past 13). A wall
  between two scraps' passages, alongside both legs, one either side of
  it, is a wall of each scrap (elevations).
- A station's splays straight up and down are part of its tube: a wall
  they reach goes with that scrap. A junction a branch holds is in the
  tube of the passage through it (FairyChimneys 9: the chimney over it
  is the main scrap's, not the branch 9 to 12's).
- A short run of wall strokes (3 m or less) carrying on in line, end to
  end, between two pieces of another scrap's wall is that scrap's wall
  (FairyChimneys 9: the floor under it, drawn where the branch 20 to 21
  over it is nearer).
- Where a scrap's wall ends on another scrap's wall (within 0.3 m), it
  ends at a node of it: the other wall gets a node there.
- In an elevation the fill reaches as high as the stations' splays say
  the roof is (FairyChimneys 31 to 39, a chamber 7 to 11 m high).
- In an extended elevation two legs from one station clash when each
  far end is more than 1.5 m beyond the other's walls and they share 2 m2
  or more of the drawing (Trident 10 to 12 over 10 to 13; BoldStep 5 to 7
  and 5 to 8, 2.4 m, stays one scrap).
- Think of the survey as tubes, one round each leg (its walls from the
  splays and the drawn plan, as Loch shows the model): tubes drawn over
  one another in the view go in separate scraps, the rest stay together.
  Scraps are as long as they can be, none over 150 m of legs (a
  starting figure). Stations `equate`d are one station: a loop, not two
  passages over one another (TritonSouth 10 and 18, 13 and 21).
- Overlap in an extended elevation is judged on the elevation as it was
  sketched (SexyTopo), never on Therion's extended layout or any other
  Therion output made from the drawings (PDF, SVG, xvi): the th2 files
  are got right as drawn, and the `extend` lines in the .th file tune
  Therion's layout for the final output afterwards (user, 2026-10-11).
  A station sketched in more than one place: each leg is taken between
  the places of its stations as far apart across the page as its
  horizontal length. Therion's outputs are used only to check (the fill
  holding legs and splays).
- The automatic split is meant to match the user's hand splits (GoSouth,
  Trident, Connection): they are targets for the rules, not just inputs.
- Elevations are split by passages (log row 150). At each junction the
  ways are paired into passages running through it, the straightest
  first in 3D (turning less than 90 degrees); a four-way junction may be
  two passages through it (Trident 10: 9 to 10 to 12, and 11 to 10 to
  13). Straight on is the default; which passage carries on from which
  is not always the straightest, and the user may say otherwise.
- Two passages clash when the drawn overlap of their legs that lie in
  different spaces in 3D (beyond each other's walls by 0.8 m, or from
  one station each far end 1.5 m beyond) is 2 m2 or more; or when one
  is mostly (over 70%) drawn over the other and reaches more than 1.5 m
  beyond its walls (FairyChimneys 9 to 12 over 8 to 9). Two legs in one
  chamber, or the two sides of a small loop, are one space seen from
  each (BoldStep, TritonSouth: one scrap each).
- A branch whose overlap starts further along is cut at its first
  overlapping leg, its first legs going with the passage it leaves
  (Connection 4 to 5 with the main scrap, 6 to 7 its own).
- Neighbouring passages are then put together, the longest scrap first,
  while no two in a scrap clash and none is over 150 m: as few scraps as
  can be, and as long. A junction may have only two scraps at it. A
  station shared by scraps goes in the one with most of its legs (on a
  tie, the one the survey starts in), every scrap keeping two stations.
- `python3 -m tools.sketch2therion scraps --score` compares the chooser
  with the user's splits ([scraps_extended]); a different split that
  keeps the rules may be as good, and is reported for the user to look
  at.
- Plans are calibrated from the pre-2026 plans: they split where
  passages overlap by more than 30% one above the other, on the leg by
  a junction where needed (the junction whole in one scrap).
- More than one split can be right: a split is judged by these rules
  (no passage over another in a scrap, joins at simple passage, sizes,
  stations), not by matching another split.

## Cross sections

- One scrap each, named survey + `PX` + station in a plan
  (`FairyChimneysPX5`), `EX` in an elevation.
- The section's station (its copy at the section in the xvi) is inside
  its walls, with a `point station` there. Splays out of the section's
  plane may end outside it (the user, 2026-10-26). Only the section's
  own strokes go in it, never a stroke of the main drawing.
- A cross section keeps the shape it was sketched: its outline encloses
  its station and splays, and a small section is not simplified as if
  it were passage walls (no corner taken for an overshoot because it is
  short for a passage; TridentLeft PX1 was smoothed to a sliver, the
  user). A section sketched as one stroke open at the bottom is that
  stroke with a floor straight across its ends; pebbles drawn on that
  floor make it `-subtype debris` and are not drawn as rocks
  (TridentLeft PX1, PX6, PX10).
- A section's outline is made only of its long strokes: pebbles and
  short dashes (sand marks under a floor) show what the floor is and are
  never part of the outline. Its strokes meeting end to end, however
  many and whatever their colour, are the outline, each its own line
  meeting at their ends with its colour's subtype: green
  `-subtype flowstone`, brown `sand`, or `debris` with pebbles on it,
  black plain (FairyChimneys PX5, fixed by the user: the sand dashes
  under the floor had been taken for its walls; Tratmans, the user
  2026-10-26: the subtypes were not followed).
- A blue line across the bottom of a section is the water's surface.
  Where no wall is drawn under it, the walls either side carry on the
  way they were going to 0.3 m below it, both ending level (Therion
  cannot keep them so: by their lengths), and the section is left open there: it
  is closed below only where the floor is drawn. The water is an
  `area water` whose border is invisible, its surface kept level with
  `adjust horizontal` (the user, 2026-10-26).
- A cross section is a drawing of its own: its walls never join or end
  on another scrap's (TridentLeft PX6 was joined to the plan's wall
  beside it).

- `line section` goes completely across the passage, and about 0.5 m
  past it, so the arrows are clear of the walls.
- Direction arrows do not overlap the passage they mark, and best not
  other passages.
- Every section line has its arrows **[lint: section-direction]**:
  prefer `-direction both`; arrows only at the start or end if that is
  the only option.
- Therion draws the arrows on the line's left, so draw the line with
  the view direction (along the survey, from the station towards the
  next) on its left.
- On the plan, a section line goes evenly across its passage: the same
  distance (0.5 m) past the wall on each side, not far from it. Where an
  arrow would land in another part of the passage it comes in (to
  0.1 m), and in the extreme that side's arrow is left off (the user,
  2026-10-15).
- A section drawing must not overlap a passage or another section,
  including those of other surveys on the same sheet: it is moved the
  least distance that clears it, along its section line where that is
  about as short, so it is still clear where it belongs.
- A section is moved by moving its `point section`. Therion centres the
  drawing's bounding box on it. The section scrap's own drawing is never
  moved or redrawn: it stays over its sketch in the backdrop (the user,
  2026-10-22).
  `python3 -m tools.sketch2therion sections` fixes both (see
  `README.md`, "A new trip").

## Layouts

- Water: solid blue. Sump: a darker solid blue. Water flow: the same
  colour as water.
- Text sizes as in the table above.

## Sketching in SexyTopo

- The drawing tools take the legs and splays from the sketch (`.xvi`),
  never from Therion's database or a layout Therion generates, so they
  run on any survey from its sketch and `.th` (the user, 2026-10-22).
- Text is SexyTopo's own: the labels in its Therion export (`point …
  label -text "…" -scale …`) are carried into the drawing exactly as
  written, every one a `label`; their letters, which SexyTopo also draws
  into the `.xvi`, are left out so they are not read as walls. Nothing is
  worked out (no P6 or C1.5 from the legs, row 24).
- A converted drawing never replaces a th2 holding anything the
  converter did not write: only SexyTopo's export (stations and labels)
  is written over; anything else needs `--force`.
- Planned: SexyTopo's export leaves out its symbols (ENTRANCE, used in
  OIAS Entrance as slope arrows, Therion `gradient`; pebbles, clay, which
  are fills: an area of sand and pebbles; stalactites and stalagmites,
  blocks), which are in its JSON only (a SexyTopo bug). The tools do not read the JSON; for OIAS_V2
  they were added once by hand. To be fixed in SexyTopo, or read later.
- Sketch both the plan and the extended elevation, and cross sections
  where the passage shape matters.
- Colour is only a guide: what a line is depends on its type and where it
  is. An outer line, with passage on one side only, is a wall whatever its
  colour or marks (OIAS Entrance's gully, drawn brown with ticks; the
  user, 2026-10-22).
- Colours (`tools/sketch2therion/rules.toml` tells the converter):
  - black: walls;
  - brown: mud, sand, debris and boulders, on a wall or across the
    passage (in an elevation the floor, the lower wall, often): boulders and debris are closed loops, told apart
    by size (boulders drawn singly or as an area); sand is dots or
    dashes (mud too: no clay), always as area fills; other brown lines are steps in mud;
  - grey: ceiling steps, but also floor steps, pitches and channels;
  - colours are hints and are sometimes wrong: the notation decides;
  - blue: water (a closed outline is a pool, kept to its sketched
    outline: not run along a wall it only touches);
  - green: flowstone and pretties (area fills, and point symbols for the
    different stals); solid green lines are gours (`line rimstone-dam`),
    but shape decides (below: ^ marks are flowstone, a line on a wall is
    its flowstone);
  - purple, red and orange: a passage where it overlaps another (rare;
    elsewhere it is drawn in the normal colours). Purple is its walls,
    read as black (they may join a black wall); red and orange have no
    meaning of their own, they only tell its other lines apart and are
    read by shape, as grey. Its symbols say what they are (built-in
    symbols are coming to SexyTopo). Purple will also be a clue to
    scraps once there are sketches using it (`colour_map` in
    `[convert]`; the user, 2026-10-14).
  - notes (P for a pitch, C for a climb) are SexyTopo text, new in
    SexyTopo, not strokes.
- A step or pitch is shown by its symbol (the ticks), not its colour: it
  can be any colour (brown for a step in mud).
- Short jogs in a wall where the sketcher's strokes did not meet are not
  features: the wall is drawn through them. The same goes for a wall
  stroke started again a little beside the last (the outer one is the
  wall) and for small gaps in a border.
- A stroke drawn on as the wall is wall all along, even where a border
  comes off it close by. Splays ending on a stroke show it is a wall.
- Pitches and floor steps are often drawn alike: a P near the line means
  a pitch, a C one depending on its height. The converter cannot read
  these notes and draws a floor step: check each one.
- Draw only what the plan sketch shows: no steps, pitches, labels or
  slope arrows inferred from the survey data or the elevation sketch.
- Sizes in these notes (boulders, dashes and their gaps, ticks, curls)
  are for an ordinary passage. The sketcher zooms to fit the screen, so
  where the passage is bigger or the legs longer everything is drawn
  bigger and sparser. The converter scales them locally, by the
  geometric mean of the passage size (splays) and the leg length nearby
  over 2 m, between 1 and 4 times (`size_ref`; Golgotha, Reservoir and
  Trident, 2026-10-30). Some poorly drawn marks are still missed.
- A closed loop with three or more short strokes inside, two meeting at
  one end, is a boulder with its rock edges, not a step with its ticks
  (TridentLeft plan; a hole's rim with two ticks stays a step: Trident).
- Little marks (dots, tiny loops, short dashes) come from sketching in a
  dirty place: ignore one on its own; many together are sand (dots
  or dashes: mud is drawn as sand).
- Brown dashes (up to about 1.5 m) are mud, drawn as sand: the whole
  stretch where they lie is one `area sand`, wall to wall, not a patch round each
  group; keep it off boulder and debris areas. Brown dashes beside a
  wall are mud, not the ticks of a step.
- A brown stroke curled round on itself is a boulder, even if the loop
  was not quite closed.
- Closed loops are boulders (about 0.3 m across or more) or debris
  (smaller), whatever their colour: a green loop on its own is a boulder,
  only rings inside one another are a formation.
- An area needs room to draw its symbols: leave out thin parts (under
  about 0.5 m) and small areas; this matters most for boulders and debris.
- Gours (`line rimstone-dam`) are smooth, regular arcs, not every wobble
  of the hand sketch. A ^ (a short stroke bent sharply) is a flowstone
  mark, never a gour.
- Flowstone is drawn as ^ marks. Shape decides and green is a clue (the
  user, 2026-10-26, after Tratman's Temple's large flowstone became 29
  flowstone points and 33 gours). Three or more ^ marks near each other
  (standing apart, not one drawing such as a stal's Y), with the small
  marks among them, are one `area flowstone`, grown round its marks and
  following the passage as a patch of mud is. A ^ on its own is a point
  `flowstone`. Only green ^ marks are read so, as bent strokes in other
  colours are rock outlines, step ticks and wall jogs.
- A green line along a wall in a plan is the wall's flowstone. The wall
  there is `line wall -subtype flowstone` and the green line is not
  drawn (hard rule 2). Along means beside it on the passage's side with
  no leg between, heading with it, or drawn close by it (within 0.6 m)
  on either side. A green line carrying a wall on from its end, in line
  with it and not ending on a leg, is the wall there, also `-subtype
  flowstone` (Tratman's Temple, the corner where the passage turns
  south). One ending on a leg, out in the passage, is a gour (Trident by
  the junction, kept by the user). A green line drawn on from one of
  these, in line with it, goes with it.
- Where there are several boulders or much debris, use an area
  (`area blocks` or `area debris`) rather than drawing each one as well;
  an area stops at a trench or step and does not cross to the other
  side. A single boulder is a `line rock-border` (straight sides, not
  smoothed) with its `line rock-edge` before it in the file, one edge line
  where its pieces share a point.
- Lines other than boulders are smooth: points only where the line
  really bends, with splines, not every point of the sketch. How closely
  a line follows the sketch goes with the length of the legs nearby (the
  drawing is zoomed so that legs fit the screen), not a fixed distance.
- Walls the sketcher did not quite join are joined: their ends meet
  exactly, end to end (not across the passage). Too close to see is
  relative to the legs nearby, with a minimum.
- No two nodes of a line so close that they cannot be told apart and
  picked when editing (about 2% of the nearby legs' length, at least
  5 cm; the check uses the 5 cm) **[lint: node-gap]**: where a line ends
  on a wall, use the wall's node if one is that close, rather than adding
  another beside it. How many nodes a line needs goes with how it bends:
  a long sweep needs only a couple, an S bend more.
- An area mostly outside the walls (rocks drawn along the wall) is not
  drawn. Areas run only just over the walls (about 0.15 m): more makes
  odd shapes and is not needed.
- Areas (not water) spread out from what is drawn in them to fill the
  space they belong to, but stop at walls, steps and longer borders; one
  area over a boulder floor, not each rock outlined.
- At a node, the control points either side are in line with it (a
  smooth node) unless the line needs a sharp corner there.
- A short line (2 nodes, sometimes 3 or 4) that meets a line of the same
  kind end to end is part of it: one line, not several. A line sketched
  in pieces with small gaps is one line too.
- Lines of different kinds ending close together share the end (a
  border running on as a floor step, then a pitch).
- A deliberate bulge or pocket in a wall is drawn; it is not a glitch to
  smooth away. Clear corners stay sharp.
- Mud dashes beside a line are mud, not the ticks of a step; an area of
  rocks stays on its side of the line, the mud on the other.
- Do not draw a wall where nothing was sketched: no presumed walls to
  close an outline; leave the gap for Therion.
- Where two passages, or the two sides of a bend, come close, the rock
  between them is rock: their walls are walls, not borders, and the
  passage's fill does not cross between them.
- A small loop off a wall, left open where it meets it, is part of the
  wall (a projection the wall goes round), not a boulder.
- Walls follow the sketch closely (within about 2% of the nearby legs'
  length), with nodes where the wall bends rather than where the hand
  wobbled.
- A cross section is its own scrap, drawn over its sketch (hard rule 7).
- A boulder's edge lines meet at a ridge point and end on its corners;
  more than one may be needed, but as few as possible.
- The guide for surveyors is the Claude Doc "Sketching in SexyTopo"
  (the user's, 2026-10-14); what it adds is kept here:
  - SexyTopo 1.12.3 or later. Export settings: plan file suffix `P`,
    plan scrap suffix `SP#`, plan cross section suffix `SX#`; extended
    elevation file suffix `Ee`, scrap suffix `SEe#`, vertical
    cross section suffix `SVX#`, horizontal (plan-view) cross section
    suffix `SHX#`; XVI folder `Notes` (the xvi files named after the
    th2 files, one for each cross section too, new in SexyTopo); export
    folder name blank and the export subtype box unticked. `#` is a
    scrap's number, or a cross section's station. The converter reads
    only the xvi sketches and names its own scraps (`XPX5`, `XEX5`), so
    these names do not change what it draws.
  - Trip information: the date, each person's role (the sketcher as
    `notes`) and the cave's licence (above).
  - Splay a cross section at every station, the first and last too,
    even where one was taken before. Every passage has a leg down it,
    even where nobody can get there. The passage is drawn on a little
    past the last station, and a survey never stops at a junction: if
    the last station is one, a little of each passage is drawn.
  - Elevations have cross sections too: vertical ones (the usual kind)
    and horizontal ones (drawn in plan view). Horizontal sections are
    new: no data yet, so the converter has no rule for them.
  - Notes (P for a pitch, C for a climb) are SexyTopo text, not strokes.
  - Brown is always mud, sand, debris or boulders (rocks), on a wall or
    across the passage. "Floor" is only the name for the lower wall in
    an elevation, whatever it is made of.
  - Surveyors call an overhang in an elevation a traverse: the same
    thing, a line with ticks hanging from one side (`line overhang`).
  - Pillars can be in plan or elevation, and may be mud (not enough
    data yet for a rule on mud pillars).
  - Steps and pitches are shown by their ticks, generally grey, but
    brown for mud or a boulder edge and green for a large calcite dam.
  - Water: a closed blue outline (perhaps hatched) is a pool; a blue
    squiggle with an arrow is water flowing that way.
  - What was written for elevations holds for plans too: a closed loop
    the survey goes round is a pillar; a wall's colour says what it is
    (black rock, brown sand or mud, green flowstone); a wall of
    boulders with no line drawn runs through their tops, a line drawn
    under or through them is the wall and the boulders its debris; a
    row of short straight brown dashes on a wall line is mud. (The
    converter does these in elevations only so far, except green walls,
    in plans too.)

## Git and CI

- Case-sensitive filenames (see above).
- One survey per commit, with anything learnt added to this file in the
  same commit.
- CI and `th2lint` must be green before merging.

## Checking

Build with `therion -l ../output/therion.log Plan_only.thcfg` in
`LongwoodValleySink/`, then (logs in `output/`):

- `grep -E "^therion: error|invalid scrap outline" output/*.log`:
  there should be none.
- `grep "intersects itself" output/*.log | sort -u`: only scraps you
  didn't touch.
- `python3 -m tools.sketch2therion.th2lint --from LongwoodValleySink/Plan_only.thcfg`
  is clean.
- `python3 -m tools.sketch2therion review check X/XP.th2`: every
  outline valid and its turning number not 0 (0 is MetaPost's
  "intersects itself"), before building; and no "second wall on one side
  of the passage" (hard rule 2: an outer wall within 1 m behind another,
  seen from the nearest station, for 1 m or more).
- `review show` (see `README.md`, "Reviewing a drawing"): the drawing beside the sketch
  round the new stations, with someone who knows the cave.
- Render and look. poppler (pdftoppm, Evince, Okular) can show white
  holes in Therion's smooth altitude shading that are not in the PDF;
  check with another renderer (MuPDF) before chasing them.
- PDF viewers show overlapping rocks fading rather than clipping; this
  is a viewer fault, do not try to fix it.

- This file is the source of truth: check every drawing run against
  every rule here, and record what a review teaches.
- At the end of every run that edits th2 files, build the whole cave in
  plan, extended elevation and 315 projected elevation, from one config
  (`LongwoodValleySink/Whole_cave.thcfg`, PDFs and SVGs in
  `LongwoodValleySink/Outputs/WholeCave*`), and check legs and splays
  against the fill: `python3 -m tools.sketch2therion fillcheck --build
  [--survey X ...]` (report in `output/check/fillcheck.txt`). The SVGs
  draw the same as the PDFs.
- Check the PDF after processing drawings. The coloured fill shows
  where Therion thinks the passage is (inside the walls). Legs and
  splays are all inside the fill, except at passage ends where the
  continuation is not drawn yet. A splay end may occasionally go
  outside a wall: record it as a thing to check if it is outside by
  more than 0.5 m.

## Reviewing a drawing with someone who knows the cave

The converted drawings follow the sketches closely but misread them in
predictable ways, and only someone who has been there can settle some
of it. What worked (Swildons, 2026), in order:

1. Agree the scope first (plan before elevation: the elevation is a
   bigger job) and work through it a few spots at a time.
2. Find the spots yourself before asking: `review gaps` (straight
   closing lines where the sketch has a wall), merged pools, steps that
   should be walls, lines that weren't drawn. Fix what the sketch makes
   certain; ask about the rest.
3. Ask with pictures, never with words alone: `review show` puts the
   sketch (its colours, legs and station names) beside the drawing with
   station names (`review build` first). One picture per question,
   numbered, 3 to 7 per batch, each naming the stations and giving the
   default you'd take, so the answer can be a word.
4. After fixing, show sketch, before and after (`review show --before`,
   with the old `output/review-plan.pdf` copied aside before editing),
   build every config, and compare the "intersects itself" list with
   the last build: no new warnings.
5. Commit and push each round; main moves, so fetch and rebase rather
   than force.
6. Write each answer down in this file, as a rule for the next drawing.

## Updating this file

Add whatever a review or drawing session teaches, in the same commit as
the drawing. Tag a rule **[lint]** only when `tools/sketch2therion/th2lint.py` checks
it, under a new id, and add the check in the same commit.
