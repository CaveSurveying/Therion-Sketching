# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""List every file a Therion build needs, starting from a thconfig.

Follows `source` and `input` (relative to the file that contains them,
as Therion does) and `\\loadpicture{...}` in layout TeX code (relative
to the thconfig's folder, where Therion runs). Reports targets that are
missing, and targets that only exist with different letter case (they
work on Windows but not on Linux or in CI).

    python3 -m tools.sketch2therion.deps ROOT LongwoodValleySink/thconfig --within LongwoodValleySink
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass, field

THERION_REF = re.compile(r'^\s*(input|source)\s+(?:"([^"]+)"|(\S+))', re.IGNORECASE)
LOADPICTURE = re.compile(r"\\loadpicture\{([^}]*)\}")


@dataclass
class Ref:
    kind: str       # input, source or loadpicture
    target: str     # as written
    line: int


@dataclass
class Problem:
    file: str       # relative to the root
    line: int
    target: str
    reason: str     # "missing" or "case differs: <actual>"


@dataclass
class Result:
    files: list = field(default_factory=list)       # relative paths, in walk order
    problems: list = field(default_factory=list)


def parse_refs(text):
    """The references in one file, skipping commented-out lines."""
    refs = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line.startswith("#"):
            continue
        m = THERION_REF.match(raw)
        if m:
            refs.append(Ref(m.group(1).lower(), m.group(2) or m.group(3), n))
            continue
        tex = raw.split("%", 1)[0]          # TeX comment
        for m in LOADPICTURE.finditer(tex):
            refs.append(Ref("loadpicture", m.group(1), n))
    return refs


def _find_case_insensitive(path):
    """The real path matching `path` ignoring case, or None."""
    parts = os.path.normpath(path).split(os.sep)
    cur = os.sep if path.startswith(os.sep) else "."
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            cur = os.path.dirname(os.path.abspath(cur))
            continue
        try:
            names = os.listdir(cur)
        except OSError:
            return None
        match = next((n for n in names if n == part), None) or \
            next((n for n in names if n.lower() == part.lower()), None)
        if match is None:
            return None
        cur = os.path.join(cur, match)
    return cur


def resolve(root, base_dir, target, kind):
    """(relative path, problem reason or None) for one reference."""
    candidates = [target]
    if kind == "input" and not os.path.splitext(target)[1]:
        candidates.append(target + ".th")
    for cand in candidates:
        rel = os.path.normpath(os.path.join(base_dir, cand))
        full = os.path.join(root, rel)
        if os.path.isfile(full):
            return rel, None
    for cand in candidates:
        rel = os.path.normpath(os.path.join(base_dir, cand))
        real = _find_case_insensitive(os.path.join(root, rel))
        if real and os.path.isfile(real):
            actual = os.path.relpath(real, root)
            return actual, f"case differs: {actual}"
    return os.path.normpath(os.path.join(base_dir, target)), "missing"


def walk(root, start):
    """Every file reachable from `start` (relative to `root`)."""
    result = Result()
    run_dir = os.path.dirname(start)
    seen = set()
    todo = [start]
    while todo:
        rel = todo.pop(0)
        if rel in seen:
            continue
        seen.add(rel)
        result.files.append(rel)
        if rel.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".xvi")):
            continue
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
            refs = parse_refs(f.read())
        for ref in refs:
            base = run_dir if ref.kind == "loadpicture" else os.path.dirname(rel)
            target, reason = resolve(root, base, ref.target, ref.kind)
            if reason:
                result.problems.append(Problem(rel, ref.line, ref.target, reason))
            if reason != "missing":
                todo.append(target)
    return result


def outside(files, within):
    """The files not under the folder `within`."""
    prefix = os.path.normpath(within) + os.sep
    return [f for f in files if not f.startswith(prefix)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", help="checkout or export of the repository")
    ap.add_argument("start", help="thconfig, relative to root")
    ap.add_argument("--within", help="also list the files outside this folder")
    a = ap.parse_args(argv)
    res = walk(a.root, os.path.normpath(a.start))
    print(f"{len(res.files)} files reached from {a.start}")
    if a.within:
        for f in outside(res.files, a.within):
            print(f"outside {a.within}: {f}")
    for p in res.problems:
        print(f"{p.file}:{p.line}: {p.target}: {p.reason}")
    return 1 if any(p.reason == "missing" for p in res.problems) else 0


if __name__ == "__main__":
    sys.exit(main())
