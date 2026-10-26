# Part of tools/sketch2therion (new for the Cheddar Catchment survey).
# GPLv3: see LICENSE.
"""How the converter reads a cave's sketches: the house drawing rules
(rules.toml, shared by every cave), then the cave's own changes to them
([convert] in tools/project.toml), over defaults that reproduce the
upstream converter exactly (caves-mendip-swildons; so the upstream
regression test still holds).

    from .settings import SETTINGS
    SETTINGS['wall_colours']
"""
import os
import tomllib

from . import project as _project

UPSTREAM = {
    'wall_colours': ['BLACK', 'BROWN', 'GRAY'],  # strokes that can make the passage outline
    'auto_scraps': False,        # True: scraps from the 3D model where [scraps]/[scraps_extended] list none (autoscraps.py)
    'section_names': False,      # True: cross sections named survey + PX/EX + station (FairyChimneysPX5); upstream X_xs_n
    'outer_walls': False,        # True: a border or `-outline none` wall with passage (by the splays) on one side only is a wall
    'dashed_presumed': False,    # True: black dashed lines (no ticks) are `line wall -subtype presumed`
    'dash_neighbours': False,    # True: a dash joins only its nearest dash ahead and behind (two dashed lines
                                 # side by side stay two: FairyChimneys 12)
    'short_links': False,        # True: a short stroke in a wall colour joined to the wall at both ends is
                                 # wall (FairyChimneys 9: the floor drawn in short brown and green pieces)
    'section_arrows': False,     # True: section lines `-direction both`, view direction on the left, 0.5 m past the passage (Style.md)
    'layout_split': True,        # True (upstream): a scrap per group of stations that fits Therion's
                                 # layout with one shift, and a sketch that fits only upside down
                                 # flipped. False (plan stage 5d): the layout is for `check` only
    'elevation_features': False,  # True: pools, water flow, curtains, blocks, rocks and rubble read
                                  # from an elevation sketch by shape (elevation.py)
    'wall_subtypes': False,      # True: elevation walls drawn brown are -subtype sand (mud too: no clay),
                                 # or debris where rocks lie along them
    'elevation_wall_colours': [],  # strokes that can make an elevation's outline, if not wall_colours
                                 # (a floor is often drawn brown)
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
    'elevation_suffix': 'E',     # extended-elevation scraps are <prefix><this><n>: GoSouthSE1 (upstream)
    'join_runs': False,          # True: lines running on into one of their kind are joined (nodes.join_runs)
    'pitch_fill': False,         # True: along a steep elevation leg the fill also reaches sideways to
                                 # the walls, as far as the side splays (a shaft's walls far from its legs)
    'gours': False,              # True: solid green lines are gours (line rimstone-dam)
    'water_to_walls': True,      # False: pools keep their sketched outline (not run along the walls)
    'area_marks': False,         # True: groups of boulders or debris are areas, not single boulders too
    'one_rock_edge': False,      # True: a boulder's edge is one line, corner to corner through a ridge
    'smooth_lines': False,       # True: borders, steps and overhangs simplified and smoothed (splines)
    'end_on_node': False,        # True: lines that end at a wall end on a node of it (nodes.py)
    'boulder_over_wall': 0.4,    # m: how far a boulder at a wall is run out along and over it
    'elevation_data': True,      # False: draw only what the plan sketch shows (no steps, pitches,
                                 # labels or slope arrows inferred from the elevation sketch)
    'drawn_rocks': False,        # True: every boulder-sized loop is drawn as a rock of its own (details.boulders:
                                 # clean corners, rock edges), smaller loops among them debris; not area blocks
    'mark_max': 0.0,             # m: brown loops and strokes smaller than this are marks (dirt):
                                 # ignored alone, sand or mud when three or more are together
    'area_min_width': 0.0,       # m: parts of areas narrower than this are dropped (sand/mud: 0.6 of it)
    'area_min_area': 0.0,
    'area_inside_min': 0.0,      # share of an area (as drawn, run over the walls) that must be inside the
                                 # passage, or it is not drawn (0: no check)        # m2: smaller areas are dropped (no room for their symbols)
    'flowstone_areas': False,    # True: groups of ^ marks (green) are area flowstone; a ^ is never a gour
    'plan_green_walls': False,   # True: in plans a green stroke on or beside a wall makes it -subtype flowstone
    'green_loops': False,        # True: single green loops are boulders/debris (colour mistaken);
                                 # only nested rings stay a formation
    'area_over_walls': 0.0,      # m: areas run out this far over the walls, which clip them (0: cut at the walls)
    'area_splines': 0.0,         # m: area outlines simplified to this and drawn as splines (0: straight, 0.03 m)
    'corner_cone': 0.0,          # degrees: an outer wall's passage leg may be this far off straight
                                 # across (a corner), when cutting the fill back to it (0: straight only)
    'dash_max': 0.0,             # m: brown open strokes up to this long and roughly straight are mud
                                 # dashes too (0: only those under DASH in marks.py, 0.6 m)
    'pockets': False,            # True: a wall piece off the outline, outside the passage, with both ends
                                 # on one outline wall is a pocket (a deliberate bulge): the wall goes round it
    'rock_faces': False,         # True: the fill is cut along the wall strokes and faces of it with no
                                 # leg or station that reach its edge (rock it took in) dropped
    'merge_short': 0,            # nodes: a piece of up to this many running on from a border's end is
                                 # border (joined by join_runs); 0: off
    'ends_meet': False,          # True: lines of different kinds (border, floor step, pit, ...) that end
                                 # close together share that end (within the wall-join reach)
    'despike': 0.0,              # m: a wall node turning right back (over 110 degrees) beside a segment
                                 # shorter than this is an overshoot and goes (0: off)
    'smooth_nodes': 0.0,         # degrees: at a node turning less than this, the control points either
                                 # side are put in line with it (a smooth node; 0: off)
    'wall_links': 0.0,           # m: a wall piece off the outline at least this long whose ends meet two
                                 # outline walls' ends is wall (the stroke between them, round a bend),
                                 # if the outline stays sound (0: off)
    'wall_hooks': False,         # True: a small black loop left open, an end at another black stroke, is
                                 # a hook of the wall, not a boulder
    'curls_closed': False,       # True: a brown stroke curled round on itself is a closed loop (boulder)
    'rock_curves': False,        # True: curved brown strokes (up to dash_max long) are rock outlines
    'area_grow': 0.0,            # m: rock areas grown this far round their marks within the passage, up to
                                 # walls, steps and other barriers (0: the hull of the marks, as upstream)
    'barrier_min': 0.0,          # m: lines inside the passage shorter than this do not stop an area, and
                                 # go if mostly inside a rock area (0: every line is a barrier)
    'mud_near': 0.0,             # m: mud/sand marks this close are one patch (0: NEAR in marks.py, 0.6 m)
    'mud_grow': 0.0,             # m: a mud/sand patch is grown this far round its marks, following the
                                 # passage (0: the convex hull of the marks, as upstream)
    'notation_rel': 0.0,         # m: ticks and dashes may be drawn bigger in proportion to the legs'
                                 # length over this (up to twice); an overhang may be two ticked dashes (0: off)
    'tick_reach': 0.0,           # m: a tick's near end may stand this far from its line (0: TOUCH in
                                 # notation.py, 0.15 m); ticks drawn a little clear of the line
    'chain_gap': 0.0,            # m: brown line strokes ending this close to the next, and carrying on,
                                 # are one line (sketched in pieces; 0: off)
    'mud_ticks': 0.0,            # m: a brown line's brown "ticks" are mud, not a step, where they are
                                 # sparse (under 0.8 a metre) or four times as many other brown dashes up to
                                 # this long lie within 1 m of it (0: off)
    'brown_ticks': True,         # False: brown short strokes are never the ticks of a non-brown line
                                 # (they are mud or rocks beside it)
    'wall_tol_rel': 0.0,         # walls refitted to within this fraction of the local leg length
                                 # (mean of the 3 nearest legs, scale.py); 0: a fixed 0.10 m (smooth.TOL)
    'wall_presmooth': 0.0,       # walls smoothed (running mean over this many times the tolerance)
                                 # before refitting, so nodes follow bends, not hand wobble (0: off)
    'line_tol_rel': 0.0,         # the same for borders, steps and overhangs (0: a fixed 0.04 m, over 0.5 m)
    'section_tol_rel': 0.0,      # cross section walls to within this fraction of the section's size
                                 # (0: as other walls)
    'sections_in_place': False,  # True: a cross section scrap's coordinates are where it was sketched,
                                 # by its section mark, so xTherion shows it there
    'section_shape': False,      # True: a cross section keeps the shape it was sketched: one open stroke is
                                 # closed by a floor straight across its ends, the closing distances scale
                                 # with its size, and its walls are not despiked as passage walls are
    'section_chain': False,      # True: a cross section's strokes end to end, any number, green and blue too,
                                 # each a wall with its colour's subtype; blue the water surface (walls 0.3 m
                                 # down and closed below, area water, level); a station point; splays may end outside
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
    'colour_map': {},            # sketch colours read as another (purple: walls of a passage where it
                                 # overlaps another, read as black; red, orange: its other lines, read
                                 # by shape as grey); upstream: none, red and orange ignored as notes
    'join_local': False,         # True: walls joined end to end are refitted only near the join
                                 # (smooth.py), so the rest of each wall stays as drawn
}

SETTINGS = dict(UPSTREAM)


RULES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rules.toml')


def house_rules(path=RULES):
    """The [convert] table of the house drawing rules."""
    with open(path, 'rb') as f:
        return tomllib.load(f)['convert']


def load(p=None):
    """SETTINGS from the house rules, changed by tools/project.toml's [convert] table."""
    p = p or _project.load()
    use(dict(house_rules(), **p.convert))


def use(values):
    unknown = set(values) - set(UPSTREAM)
    if unknown:
        raise ValueError(f"[convert] (rules.toml or project.toml): unknown {', '.join(sorted(unknown))}")
    if values.get('brown', 'level') not in ('level', 'floor'):
        raise ValueError('[convert] (rules.toml or project.toml): brown must be "level" or "floor"')
    SETTINGS.clear()
    SETTINGS.update(UPSTREAM)
    SETTINGS.update(values)


load()


def inner_wall_head():
    """What a wall inside the passage (not on the outline) becomes: the edge
    of something, a `line border`, in plans and elevations alike. Never a
    wall with `-outline none` (Style.md: every outer line is a wall, an
    inner line is drawn as what it is)."""
    return 'line border'

