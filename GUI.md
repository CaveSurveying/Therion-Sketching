# Therion Sketching GUI

A window that runs the converter on a new trip, step by step, as
"A new trip" in `README.md` does them by hand.

```bash
python3 -m tools.sketch2therion.gui            # from the top of a cave's repository
```

It needs Qt for Python: PySide6 (`pip install PySide6`), or PyQt6 if
that is what is installed. The scripts themselves run with the cave's
Python (its `.venv` if it has one), which needs `requirements.txt`, so
the window and the scripts may use different Pythons.

## What it does

- **Always shown**: the cave (the folder holding `tools/project.toml`),
  the survey (`survey_file` in `project.toml`), and its plan and
  elevation drawings: the th2 files the survey's `.th` inputs, each
  with the `.xvi` sketches it links as backdrops (a drawing may link
  several, often cross sections). View opens a drawing in the viewer.
- **Tabs that run**, in this order, each with a tick box for each part
  and a tick box on the tab itself, so a tab can be switched on or off
  without opening it:

  | Tab | Parts |
  |---|---|
  | Check | the plan drawing's sketches, the elevation drawing's sketches |
  | Plan | `plan`, `roofs`, `details`, `smooth` (and `--floor`) |
  | Elevation | `extended`, `roofs`, `smooth` |
  | Cave | Therion's database (`tools/layout.thcfg`), `place`, `sections` (report, `--write`) |
  | Checks | `review check`, `th2lint`, `fillcheck --build` |

  Run runs the ticked parts of every ticked tab, in order, with their
  output in the log; it stops at the first that fails, and Stop ends
  the running one. `plan` and `extended` convert the drawing's first
  sketch, the one every later step reads.
- **Author**: the name (someone in the `.th`'s team, the local default,
  or typed) and the date (the `.th`'s, or typed); the copyright, from
  the local default or the `.th`, or none.
- **Environment**: the Python that runs the scripts (the cave's `.venv`
  by default), the Therion that compiles, the viewer (xTherion or
  Therion Studio, each with a local build if wanted) and the local
  default author and copyright holder.
- **Asks first** before what can lose work: replacing a drawing that is
  not SexyTopo's export (`--force`, its hand edits are lost) and
  `sections --write` (changes every plan drawing in the cave).

The window does no converting itself: every step is the command line
(`python3 -m tools.sketch2therion ...`, `therion ...`) run in the cave's
folder, so the README and the window always do the same. `trip.py`
builds the commands, without Qt, and is tested in `tests/`.

The settings are kept on this computer (Qt's settings): the cave, and
for each cave its Python, survey, drawings and ticks; the environment
and local defaults for every cave.

## Plan

Done: `trip.py` and `gui.py` (the window above) with their tests,
`Project.surveys()` (which `joins` uses too), and `survey.py` reading a
`.th`'s inputs, team, date and copyright.

Later:

- Options from `project.toml` in the window, and saved back to it with
  its comments (needs `tomlkit`); where author and copyright are kept
  (each cave, each person) is still to decide.
- A drawing's other sketches (often cross sections) used in converting
  it: for now only its first sketch is converted.
- Therion Studio opening the drawing it is given (it opens its last
  session for now).
- A trip outside the cave's folder (a `.th` chosen anywhere), and caves
  whose surveys are not each in a folder of the cave's folder
  (most of Swildons' trips are deeper down, as `streamway/...`; the
  window finds only `Tratmans`).
- `review gaps`, `review show` and `joins` in the window.
- Reading SexyTopo's own files (`.json`) directly, with SexyTopo's
  (Java) code.
- An extended elevation drawn from the splays alone, for a trip with no
  extended sketch.
