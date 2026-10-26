# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""The per-cave settings in tools/project.toml.

    from tools.sketch2therion import project
    p = project.load()
    p.plan_file("GoSouth")      # LongwoodValleySink/GoSouth/GoSouth.plan.th2
    p.path(p.build["sql"])      # absolute path
"""

import os
import re
import tomllib

# The cave's repository: this package is at tools/sketch2therion in it
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOML = os.path.join(REPO, "tools", "project.toml")

REQUIRED = {
    "cave": ["name", "title", "folder", "master", "survey", "thconfig", "plan_map", "plan_map_file"],
    "names": ["survey_file", "plan_file", "scrap_prefix", "survey_plan_map", "plan_sketch"],
    "drawing": ["line_endings", "map_scale", "licence"],
    "build": ["outputs", "log", "layout_plan", "layout_extended", "sql", "review_plan"],
}


class ConfigError(ValueError):
    pass


class Project:
    def __init__(self, data, root=REPO):
        for table, keys in REQUIRED.items():
            for key in keys:
                if key not in data.get(table, {}):
                    raise ConfigError(f"project.toml: missing {table}.{key}")
        if data["drawing"]["line_endings"] not in ("lf", "crlf"):
            raise ConfigError("project.toml: drawing.line_endings must be \"lf\" or \"crlf\"")
        for i, sheet in enumerate(data.get("sheets", [])):
            for key in ("file", "title", "blurb"):
                if key not in sheet:
                    raise ConfigError(f"project.toml: missing sheets[{i}].{key}")
        self.root = root
        self.cave = data["cave"]
        self.names = data["names"]
        self.drawing = data["drawing"]
        self.build = data["build"]
        self.sheets = data.get("sheets", [])
        self.convert = data.get("convert", {})     # sketch2therion settings (settings.py)
        self.scraps = data.get("scraps", {})       # survey -> station specs per plan scrap (sketch2therion/scraps.py)
        self.scraps_extended = data.get("scraps_extended", {})   # the same, per extended-elevation scrap
        self.glitches = data.get("glitches", {})   # survey -> sketch -> [[x0, y0, x1, y1], ...] (sketch metres)

    def path(self, rel):
        return os.path.join(self.root, rel)

    def _in_cave(self, pattern, survey):
        return os.path.join(self.cave["folder"], pattern.format(survey=survey))

    def survey_file(self, survey):
        return self._in_cave(self.names["survey_file"], survey)

    def plan_file(self, survey):
        return self._in_cave(self.names["plan_file"], survey)

    def scrap_prefix(self, survey):
        return self.names["scrap_prefix"].format(survey=survey)

    def survey_plan_map(self, survey):
        return self.names["survey_plan_map"].format(survey=survey)

    def qualified(self, name, survey):
        """`name@survey`, as a map in the cave's maps file refers to it."""
        return f"{name}@{survey}"

    def is_plan_sketch(self, path):
        """True for a plan sketch (.xvi), by its file name."""
        return re.search(self.names["plan_sketch"], os.path.basename(path)) is not None

    @property
    def newline(self):
        return "\r\n" if self.drawing["line_endings"] == "crlf" else "\n"

    @property
    def licence_comment(self):
        return f"# Licence: {self.drawing['licence']} (see README.md at the top of the repository)"


def parse(text, root=REPO):
    return Project(tomllib.loads(text), root)


def load(path=TOML, root=REPO):
    with open(path, "rb") as f:
        return Project(tomllib.load(f), root)
