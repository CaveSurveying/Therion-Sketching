# Therion Sketching

Tools and house drawing rules for turning SexyTopo (and PocketTopo)
sketches into [Therion](https://therion.speleo.sk/) drawings, shared by
every cave survey that uses them.

| File | What it is |
|---|---|
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

## Changing the rules

A lesson learnt on any cave goes into `Style.md` and, where the
converter reads it, `rules.toml`, so every cave gets it when the clone
is pulled. The "Hard rules" at the top of `Style.md` change only
with the user's confirmation, as the file says.

## Licence

GPLv3 (`LICENSE`). Adapted from the Swildons survey's tools
(<https://github.com/paperclipmonkey/caves-mendip-swildons>), and
developed for the Cheddar Catchment survey.
