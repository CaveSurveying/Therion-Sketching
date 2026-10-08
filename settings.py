# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see tools/LICENSE.
"""How the converter reads a cave's sketches: the [convert] table in
tools/project.toml, over defaults that reproduce the upstream converter
exactly (caves-mendip-swildons; so the upstream regression test still holds).

    from .settings import SETTINGS
    SETTINGS['wall_colours']
"""
from .. import project as _project

UPSTREAM = {
    'wall_colours': ['BLACK', 'BROWN', 'GRAY'],  # strokes that can make the passage outline
    'interior_borders': False,   # True: lines inside the passage stay borders (no floor-step guessing)
    'brown': 'level',            # 'level': another level's walls (upstream); 'floor': boulders, debris, sand, mud
    'boulder_min': 0.6,          # m: a closed brown loop at least this wide is a boulder, smaller is debris
    'wall_jog_max': 0.0,         # m: a wall is joined through a short cross-piece up to this long (0: off)
    'pool_min_area': 0.25,       # m2: a closed blue outline at least this big is a pool
    'pools_first': False,        # True: a closed blue outline is never also a flow arrow
    'climb_whole': False,        # True: climb/pitch labels in whole metres
    'notation': False,           # True: steps, pitches and overhangs from their notation (notation.py)
    'elevation_step_min': 0.0,   # m: an elevation climb with no notation near gets a guessed step if this high
    'pitch_min': 2.0,            # m: a ticked line where the elevation drops this much is a pitch
    'gours': False,              # True: solid green lines are gours (line rimstone-dam)
    'water_to_walls': True,      # False: pools keep their sketched outline (not run along the walls)
    'area_marks': False,         # True: groups of boulders or debris are areas, not single boulders too
    'one_rock_edge': False,      # True: a boulder's edge is one line, corner to corner through a ridge
    'smooth_lines': False,       # True: borders, steps and overhangs simplified and smoothed (splines)
    'end_on_node': False,        # True: lines that end at a wall end on a node of it (nodes.py)
    'boulder_over_wall': 0.4,    # m: how far a boulder at a wall is run out along and over it
    'elevation_data': True,      # False: draw only what the plan sketch shows (no steps, pitches,
                                 # labels or slope arrows inferred from the elevation sketch)
    'mark_max': 0.0,             # m: brown loops and strokes smaller than this are marks (dirt):
                                 # ignored alone, sand or mud when three or more are together
    'area_min_width': 0.0,       # m: parts of areas narrower than this are dropped (sand/mud: 0.6 of it)
    'area_min_area': 0.0,        # m2: smaller areas are dropped (no room for their symbols)
    'green_loops': False,        # True: single green loops are boulders/debris (colour mistaken);
                                 # only nested rings stay a formation
    'area_over_walls': 0.0,      # m: areas run out this far over the walls, which clip them (0: cut at the walls)
    'area_splines': 0.0,         # m: area outlines simplified to this and drawn as splines (0: straight, 0.03 m)
    'corner_cone': 0.0,          # degrees: an outer wall's passage leg may be this far off straight
                                 # across (a corner), when cutting the fill back to it (0: straight only)
    'dash_max': 0.0,             # m: brown open strokes up to this long and roughly straight are mud
                                 # dashes too (0: only those under DASH in marks.py, 0.6 m)
    'curls_closed': False,       # True: a brown stroke curled round on itself is a closed loop (boulder)
    'mud_near': 0.0,             # m: mud/sand marks this close are one patch (0: NEAR in marks.py, 0.6 m)
    'mud_grow': 0.0,             # m: a mud/sand patch is grown this far round its marks, following the
                                 # passage (0: the convex hull of the marks, as upstream)
    'brown_ticks': True,         # False: brown short strokes are never the ticks of a non-brown line
                                 # (they are mud or rocks beside it)
    'wall_tol_rel': 0.0,         # walls refitted to within this fraction of the local leg length
                                 # (mean of the 3 nearest legs, scale.py); 0: a fixed 0.10 m (smooth.TOL)
    'line_tol_rel': 0.0,         # the same for borders, steps and overhangs (0: a fixed 0.04 m, over 0.5 m)
    'section_tol_rel': 0.0,      # cross-section walls to within this fraction of the section's size
                                 # (0: as other walls)
    'sections_in_place': False,  # True: a cross-section scrap's coordinates are where it was sketched,
                                 # by its section mark, so xTherion shows it there
    'wall_ends_meet': 0.0,       # m: wall ends this close meet, and an end near another wall's side ends
                                 # on it, unless the gap crosses a survey leg (nodes.walls_meet; 0: off)
    'wall_ends_meet_rel': 0.0,   # ... or within this share of the local leg length, if larger
    'node_gap': 0.0,             # m: no two nodes of a line closer than this (they cannot be picked apart
                                 # when editing; nodes.thin) ...
    'node_gap_rel': 0.0,         # ... or this share of the local leg length, if larger (both 0: off)
    'presumed_walls': True,      # False: an outline gap Therion might close badly is still left open,
                                 # not drawn as a presumed wall where nothing was sketched
    'area_lines': True,          # False: open brown lines lying mostly inside a boulder/debris area are
                                 # dropped (they are part of the rocks' drawing)
    'hand_scraps': False,        # True: plan scraps from [scraps] in project.toml where a survey has them (scraps.py)
    'join_local': False,         # True: walls joined end to end are refitted only near the join
                                 # (smooth.py), so the rest of each wall stays as drawn
}

SETTINGS = dict(UPSTREAM)


def load(p=None):
    """SETTINGS from tools/project.toml's [convert] table."""
    p = p or _project.load()
    use(p.convert)


def use(values):
    unknown = set(values) - set(UPSTREAM)
    if unknown:
        raise ValueError(f"project.toml [convert]: unknown {', '.join(sorted(unknown))}")
    if values.get('brown', 'level') not in ('level', 'floor'):
        raise ValueError('project.toml [convert]: brown must be "level" or "floor"')
    SETTINGS.clear()
    SETTINGS.update(UPSTREAM)
    SETTINGS.update(values)


load()
