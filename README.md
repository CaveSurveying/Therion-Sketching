# Therion Sketching

Tools and house drawing rules for turning SexyTopo (and PocketTopo)
sketches into [Therion](https://therion.speleo.sk/) drawings, shared by
every cave survey that uses them.

The script and model building work better if the
[drawing guide](sketching-guide.md)
is followed.

| File | What it is |
|---|---|
| `sketching-guide.md` | Sketching in SexyTopo, for surveyors: how to survey and sketch, and the export settings. |
| `Style.md` | The drawing rules: how to sketch underground and how the drawings are made. The source of truth. |
| `rules.toml` | The same rules as settings for the converter. |
| `*.py` | The converter (`python3 -m tools.sketch2therion`), its checks (`review`, `fillcheck`) and `th2lint`. |
| `requirements.txt` | Python libraries (`pip install -r tools/sketch2therion/requirements.txt`). |
| `tests/` | The tools' tests, run in a small test cave (`tests/cave`). |

## Using it in a cave's repository

The tools live at `tools/sketch2therion` in the cave's repository, as a
link to a clone of this repository in the same folder as the cave's:

```bash
git clone https://github.com/CaveSurveying/Therion-Sketching.git
ln -s ../../Therion-Sketching <cave>/tools/sketch2therion
```

Every cave on the computer uses whatever is checked out here, so a
branch can be tried on all of them at once. The first note in each
drawing gives the commit that made it (`-dirty` if there were
uncommitted changes).

`tools/` needs an empty `__init__.py`, and the cave keeps its own
settings next to the link:

- `tools/project.toml`: the cave's name, master survey, maps, file and
  scrap names, sheets, scraps chosen by hand and sketch glitches. A
  `[convert]` table there changes a house rule for this cave only, with
  the reason.
- `tools/th2lint-baseline.txt`: findings in the cave's existing
  drawings.
- `tools/layout.thcfg`: exports where Therion puts every station, for
  `check` (the survey's station names), `joins`, `sections` and `review`
  (the cave's drawings in one frame). A drawing keeps the sketch's own
  station positions.

Run everything from the top of the cave's repository, for example

```bash
python3 -m tools.sketch2therion plan Cave/X/Notes/XP.xvi --survey X -o Cave/X/XP.th2
python3 -m tools.sketch2therion.th2lint --from Cave/thconfig
```

The steps for a new trip are below ("A new trip"). The cave's
`tools/README.md` gives its own names, its build and any steps of its
own.

## Tests

From the top of this repository, with the libraries in
`requirements.txt` and pytest:

```bash
python3 -m pytest -q tests
```

They run in `tests/cave`, a test cave laid out as a cave's repository
is, so they reach the tools as `tools.sketch2therion`, as a cave does,
and use the house rules as they are (its `[convert]` is empty). A test
of the tools goes here, with the strokes it needs made up in the test,
or on one of the few real sketches kept in the test cave
(`tests/cave/TestCave`, from the Cheddar Catchment survey, GPLv3.0+
here). A test of a cave's own drawings, settings or build stays in that
cave's repository.

## Converting a drawing

A sketch (SexyTopo or PocketTopo `.xvi`) is converted in several steps,
always all of them and in this order: what the first step writes is not
finished, and breaks the hard rules in `Style.md` until the last step
has run.

| Drawing | Steps |
|---|---|
| Plan | `plan`, `roofs`, `details`, `smooth` |
| Extended elevation | `extended`, `roofs`, `smooth` |

```bash
python3 -m tools.sketch2therion extended Cave/X/Notes/XEe.xvi --survey X -o Cave/X/XEe.th2
python3 -m tools.sketch2therion roofs Cave/X/XEe.th2
python3 -m tools.sketch2therion smooth Cave/X/XEe.th2
```

The sketch can be kept anywhere: `plan` and `extended` write its path in
the drawing as xTherion's backdrop, and every later step, and anything
else that needs a survey's sketch (the scrap chooser, `projected`,
`stxvi`), reads it from the backdrop of the survey's drawing. Nothing
looks for sketches by folder or file name. To convert a drawing again,
give the sketch its backdrop names.

## A new trip

`<Cave>` is the cave's folder for its surveys and `X` the trip's survey.
File, scrap and map names come from the cave's `tools/project.toml`;
those below are the usual ones.

### Underground, in SexyTopo

Sketch as `sketching-guide.md` says: the colours the converter reads,
cross sections, and drawing both the plan and the extended elevation. Note in the book which existing station the trip
starts from.

### After the trip

1. **Export** from SexyTopo into the survey's own folder: `X.th`, and
   the sketches in `X/Notes/` (`XP.xvi` for the plan, `XEe.xvi` for the
   extended elevation). The cave's `tools/new-trip-template.th` shows
   what `X.th` should contain.
2. **Tie it in** in the cave's master file (`master` in
   `project.toml`): `input X/X.th`, and an `equate` from the trip's
   first station to the one it started from. Build and check the log
   for loop errors.
3. **Therion's layout:**
   ```bash
   therion -l output/therion-layout.log tools/layout.thcfg
   ```
   writes `output/layout-plan.xvi`, `output/layout-extended.xvi` and
   `output/layout.sql`. Rerun it whenever the survey data change.
4. **Check the sketch:**
   ```bash
   python3 -m tools.sketch2therion check <Cave>/X/Notes/XP.xvi --survey X
   ```
   It lists the sketch's stations, legs and lines. Stations Therion
   doesn't know mean the trip isn't input, the layout is stale or
   `--survey` is wrong. The drawing keeps the sketch's own station
   positions, so they are not compared with Therion's.
5. **Convert the plan**, all four steps:
   ```bash
   python3 -m tools.sketch2therion plan <Cave>/X/Notes/XP.xvi --survey X \
     --author 2026.04.25 "Name" --copyright 2026 "licence" -o <Cave>/X/XP.th2
   python3 -m tools.sketch2therion roofs <Cave>/X/XP.th2
   python3 -m tools.sketch2therion details <Cave>/X/XP.th2
   python3 -m tools.sketch2therion smooth <Cave>/X/XP.th2
   python3 -m tools.sketch2therion place X
   ```
   SexyTopo's labels come from its th2 export, the one with this sketch
   as its backdrop; a th2 that is not that export is not overwritten
   without `--force`. Scraps are named `XSP1`, `XSP2`, … and cross
   sections `XPX<station>`. `place` inputs the drawing in `X.th` with a
   `map XMP` of its scraps, adds `XMP@X` to the cave's plan map
   (`plan_map`), and removes SexyTopo's own empty plan th2 unless the
   drawing was written over it.

   **Convert the extended elevation** the same way, all three steps:
   ```bash
   python3 -m tools.sketch2therion extended <Cave>/X/Notes/XEe.xvi --survey X \
     --author 2026.04.25 "Name" --copyright 2026 "licence" -o <Cave>/X/XEe.th2
   python3 -m tools.sketch2therion roofs <Cave>/X/XEe.th2
   python3 -m tools.sketch2therion smooth <Cave>/X/XEe.th2
   ```
6. **Cross sections.** With Therion's layout up to date (step 3):
   ```bash
   python3 -m tools.sketch2therion sections --write
   ```
   turns each cross section line to look along the survey, carries it
   evenly across its passage (0.5 m past the wall each side, less where
   an arrow would land in another passage), and moves section drawings
   clear of the passages and each other by their `point section`, for
   every plan drawing the master file inputs. Without `--write` it only
   reports.
7. **Finish by hand** in xTherion (the sketch is linked as a
   backdrop): passage names at the label sizes in `Style.md`, flow
   arrows, `C2`/`P5`, `join`s to neighbouring scraps.
8. **Check**, as in `Style.md` ("Checking"):
   ```bash
   python3 -m tools.sketch2therion review check <Cave>/X/XP.th2
   python3 -m tools.sketch2therion review gaps <Cave>/X/XP.th2 XSP1
   python3 -m tools.sketch2therion.th2lint <Cave>/X/XP.th2
   python3 -m tools.sketch2therion fillcheck --build --survey X
   ```
   and with someone who knows the cave ("Reviewing a drawing").
9. **Commit** one survey per commit. Anything learnt goes into
   `Style.md` here ("Changing the rules").

### Reviewing a drawing

```bash
python3 -m tools.sketch2therion review build      # output/review-plan.pdf, with station names
python3 -m tools.sketch2therion review show out.png 90 91 92 --survey X [--before old.pdf]
python3 -m tools.sketch2therion zip X review-X.zip --extra review/
```

- `review build` makes the plan from the cave's build (`thconfig` in
  `project.toml`) with station names on; copy it aside before editing
  to have a "before".
- `review show` puts the sketch (its colours, legs and stations, turned
  to the sheet) beside the drawing round those stations. Station names
  restart in each survey, so give `--survey`.
- `review check` reports each outline as Therion and MetaPost see it:
  valid, and the turning number (0 means "scrap outline intersects
  itself").
- `review gaps` lists where Therion will close the outline with a
  straight line, and how much of it the sketch draws as wall.
- `fillcheck [--build] [--projection plan] [--survey X ...]` builds the
  cave's check build (`check_build` in `project.toml`) and lists legs
  outside Therion's fill, and splay ends more than 0.5 m outside it.
  Run it at the end of every run that edits th2 files.
- `zip` zips the drawing, its sketches (the backdrop works when
  unzipped), `X.th`, the master file and the files in `review/`, for
  review on another computer.

### PocketTopo

The same commands take PocketTopo files: a `.top`, or the Therion
export `_th.txt`. Two more commands help:

```bash
# a PocketTopo sketch as an XVI backdrop for xTherion
python3 -m tools.sketch2therion xvi <Cave>/X/pockettopo/X.top --view elevation \
  -o <Cave>/X/pockettopo/X_th_e.xvi
# copy PocketTopo's left/right leg directions into the trip's .th
python3 -m tools.sketch2therion extend <Cave>/X/pockettopo/X_th.txt <Cave>/X/X.th
```

PocketTopo's Therion export sometimes lists a side view's stations
somewhere other than where its sketch put them; `check` shows that as
a large distance from stations to walls. The `.top` file is laid out
the way the sketch was drawn, so convert from that instead.

## Changing the rules

A lesson learnt on any cave goes into `Style.md` and, where the
converter reads it, `rules.toml`, so every cave gets it when the clone
is pulled. The "Hard rules" at the top of `Style.md` change only
with the user's confirmation, as the file says.

## Licence

GPLv3 (`LICENSE`). Adapted from the Swildons survey's tools
(<https://github.com/paperclipmonkey/caves-mendip-swildons>), and
developed for the Cheddar Catchment survey.
