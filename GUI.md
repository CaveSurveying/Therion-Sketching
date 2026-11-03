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

- **Cave**: the cave's repository (the folder holding
  `tools/project.toml`), and the Python that runs the scripts.
- **Trip**: one of the cave's surveys (`survey_file` in
  `project.toml`), its plan and extended sketches (from its `.xvi`
  files; `plan_sketch` says which are plans) and the drawings they make
  (`plan_file`, `extended_file`).
- **Drawing**: author (date, name) and copyright (year, holder) for
  `plan` and `extended`, and whether the plan takes floor steps from
  the extended sketch (`--floor`).
- **Steps**, each run on its own or a drawing's steps all in order:

  | Group | Steps |
  |---|---|
  | Check | the plan sketch, the extended sketch |
  | Plan | `plan`, `roofs`, `details`, `smooth` |
  | Extended | `extended`, `roofs`, `smooth` |
  | Cave | Therion's database (`tools/layout.thcfg`), `place`, `sections` (report, write) |
  | Checks | `review check`, `th2lint`, `fillcheck --build` |

  Each step shows whether it last ran well, and its output goes to the
  log. A drawing's steps stop at the first that fails. Stop ends the
  running step.
- **Asks first** before what can lose work: replacing a drawing that is
  not SexyTopo's export (`--force`, its hand edits are lost) and
  `sections --write` (changes every plan drawing in the cave).

The window does no converting itself: every step is the command line
(`python3 -m tools.sketch2therion ...`, `therion ...`) run in the cave's
folder, so the README and the window always do the same. `trip.py`
builds the commands, without Qt, and is tested in `tests/`.

The cave, its Python, the survey, the author's name and the copyright
holder are remembered on this computer (Qt's settings), for each cave.

## Plan

Done: `trip.py` with its tests, `Project.surveys()` (which `joins` now
uses too), `gui.py` (the window above) with its tests, this file and the
README.

Later:

- Options from `project.toml` in the window, and saved back to it with
  its comments (needs `tomlkit`); where author and copyright are kept
  (each cave, each person) is still to decide.
- A trip outside the cave's folder (a `.th` chosen anywhere), and caves
  whose surveys are not each in a folder of the cave's folder
  (most of Swildons' trips are deeper down, as `streamway/...`; the
  window finds only `Tratmans`).
- `review gaps`, `review show` and `joins` in the window.
- Reading SexyTopo's own files (`.json`) directly, with SexyTopo's
  (Java) code.
- An extended elevation drawn from the splays alone, for a trip with no
  extended sketch.
