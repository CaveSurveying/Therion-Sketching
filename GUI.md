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
  | Plan | check the sketches, `plan` (and `--floor`), `roofs`, `details`, `smooth`, `review check`, `th2lint` |
  | Elevation | check the sketches, `extended`, `roofs`, `smooth`, `th2lint` |
  | Cave | Therion's database (`tools/layout.thcfg`), `place`, `sections` (report, `--write`), `fillcheck --build` |

  Each drawing's tab runs in the order the drawing is made: check its
  sketches, convert them, then check the result. The Cave tab needs the
  trip tied into the cave.

  Run runs the ticked parts of every ticked tab, in order, with their
  output in the log; it stops at the first that fails, and Stop ends
  the running one. `plan` and `extended` convert the drawing's first
  sketch, the one every later step reads.
- **Credits**: the author's name (someone in the `.th`'s team, the
  default author, or typed, with where it came from shown after it) and
  the date (the `.th`'s, or typed); the copyright, from the default
  holder, the `.th`, typed here, or none; the licence, the cave's
  (`drawing.licence` in `project.toml`) and greyed out, as the converter
  writes no other yet.
  The default author and copyright holder are changed only with the
  Change defaults button, so it is clear the default is changing and
  not just this run.
- **Environment**: the Python that runs the scripts (the cave's `.venv`
  by default), the Therion that compiles, and the viewer (xTherion or
  Therion Studio, each with a local build if wanted).
- **Every option** has a short note on what it does, and an (i) button
  for more, giving what it changes or prints, an example of its output and
  what to do about it. The steps' texts are in `trip.SECTIONS`, the
  others in `gui.HELP`.
- **Save defaults** (bottom left) keeps the tick boxes, the copyright
  choice and the Environment as they are, for next time. Every tick box
  is on until then.
- **Asks first** before what can lose work: replacing a drawing that
  has lines or points other than stations and labels (`--force`, its
  drawing is lost) and `sections --write` (changes every plan drawing in
  the cave).

The window does no converting itself: every step is the command line
(`python3 -m tools.sketch2therion ...`, `therion ...`) run in the cave's
folder, so the README and the window always do the same. `trip.py`
builds the commands, without Qt, and is tested in `tests/`.

The settings are kept on this computer (Qt's settings): the defaults
for every cave, and for each cave its Python, last survey and drawings.

## Plan

Done: `trip.py` and `gui.py` (the window above) with their tests,
`Project.surveys()` (which `joins` uses too), and `survey.py` reading a
`.th`'s inputs, team, date and copyright.

Next:

- **A drawing's other sketches**, cross sections at least: a drawing
  often links more than one `.xvi` (cross sections sketched on their
  own), and only its first is converted for now.
- **Finding the surveys.** Scan the cave's repository for `.th` files,
  wherever they are (leaving out `tools/` and `.git`, and not following
  links), and read each one's `survey NAME` lines: every survey with the
  `.th` that declares it. No pattern and no master file, so a new trip
  is found before it is tied in, and Swildons' trips two folders down
  (`Streamway/TratmansToSump1/TratmansToSump1.th`) or several to a
  folder (`Entrance/EntToWaterChamber/ZigZags.th`) are found too. A
  name declared in more than one `.th` (Swildons' `SwildonsHole`,
  `wstanton`) is shown with its path. The window uses that `.th`, not
  one built from `survey_file`.
- **One piece of code for it**, in `survey.py`, replacing
  `sections.survey_files` and `Project.surveys()`; `sections` and
  `joins` use it too, unless there is a good reason not to. `joins`
  builds a survey's `.th` path from `survey_file`, which is why it
  fails on Swildons (`BarnesLoopToTratmans.Swildons/...`).

Later:

- **Style in the window, editable in the end.** `Style.md` should hold
  only how a drawing looks. Today it also holds names and files,
  licence and authorship, how the converter reads a sketch, Git and
  CI, checking and reviewing. Not one Style tab, as the rules belong
  with what they govern:
  - general drawing rules (the hard rules, walls and the outline,
    symbols, scraps) shared by plan and elevation, in a tab of their
    own
  - plan only rules (cross sections) with the Plan tab, elevation only
    rules with the Elevation tab
  - names and files with the cave's settings (`project.toml`), as they
    differ for each cave
  - licence and authorship with Credits
  - how the sketch is read with the steps that read it (`plan`,
    `extended`)
  - Git, checking and reviewing stay in the README, linked from the
    check steps' (i).

  Splitting `Style.md` to match comes first. What can be edited is
  still to decide (the numbers in `project.toml` are easy, the prose
  less so), and hard rules change only with the user's confirmation.
  `Style.md` is shared by every cave, so editing it in the window
  changes Therion-Sketching, not the cave.

- Options from `project.toml` in the window, and saved back to it with
  its comments (needs `tomlkit`); where author and copyright are kept
  (each cave, each person) is still to decide.
- Therion Studio opening the drawing it is given (it opens its last
  session for now).
- `review gaps`, `review show` and `joins` in the window.
- Reading SexyTopo's own files (`.json`) directly, with SexyTopo's
  (Java) code.
- An extended elevation drawn from the splays alone, for a trip with no
  extended sketch.
