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
  the converter.

Run everything from the top of the cave's repository, for example

```bash
python3 -m tools.sketch2therion plan Cave/X/Notes/XP.xvi --survey X -o Cave/X/XP.th2
python3 -m tools.sketch2therion.th2lint --from Cave/thconfig
```

The steps for a new trip are in the cave's `tools/README.md`.

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

## Changing the rules

A lesson learnt on any cave goes into `Style.md` and, where the
converter reads it, `rules.toml`, so every cave gets it when the clone
is pulled. The "Hard rules" at the top of `Style.md` change only
with the user's confirmation, as the file says.

## Licence

GPLv3 (`LICENSE`). Adapted from the Swildons survey's tools
(<https://github.com/paperclipmonkey/caves-mendip-swildons>), and
developed for the Cheddar Catchment survey.
