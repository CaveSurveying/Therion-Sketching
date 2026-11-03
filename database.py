# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""Therion's database export (`export database -fmt sql`), read with
SQLite. tools/layout.thcfg writes the cave's to output/layout.sql.

    db = database.connect(path)
    for i, name, survey, x, y, z in database.stations(db): ...
"""
import re
import sqlite3


def sql_text(text):
    """Therion's SQL export with bare nan values (it writes them for some
    projected-elevation maps) made NULL, which SQLite can read."""
    return re.sub(r'(?<=[,(])(\s*)-?nan(?=\s*[,)])', r'\1NULL', text)


def connect(path):
    """The export at `path` in an SQLite database in memory."""
    db = sqlite3.connect(':memory:')
    db.executescript(sql_text(open(path, encoding='utf-8', errors='replace').read()))
    return db


def stations(db):
    """(id, name, survey, x, y, z) of every station, splay ends ('-', '.')
    too; `survey` is the name of the survey it is in (not its full path)."""
    surveys = dict(db.execute('select ID, NAME from SURVEY'))
    return [(i, name, surveys.get(sv, ''), x, y, z)
            for i, name, sv, x, y, z in db.execute('select ID, NAME, SURVEY_ID, X, Y, Z from STATION')]
