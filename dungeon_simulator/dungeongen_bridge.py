"""Bridge from our own dungeon layout (layout.py) to dungeongen's renderer.

dungeongen (MIT, https://github.com/benjcooley/dungeongen) is a mature,
purpose-built dungeon-map renderer (Skia-based) - we use it only to draw
the background art (walls, hatching, an unambiguous open/closed door
glyph), never for content or room placement: our own generator.py and
layout.py already do that faithfully from the source rulebook's tables,
including collision-avoidance between rooms. This module only translates
already-computed room/link data into dungeongen's own Room/Passage/Door
model so it can render that background; the interactive overlay (room
numbers, tooltips, the key list, stairs/portals/dead-ends dungeongen has
no concept of) is still drawn by render_map.py on top, in the exact same
coordinate space.

Optional dependency: if dungeongen (or its skia-python dependency) isn't
importable - it needs system graphics libraries that aren't guaranteed to
be present everywhere - `available()` returns False and callers should
fall back to the pure-SVG/RoughJS renderer in render_map.py.

TODO (pending cleanup, not done as part of the grid-native layout change):
layout.py now quantizes every measurement to whole 10ft cells as it walks
the tree, so every coordinate this module receives is already an integer.
That makes several things in here partly or fully redundant:

  - _grid() is now just `int(v)` for any real input - the "round a half
    cell up" logic it documents can no longer trigger, because layout.py
    never hands it a .5 any more.
  - _cell_span/_grid_cell_path's whole reason to exist was reconciling a
    *continuous* lattice coordinate against dungeongen's *cell* coordinate
    (a room wall at x=14 vs. a 5ft hop to x=14.5, etc.) - with integer
    input in, they degenerate to near-identity passthroughs.
  - _pad_single_cell, and the placed-inflation search in
    build_dungeongen_dungeon (trying offsets to grow a small room without
    overlapping a neighbour or a corridor cell) may still be doing real
    work - inflation and neighbour-avoidance are still meaningful even
    with integer input - but that needs checking function by function,
    not assumed.

Don't rip this out reflexively "because it's dead now": some of it
probably still is doing something, and the failure mode here (this
exact bridge, this exact session) has repeatedly been "looks obviously
redundant, turns out to matter for one specific island shape" - see the
git history for the number of rounds that took. When this gets done, it
needs the same treatment as every fix above: a before/after measurement
across a real seed sweep (room/link counts, the hang-safety loop, seed
72 checked visually), not just "tests still pass locally".
"""

from __future__ import annotations

import math
import os
import tempfile

try:
    from dungeongen.layout.models import (
        Dungeon as _DGDungeon,
        Door as _DGDoor,
        DoorType as _DGDoorType,
        Exit as _DGExit,
        ExitType as _DGExitType,
        Stair as _DGStair,
        StairDirection as _DGStairDirection,
        Passage as _DGPassage,
        Room as _DGRoom,
        RoomShape as _DGRoomShape,
    )
    from dungeongen.webview.adapter import convert_dungeon as _convert_dungeon
    _IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - environment dependent
    _IMPORT_ERROR = exc

# Our own grid unit is 10 ft; dungeongen's own cell is fixed at that same
# 10ft - it has no finer resolution available. The rulebook's own tables
# genuinely produce 5ft features (a passage's minimum length, a door's own
# width), exactly half of that cell. Doubling dungeongen's resolution
# (SCALE=2) to represent those exactly was tried and reverted: it halves the
# real-world footprint dungeongen's own +/-3200 map-unit crash limit allows,
# pushing far more dungeons off the nicer background art and onto the
# hand-drawn RoughJS fallback than the fidelity gain was worth. Instead, a
# real 5ft feature is drawn on this map as a full 10ft cell, deliberately and
# consistently - a visible rendering convention (this map's smallest unit is
# 10ft, so a genuine 5ft passage or door still gets its own distinct cell,
# just one that reads as twice its real length) rather than a bug. The log
# and the RoughJS renderer, both working in continuous units, still show the
# real 5ft. See _grid_cell_path for where this is
# actually enforced.
SCALE = 1

_SHAPE_MAP = {
    "rect": "RECT", "square": "SQUARE", "circle": "CIRCLE",
    "triangle": "RECT", "polygon": "OCTAGON", "trapezoid": "RECT", "cave": "RECT",
}

# Visual-only floor for dungeongen's background render - see the comment where
# it's applied in build_dungeongen_dungeon().
_MIN_ROOM_GRID_UNITS = 2

_COMPASS_TO_DG_DIRECTION = {"N": "north", "E": "east", "S": "south", "W": "west"}
_OPPOSITE_COMPASS = {"N": "S", "S": "N", "E": "W", "W": "E"}


def available() -> bool:
    return _IMPORT_ERROR is None


def _grid(v: float) -> int:
    """Snap a lattice coordinate to dungeongen's grid, rounding a half cell
    consistently *up*.

    Not `round()`: that is banker's rounding, which sends .5 to the nearest
    even integer - so a room from 6.5 to 9.5 has its two ends rounded in
    opposite directions (6.5 down to 6, 9.5 up to 10) and comes out 4 cells
    wide when it is 3. The extra cell is taken from whatever sits beside it,
    which is how a 30ft room swallowed 10ft of the corridor leaving its own
    west wall. Rounding both ends the same way keeps a room's drawn width
    equal to its real one."""
    return math.floor(v * SCALE + 0.5)


def _dedupe(points: list[tuple]) -> list[tuple]:
    deduped = [points[0]]
    for point in points[1:]:
        if point != deduped[-1]:
            deduped.append(point)
    return deduped


def _cell_rects_overlap(a, b) -> bool:
    """Whether two half-open cell rects share any cell. Touching along an edge
    is not an overlap - that's two rooms sharing a wall, which is fine."""
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _is_axis_aligned_path(waypoints) -> bool:
    return all(a[0] == b[0] or a[1] == b[1] for a, b in zip(waypoints, waypoints[1:]))


def _cell_span(a: float, b: float) -> tuple[int, int]:
    """The (first, last) cell index a run from `a` to `b` passes through, in
    travel order. A cell is claimed as soon as the run touches it, so a 5ft
    hop - half of dungeongen's 10ft cell - still claims one whole cell rather
    than collapsing to nothing, while a hop that fits inside the cell it
    started in does not invent a second one."""
    lo = math.floor(min(a, b) * SCALE)
    hi = math.ceil(max(a, b) * SCALE) - 1
    if hi < lo:
        hi = lo
    return (lo, hi) if b >= a else (hi, lo)


def _grid_cell_path(points: list[tuple]) -> list[tuple]:
    """Convert a continuous, axis-aligned point list into the cell path
    dungeongen draws.

    Our own coordinates are *lattice* positions - a corridor is a zero-width
    line between two points - while a dungeongen waypoint (gx, gy) names a
    whole cell, [gx, gx+1] x [gy, gy+1]. Converting between them by rounding
    each point independently conflates the two: a room's east wall at x=14
    and a 5ft hop east to x=14.5 both round to 14, look like a collapse, and
    get pushed apart to 14 and 15 - which silently spends *two* cells on a
    single 5ft step and shifts everything downstream of it a cell sideways.

    Walking spans instead states the module's convention directly: whatever a
    run touches, it claims, so the 5ft step east out of a wall at x=14 is
    exactly cell 14 - one 10ft cell, the smallest this map can draw - and a
    following turn north continues up that same column instead of stepping
    aside first. The axis that isn't moving is carried forward from the
    previous cell rather than recomputed, so consecutive waypoints never
    differ on both axes: dungeongen has no concept of a diagonal waypoint and
    has been observed to hang trying to route one."""
    cells: list[tuple] = []
    cx = cy = None
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        dx, dy = bx - ax, by - ay
        if dx and not dy:
            start, end = _cell_span(ax, bx)
            row = math.floor(ay * SCALE)
            if cx is None:
                cx, cy = start, row
                cells.append((cx, cy))
            elif row != cy:
                # The path turned, and the new leg runs along a different row
                # than the cell we're standing in. Stepping straight to the
                # new leg's far end would leave a diagonal jump - two cells
                # touching only at a corner, which is not a corridor you can
                # walk down. The corner cell in between makes it continuous;
                # carrying the old row forward instead (what this used to do)
                # kept it continuous but ended the corridor one cell short of
                # the room it was heading for.
                cy = row
                cells.append((cx, cy))
            cx = end
        elif dy and not dx:
            start, end = _cell_span(ay, by)
            col = math.floor(ax * SCALE)
            if cx is None:
                cx, cy = col, start
                cells.append((cx, cy))
            elif col != cx:
                cx = col
                cells.append((cx, cy))
            cy = end
        else:
            # Diagonal or zero-length in raw space - our own geometry only
            # ever moves one axis at a time, so this shouldn't happen; take
            # the endpoint's own cell rather than guess which axis to fix.
            if cx is None:
                cells.append((math.floor(ax * SCALE), math.floor(ay * SCALE)))
            cx, cy = math.floor(bx * SCALE), math.floor(by * SCALE)
        cells.append((cx, cy))
    if not cells:
        cells = [(math.floor(points[0][0] * SCALE), math.floor(points[0][1] * SCALE))]
    return _dedupe(cells)


def _path_cells(waypoints: list[tuple]) -> set[tuple]:
    """Every cell a waypoint path occupies, not just the corners it turns at.

    Waypoints name the bends; the cells in between are just as much part of
    the corridor, and telling whether a second corridor is already covered
    means comparing the *whole* run, not the endpoints."""
    cells: set[tuple] = set()
    for (ax, ay), (bx, by) in zip(waypoints, waypoints[1:]):
        if ax == bx:
            cells.update((ax, y) for y in range(min(ay, by), max(ay, by) + 1))
        elif ay == by:
            cells.update((x, ay) for x in range(min(ax, bx), max(ax, bx) + 1))
        else:  # never produced by _grid_cell_path, but don't silently drop it
            cells.update(((ax, ay), (bx, by)))
    if waypoints:
        cells.add(waypoints[0])
    return cells


def _claim_takeoff_cell(waypoints, other_cells, takeoff=None):
    """Extend a branch back onto the cell it takes off from, so it shares one
    with its trunk.

    dungeongen's adapter only calls a cell a crossing when two passages
    *occupy the same cell*: it splits both there and connects the pieces. A
    branch that merely runs up against the flank of another corridor shares no
    cell with it, so the adapter sees two unrelated passages, puts them in
    separate connected regions, and draws a wall between them - an arm of a
    four-way came out as a sealed stub beside the crossing rather than part of
    it.

    `takeoff` is the trunk cell the layout recorded for this branch. Deriving
    it here instead was tried twice and is wrong in both directions: take the
    cell *behind* the branch and a side branch joins the arm opposite it
    rather than its trunk, since its trunk is perpendicular; prefer the
    perpendicular cell and a straight continuation joins whatever corridor
    happens to run alongside. Only the walk knows, and now it says.

    Still checked rather than trusted blindly: the cell has to be one some
    other route actually occupies, and to sit orthogonally beside this
    branch's first cell - otherwise there is nothing to join, or joining it
    would knock a hole through a wall."""
    if takeoff is None:
        return waypoints
    first = waypoints[0]
    if takeoff == first or takeoff not in other_cells:
        return waypoints
    if abs(takeoff[0] - first[0]) + abs(takeoff[1] - first[1]) != 1:
        return waypoints
    return [takeoff, *waypoints]


def _sign(v: int) -> int:
    return (v > 0) - (v < 0)


def _pad_single_cell(cells: list[tuple]) -> list[tuple]:
    """Two rooms only 5ft apart are joined by a corridor that genuinely fits
    inside a single 10ft cell, so its cell path is one cell long. That is a
    real connection and dungeongen draws it happily - a passage whose two
    waypoints are the same cell renders as a one-cell corridor, and its
    adapter derives the two door directions from the rooms at either end.
    What it cannot survive is being handed a one-element path, so the cell is
    repeated. Dropping such links instead (the previous behaviour) left the
    rooms looking unconnected on the map."""
    return [cells[0], cells[0]] if len(cells) == 1 else cells


def door_cells(door: dict) -> list[tuple]:
    """The cells a door's own segment occupies, by the same conversion the
    corridor around it uses."""
    return _grid_cell_path([(door["x1"], door["y1"]), (door["x2"], door["y2"])])


def link_end_cells(link: dict) -> tuple:
    """A link's own first and last cell - the two places dungeongen is able to
    put a door glyph, since it only ever draws one where a passage meets a
    room."""
    cells = _grid_cell_path(_dedupe(link["points"]))
    return cells[0], cells[-1]


def _door_type_at(link: dict, end_cell: tuple) -> "_DGDoorType":
    """Whether a real door node occupies this end of the link, rather than
    sitting somewhere further along it. A link is a compressed room-to-room
    path that can pass through a real door partway along, a room pushed far
    from its natural spot, or both - marking *both* ends CLOSED whenever the
    link has a door anywhere drew a closed-door glyph on a room's own wall
    even where that room's entrance is a plain, doorless opening.

    The comparison is by cell, not by raw coordinate: a door 5ft from the
    room's wall is a different *point* but the same 10ft *cell*, and this
    map's whole convention is that a 5ft feature occupies its cell. Matching
    raw points instead left such a door OPEN - and in dungeongen an open door
    is not merely a different glyph: `Map._trace_connected_region` walks
    straight through it, so the room and the corridor collapse into a single
    region and the wall between them is never drawn at all. A corridor
    running alongside the room it leaves then reads as part of that room
    rather than as a separate passage."""
    # Matched by cell, and that works because the route now records crossing
    # the threshold: a door takes no cell of its own, so without that step the
    # link's path stopped on the near side and its end cell could never match
    # the door's own. There is no special case for "the whole link is one
    # threshold" any more - over 40 seeds no link collapses to a single point.
    for door in link["doors"]:
        if end_cell in door_cells(door):
            return _door_kind(door)
    return _DGDoorType.OPEN


def _door_kind(door: dict) -> "_DGDoorType":
    """Every door goes over closed, secret ones included.

    dungeongen does have a SECRET type, and handing it over looks like the
    right thing - but its webview adapter, which is the path we render
    through, folds it straight into an *open* door:

        door_type = DoorType.OPEN if layout_door_type in (OPEN, SECRET) ...

    and an open door is not a glyph, it is a hole: its region tracing walks
    through one, so the two sides merge and the wall between them is never
    drawn. A secret door handed over honestly therefore came out as the one
    thing a secret door must not be - an opening. Closed keeps the wall, and
    the overlay draws the mark that says it is secret (see render_map.py)."""
    return _DGDoorType.CLOSED


def _door_direction(point, x0: int, y0: int, x1: int, y1: int) -> str:
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = point[0] - cx, point[1] - cy
    if abs(dx) > abs(dy):
        return "east" if dx > 0 else "west"
    return "south" if dy > 0 else "north"


def _wall_for_approach(point, bounds) -> str | None:
    """Which wall of `bounds` the passage cell `point` enters through, or None
    if that cell doesn't sit against the room at all.

    `bounds` are lattice edges, so the room *occupies* cells x0..x1-1 by
    y0..y1-1 and the cells touching it are exactly one step outside that
    block. A passage cell qualifies when it is that one step out and lines up
    with the room's own extent on the other axis; the four cases are mutually
    exclusive (a diagonal cell satisfies neither the row nor the column test),
    so there's no ambiguity to resolve and no need to consult the direction of
    travel. Notably a cell alongside the room counts as a proper approach even
    when the corridor then runs parallel to that wall - the door still opens
    straight through it, and forcing a detour there is what used to push a
    corridor a cell away from the room it was leaving."""
    wx, wy = point
    x0, y0, x1, y1 = bounds
    if x0 <= wx <= x1 - 1:
        if wy == y0 - 1:
            return "north"
        if wy == y1:
            return "south"
    if y0 <= wy <= y1 - 1:
        if wx == x0 - 1:
            return "west"
        if wx == x1:
            return "east"
    return None


def _ensure_perpendicular_approach(waypoints, bounds, at_start: bool):
    """A passage has to start on a cell that actually touches the room it
    claims to leave, or dungeongen silently places no door and the room reads
    as unconnected. `_grid_cell_path` normally lands on one already; when the
    conversion leaves the first cell short of the room (a link whose end was
    clipped, or a room the size floor grew after the fact), splice in a stub
    cell against the wall it lines up with so the approach is restored."""
    point = waypoints[0] if at_start else waypoints[-1]
    neighbor = waypoints[1] if at_start else waypoints[-2]
    wall = _wall_for_approach(point, bounds)
    if wall is not None:
        return waypoints  # already sits against the room
    # Not touching the room - only patch it up when `point` lines up with
    # exactly one wall; anything else (diagonally off a corner, or floating
    # away from the room entirely) is left untouched rather than risked.
    wx, wy = point
    x0, y0, x1, y1 = bounds
    on_walls = [w for w, hit in (
        ("west", wx < x0 - 1 and y0 <= wy <= y1 - 1),
        ("east", wx > x1 and y0 <= wy <= y1 - 1),
        ("north", wy < y0 - 1 and x0 <= wx <= x1 - 1),
        ("south", wy > y1 and x0 <= wx <= x1 - 1),
    ) if hit]
    if len(on_walls) != 1:
        return waypoints
    wall = on_walls[0]
    stub = {
        "west": (x0 - 1, wy), "east": (x1, wy),
        "north": (wx, y0 - 1), "south": (wx, y1),
    }[wall]
    # A single stub can only be spliced in without creating a diagonal
    # (non-grid) segment if it shares an axis with `neighbor`. When it
    # doesn't - typically an exit that immediately turns to run *along* its
    # own wall (no travel away from the room first) rather than through it -
    # a second corner point still gets there without ever handing dungeongen
    # a diagonal: one cell straight out from the wall (the stub), then
    # straight across to `neighbor`'s own line. Without this, dungeongen
    # draws the room's wall with its own automatic little alcove to patch
    # the mismatch, and anything positioned at the door's *real* coordinate
    # (our own overlay markers) ends up looking like it's sitting inside the
    # room instead of in the corridor.
    if neighbor[0] != stub[0] and neighbor[1] != stub[1]:
        corner = (stub[0], neighbor[1]) if wall in ("west", "east") else (neighbor[0], stub[1])
        if at_start:
            rest = [p for p in waypoints[1:] if p not in (stub, corner)]
            return _dedupe([waypoints[0], stub, corner, *rest])
        rest = [p for p in waypoints[:-1] if p not in (stub, corner)]
        return _dedupe([*rest, corner, stub, waypoints[-1]])
    if at_start:
        rest = [p for p in waypoints[1:] if p != stub]
        return _dedupe([waypoints[0], stub, *rest]) if rest else [waypoints[0], stub]
    rest = [p for p in waypoints[:-1] if p != stub]
    return _dedupe([*rest, stub, waypoints[-1]]) if rest else [stub, waypoints[-1]]


def build_dungeongen_dungeon(island: dict) -> "_DGDungeon":
    """Translate one already-computed island (see layout.compute_layout) into
    a dungeongen Dungeon: rooms plus the direct room-to-room links between
    them. Dead ends, map edges, stairs and portals have no equivalent in
    dungeongen's room-graph model, so they're simply omitted here - the
    caller's own overlay draws those."""
    if not available():
        raise RuntimeError(f"dungeongen is not available: {_IMPORT_ERROR}")

    dungeon = _DGDungeon()
    room_bounds: dict[int, tuple] = {}  # our room id -> (dg_id, x0, y0, x1, y1)
    # Every room's honest cell rect, in island order, so the size floor below
    # can tell whether growing one would run into a neighbour.
    true_rects = []
    for room in island["rooms"]:
        xs = [c[0] for c in room["corners"]]
        ys = [c[1] for c in room["corners"]]
        x0, y0, x1, y1 = _grid(min(xs)), _grid(min(ys)), _grid(max(xs)), _grid(max(ys))
        true_rects.append((x0, y0, x0 + max(1, x1 - x0), y0 + max(1, y1 - y0)))
    rects = list(true_rects)
    # Cells the map's own corridors run through. A room may not be grown over
    # one: the corridor leaving a room starts at that room's real wall, so
    # growing that way swallows its first cell and draws the room straight
    # over the passage it connects to.
    route_cells: set[tuple] = set()
    for route in [*island["corridors"], *island["links"]]:
        points = _dedupe(route["points"])
        if len(points) >= 2:
            route_cells.update(_grid_cell_path(points))

    for index, room in enumerate(island["rooms"]):
        x0, y0, x1, y1 = rects[index]
        width, height = x1 - x0, y1 - y0
        dg_id = f"r{room['id']}"
        shape_name = _SHAPE_MAP.get(room["shape"], "RECT")
        if width < _MIN_ROOM_GRID_UNITS or height < _MIN_ROOM_GRID_UNITS:
            # Some legitimate rolls (e.g. the Room Table's smallest circular
            # room, 10ft diameter) are exactly as wide as a standard corridor.
            # Drawn at their real size they're an unreadable pinch/bulge in
            # the corridor rather than a recognizable room. This only inflates
            # dungeongen's background art - the room's real recorded
            # dimensions, log text, and layout math are untouched.
            #
            # But only where there is actually space to grow into. Our own
            # layout guarantees rooms don't overlap at their real sizes;
            # inflating one regardless overruns that guarantee and draws it
            # straight through a neighbour - a 10ft room 5ft from a wall grew
            # a full cell into the room next door. Where it doesn't fit, the
            # room is drawn at its true size instead: small, but correct.
            grown_w = max(width, _MIN_ROOM_GRID_UNITS)
            grown_h = max(height, _MIN_ROOM_GRID_UNITS)
            if shape_name == "CIRCLE":
                grown_w = grown_h = max(grown_w, grown_h)
            # Centred on the room is the ideal, but a neighbour on one side
            # doesn't have to cost the room its legibility - it can grow away
            # from that side instead. Every placement that still *contains*
            # the room's true footprint is a candidate (so its walls, and the
            # doors punched in them, stay where the room actually is), tried
            # nearest-to-centred first.
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            ideal_x, ideal_y = cx - grown_w / 2, cy - grown_h / 2
            candidates = [
                (gx0, gy0)
                for gx0 in range(x1 - grown_w, x0 + 1)
                for gy0 in range(y1 - grown_h, y0 + 1)
            ]
            candidates.sort(key=lambda c: (abs(c[0] - ideal_x) + abs(c[1] - ideal_y)))
            others = [other for i, other in enumerate(rects) if i != index]
            # Corridor cells already inside the room's own footprint are its
            # own doorway and don't count against it.
            blocked = {
                cell for cell in route_cells
                if not (x0 <= cell[0] < x1 and y0 <= cell[1] < y1)
            }
            for gx0, gy0 in candidates:
                grown = (gx0, gy0, gx0 + grown_w, gy0 + grown_h)
                if any(_cell_rects_overlap(grown, other) for other in others):
                    continue
                if any(gx0 <= cx_ < gx0 + grown_w and gy0 <= cy_ < gy0 + grown_h
                       for cx_, cy_ in blocked):
                    continue
                rects[index] = grown
                x0, y0 = gx0, gy0
                width, height = grown_w, grown_h
                break
        if shape_name == "CIRCLE" and width != height:
            # dungeongen rejects a circle whose width and height differ (it
            # raises, and the whole level falls back to the plainer renderer).
            # A circular room can reach this either by rounding to a slightly
            # off-square cell count or by the size floor above raising only
            # one of its sides; squaring it off to the larger side keeps the
            # room drawn, and only affects dungeongen's own background art.
            width = height = max(width, height)
            rects[index] = (x0, y0, x0 + width, y0 + height)
        dungeon.add_room(_DGRoom(
            x=x0, y=y0, width=width, height=height,
            shape=getattr(_DGRoomShape, shape_name), z=0, id=dg_id, number=room["id"],
        ))
        room_bounds[room["id"]] = (dg_id, x0, y0, x0 + width, y0 + height)

    covered_exits: set[tuple] = set()
    drawn_cells: set[tuple] = set()  # cells dungeongen has already been told to open
    for link in island["links"]:
        from_info = room_bounds.get(link["from_room"])
        to_info = room_bounds.get(link["to_room"])
        if from_info is None or to_info is None:
            continue
        covered_exits.add((link["from_room"], round(link["points"][0][0], 3), round(link["points"][0][1], 3)))

        points = _dedupe(link["points"])
        if not points:
            continue
        # A link of one cell is normal, not a degenerate case to drop: two
        # rooms sharing a wall with a door in it are 110 of the 151 resolved
        # links across 40 seeds. Dropping them (what a `len(points) < 2` guard
        # once did) left most adjacent rooms drawn with no way between them.
        # dungeongen models it directly - a Door is *the* element for the cell
        # it occupies, and no passage is created when doors cover the whole
        # path - so the single cell is handed over as it is.
        waypoints = _pad_single_cell(_grid_cell_path(points))
        if len(waypoints) < 2:
            continue
        waypoints = _ensure_perpendicular_approach(waypoints, from_info[1:], at_start=True)
        waypoints = _ensure_perpendicular_approach(waypoints, to_info[1:], at_start=False)
        if not _is_axis_aligned_path(waypoints):
            # Never hand dungeongen a diagonal waypoint - its own layout code
            # has no concept of one and has been observed to hang trying to
            # route it, rather than raising a catchable error. Fall back to
            # the pre-fixup, still axis-aligned waypoints instead.
            waypoints = _pad_single_cell(_grid_cell_path(points))
            if len(waypoints) < 2:
                continue

        # the link's own end cells, independent of any approach stub spliced
        # on above - a door belongs where our geometry puts it, not on a cell
        # invented to satisfy dungeongen's routing
        start_cell, end_cell = link_end_cells(link)
        from_id, to_id = from_info[0], to_info[0]
        passage = _DGPassage(start_room=from_id, end_room=to_id, waypoints=waypoints, width=1)
        if not dungeon.add_passage(passage):
            continue  # duplicate room pair or self-loop - skip rather than crash
        drawn_cells |= _path_cells(waypoints)

        start_pt, end_pt = waypoints[0], waypoints[-1]
        dungeon.add_door(_DGDoor(
            x=start_pt[0], y=start_pt[1],
            direction=_door_direction(start_pt, *from_info[1:]),
            door_type=_door_type_at(link, start_cell), room_id=from_id, passage_id=passage.id,
        ))
        dungeon.add_door(_DGDoor(
            x=end_pt[0], y=end_pt[1],
            direction=_door_direction(end_pt, *to_info[1:]),
            door_type=_door_type_at(link, end_cell), room_id=to_id, passage_id=passage.id,
        ))

    # A room's own exit slots that never resolve into a room-to-room link -
    # a branch that stairs, dead-ends, or hits the map edge before reaching
    # another room in this island - have no Door of their own above, since
    # that loop only sees the links our layout math actually resolved. Left
    # alone, dungeongen draws a solid, unbroken wall there even though the
    # room genuinely has an opening (the overlay's own stairs/dead-end icons
    # then float with no wall breach to connect to). An Exit is a one-sided
    # door - it punches the same wall breach without needing a room on the
    # other side.
    for room_exit in island.get("room_exits", []):
        key = (room_exit["room_id"], round(room_exit["x"], 3), round(room_exit["y"], 3))
        if key in covered_exits:
            continue
        from_info = room_bounds.get(room_exit["room_id"])
        if from_info is None:
            continue
        if room_exit.get("secret"):
            # Not for a secret one. dungeongen's Exit is not a neutral wall
            # breach: its own docstring calls it "a skewed inverted U archway
            # extending away from the dungeon" - the way *out*, drawn in
            # perspective, sticking out of the wall. On a hidden way in that
            # is the opposite of the truth, and it breaks the same rule a
            # secret door already follows here: the wall it hides in has to
            # survive. So nothing is handed over, the wall stays solid, and
            # the overlay's "S" is the only thing that marks it - which is
            # what a secret entrance is supposed to look like.
            continue
        dungeon.add_exit(_DGExit(
            x=_grid(room_exit["x"]), y=_grid(room_exit["y"]),
            direction=_COMPASS_TO_DG_DIRECTION.get(room_exit["direction"], "north"),
            exit_type=_DGExitType.EXIT, room_id=from_info[0],
        ))

    # The corridors on those same branches. dungeongen's model only reaches
    # what a link connects, so a corridor running off to stairs, a dead end or
    # the map edge was left for the overlay to ink on top as a bare line -
    # 10ft wide ones came out as a solid black rectangle rather than a
    # corridor with walls. dungeongen draws them properly if it's simply told
    # about them: a passage may end somewhere that isn't a room, and its
    # adapter joins one up to whatever Exit sits beside its end.
    #
    # The far end is a synthetic id that is deliberately not a room, which
    # also keeps `add_passage` from rejecting the second branch off a room
    # that has two - it discards duplicates by room *pair*, so every branch
    # needs a distinct one.
    #
    # Whether a corridor is already drawn is decided on the *cells it covers*,
    # against what was actually handed over above. Testing whether its first
    # point coincides with some link's point (what this used to do) threw away
    # exactly the corridors a junction is made of: at a four-way, the arms
    # leave from a cell the through-route merely passes through, so all but the
    # one whose first point happened to differ were dropped as "already drawn"
    # when nothing drew them - the crossing rendered as a T with an arm
    # missing. Comparing cells also catches the reverse case the old test
    # missed, a corridor lying entirely under a link but starting elsewhere.
    # Which cell a branch takes off from is a fact about the map, not about
    # how far through this loop we happen to be. Testing it against the cells
    # handed over *so far* (which is right for the skip test below) made it
    # depend on the order the corridors are listed in: an arm that came before
    # its own trunk found nothing behind it and stayed sealed off, so whether
    # a crossing was drawn as one was luck. Collected up front instead.
    route_cells: set[tuple] = set()
    for route in [*island["links"], *island["corridors"]]:
        pts = _dedupe(route["points"])
        if len(pts) >= 2:
            route_cells |= _path_cells(_pad_single_cell(_grid_cell_path(pts)))

    stair_corridor_ids = {f"stairs{stair['id']}" for stair in island.get("stairs", [])}
    for index, corridor in enumerate(island["corridors"]):
        points = _dedupe(corridor["points"])
        if len(points) < 2:
            continue
        if corridor["id"] in stair_corridor_ids:
            # Handed over below as a one-cell room instead, so the steps get
            # walls of their own. As a passage it merged with whatever floor it
            # touched and lost them.
            continue
        waypoints = _pad_single_cell(_grid_cell_path(points))
        if len(waypoints) < 2 or not _is_axis_aligned_path(waypoints):
            continue
        cells = _path_cells(waypoints)
        claimed = _claim_takeoff_cell(
            waypoints, route_cells - cells, island.get("_takeoff", {}).get(corridor["id"]))
        # "Already drawn" is about the cells, but a corridor that claims its
        # takeoff cell is carrying something the cells cannot express: the join
        # between itself and its trunk. Two passages can cover the same cell
        # and still be strangers to each other - which is exactly what a
        # crossing must not be - so a corridor that claims is always handed
        # over, and only one that claims nothing can be dropped as redundant.
        if claimed is waypoints and cells <= drawn_cells:
            continue
        waypoints = claimed
        cells = _path_cells(waypoints)
        if dungeon.add_passage(_DGPassage(
            start_room=f"branch{index}a", end_room=f"branch{index}b",
            waypoints=waypoints, width=1,
        )):
            drawn_cells |= cells

    # The steps themselves. dungeongen has a real staircase prop - a 1x1 cell
    # of drawn steps - and its adapter hangs one off whichever passage
    # contains that cell, so the corridor the layout now puts under every
    # stairs node is what makes this possible at all. Without one the adapter
    # silently falls back to `passages[0]` and the steps appear somewhere
    # unrelated, so a stair whose cell nothing covers is skipped and left to
    # the overlay.
    alcove_cells: set[tuple] = set()
    for stair in island.get("stairs", []):
        cell = (stair.get("cell_x"), stair.get("cell_y"))
        if cell[0] is None:
            continue

        # A one-cell room rather than a passage, and this is the whole point.
        # dungeongen draws a wall only along the outline of a region, and two
        # touching floor cells in the same region have no outline between them
        # - so a stairs passage running alongside another corridor (32% of
        # them) simply had no wall on that flank. A room of its own is its own
        # region, so the alcove gets walls all round.
        #
        # Added straight here rather than through the loop above so it skips
        # the small-room inflation: this one is meant to be exactly one cell.
        # Unless the steps are inside a room already: some stairs are walked
        # from a point that was itself in one, so the cell is that room's own
        # floor. An alcove there would be a little box drawn inside a room -
        # and two overlapping rooms, which dungeongen has no business being
        # handed. The staircase still lands, via `_convert_stair`'s own room
        # fallback.
        # Two stairs can be walked onto the same cell; one alcove is one room,
        # and a second identical one is two rooms drawn on top of each other.
        # The stair itself is still handed over either way - it is only the
        # alcove that must not be duplicated.
        if cell in alcove_cells or any(
                x0 <= cell[0] < x1 and y0 <= cell[1] < y1
                for _, x0, y0, x1, y1 in room_bounds.values()):
            room_id = None
        else:
            room_id = f"stair{stair['id']}"
            alcove_cells.add(cell)
            dungeon.add_room(_DGRoom(
                x=cell[0], y=cell[1], width=1, height=1,
                shape=_DGRoomShape.RECT, z=0, id=room_id, number=stair["id"],
            ))
        # And the way in - the same three pieces dungeongen uses for every
        # ordinary room off a corridor, which is what this is: a room, a
        # passage that *ends* in it, and a door on the wall between them,
        # tied to that passage by `passage_id`.
        #
        # All three are needed together, and getting there took several wrong
        # turns worth recording. A chip on its own (an Exit, or a door with no
        # passage terminating at it) does not open anything - it is meant to
        # sit in a wall two floors already reach. And leaving the cell a plain
        # passage keeps it in the same region as whatever it touches, so the
        # flank wall never gets drawn. A Room draws its own outline whatever
        # region it is in, which is what supplies the other three walls.
        #
        # The door is CLOSED: an open one merges the regions and takes the
        # wall with it (same reason a secret door goes over closed).
        take = island.get("_takeoff", {}).get(f"stairs{stair['id']}")
        if room_id is not None and take is not None:
            towards = ("E" if take[0] > cell[0] else
                       "W" if take[0] < cell[0] else
                       "S" if take[1] > cell[1] else "N")
            # The door faces *into* the alcove, away from the corridor it is
            # entered from - the same sense dungeongen's own
            # `_get_door_direction` produces, which measures from the room's
            # centre outwards to the passage and so points back at the room.
            # Handing over the corridor's own side instead leaves the wall
            # closed: measured 0% opening on all four edges either way round
            # until this was right.
            approach = _DGPassage(
                start_room=f"stairway{stair['id']}", end_room=room_id,
                waypoints=[tuple(take), cell], width=1,
            )
            if dungeon.add_passage(approach):
                dungeon.add_door(_DGDoor(
                    x=cell[0], y=cell[1],
                    direction=_COMPASS_TO_DG_DIRECTION[_OPPOSITE_COMPASS[towards]],
                    door_type=_DGDoorType.CLOSED, room_id=room_id,
                    passage_id=approach.id,
                ))
        # Which way the steps face: the prop is oriented by the direction they
        # *ascend*. Going down, that is back the way you came.
        heading = stair.get("heading")
        if stair.get("delta", 0) >= 0:
            heading = {"N": "S", "S": "N", "E": "W", "W": "E"}.get(heading, heading)
        dungeon.add_stair(_DGStair(
            x=cell[0], y=cell[1],
            direction=_COMPASS_TO_DG_DIRECTION.get(heading, "north"),
            stair_dir=(_DGStairDirection.UP if stair.get("delta", 0) < 0
                       else _DGStairDirection.DOWN),
        ))

    return dungeon


# dungeongen has a hard internal sanity limit around +/-3200 map units for any
# shape's bounds - go past it and it doesn't just refuse, it can segfault
# (a native Skia crash, not a catchable Python exception). Our own rulebook
# can produce dungeons much bigger than dungeongen's own generator ever
# would, so anything within reach of that limit is rejected up front rather
# than risking the crash.
_MAX_MAP_UNITS = 2800  # comfortably under the ~3200 limit, padding+inflation included


# How much of its cell the alcove staircase is drawn across. dungeongen's own
# steps run the full width and put the *widest* tread exactly on the cell
# boundary (`y = -CELL_SIZE/2`, plus a small overhang to cover the grid dots).
# For an ordinary passage that is right - the treads should meet its walls -
# but the alcove's boundary on that side is its doorway, so the top step lands
# across the opening and closes it up again. Drawn a little smaller, no tread
# reaches the wall and the doorway stays clear.
_ALCOVE_STAIR_SCALE = 0.66

_ALCOVE_STAIRS_CLASS = None


def _alcove_stairs_class():
    """dungeongen's staircase, drawn inside the cell instead of across it.

    Subclassed rather than nudged: the geometry is all inside `_draw_content`,
    which takes no size of its own, so there is nothing to pass. Everything
    else about the prop - its 1x1 footprint, its rotation, how the map hangs it
    off an element - is inherited untouched."""
    global _ALCOVE_STAIRS_CLASS
    if _ALCOVE_STAIRS_CLASS is None:
        import skia
        from dungeongen.constants import CELL_SIZE
        from dungeongen.map.enums import Layers
        from dungeongen.map.props import StairsProp

        class _AlcoveStairs(StairsProp):
            def _draw_content(self, canvas, bounds, layer=Layers.PROPS) -> None:
                if layer is not Layers.PROPS:
                    return
                paint = skia.Paint(
                    AntiAlias=True, Style=skia.Paint.kStroke_Style,
                    StrokeWidth=self._map.options.border_width * 0.5,
                    Color=skia.Color(0, 0, 0),
                )
                # Same six treads and the same taper as the original; only the
                # extent changes, and the overhang is dropped with it.
                steps, widest, narrowest = 6, _ALCOVE_STAIR_SCALE, 0.15
                run = CELL_SIZE * _ALCOVE_STAIR_SCALE
                spacing = run / (steps - 1)
                for i in range(steps):
                    t = i / (steps - 1)
                    y = -run / 2 + spacing * i
                    half = CELL_SIZE * (widest - t * (widest - narrowest)) / 2
                    canvas.drawLine(-half, y, half, y, paint)

        _ALCOVE_STAIRS_CLASS = _AlcoveStairs
    return _ALCOVE_STAIRS_CLASS


def _quieten_stair_alcoves(dg_map, dg_dungeon) -> None:
    """Fix up the one-cell rooms the stairs are drawn in.

    Two things, both consequences of using a room for the alcove:

    - The adapter decorates every room it converts, and does it before the
      stairs are converted at all, so a column or an altar lands on the steps.
    - `_convert_stair` looks for a passage before it looks for a room and
      falls back to `passages[0]`; now that a stairs cell is not a passage,
      the staircase can end up on an unrelated corridor, or be dropped
      outright on an island that has no passages left.

    An alcove is identified by *position*, against the stair cells this
    dungeon was built from. Identifying it by size instead ("the only room one
    cell across") was wrong: real rooms come out 1x1 too, and they were having
    their decoration stripped and their exits silenced."""
    if not dg_dungeon.stairs:
        return
    from dungeongen.map.room import Room as _MapRoom
    from dungeongen.map.door import Door as _MapDoor
    from dungeongen.graphics.shapes import Rectangle as _Rectangle, ShapeGroup as _ShapeGroup
    from dungeongen.map.props import StairsProp as _StairsProp
    from dungeongen.graphics.rotation import Rotation as _Rotation
    from dungeongen.constants import CELL_SIZE

    # Same mapping `_convert_stair` uses: the steps are oriented by the way
    # they ascend.
    rotations = {"north": _Rotation.ROT_0, "south": _Rotation.ROT_180,
                 "east": _Rotation.ROT_90, "west": _Rotation.ROT_270}
    off_x = -dg_dungeon.bounds[0] if dg_dungeon.rooms else 0
    off_y = -dg_dungeon.bounds[1] if dg_dungeon.rooms else 0
    stair_at = {(stair.x + off_x, stair.y + off_y): stair
                for stair in dg_dungeon.stairs.values()}

    def alcove_cell(element):
        if not isinstance(element, _MapRoom):
            return None
        bounds = element.shape.bounds
        cell = (round(bounds.x / CELL_SIZE), round(bounds.y / CELL_SIZE))
        return cell if cell in stair_at else None

    alcoves = {}
    for element in dg_map._elements:
        cell = alcove_cell(element)
        if cell is not None:
            alcoves[cell] = element
            for prop in [x for x in element.props if not isinstance(x, _StairsProp)]:
                element.remove_prop(prop)

    for cell, alcove in alcoves.items():
        # Whatever the adapter hung this staircase on, take it off there: it
        # looks for a passage before a room and falls back to `passages[0]`,
        # so with a stairs cell no longer being a passage the steps can land
        # on an unrelated corridor - or be dropped, on an island with no
        # passages left at all.
        for element in dg_map._elements:
            for prop in [x for x in getattr(element, "props", [])
                         if isinstance(x, _StairsProp)]:
                pos = prop.position
                if (round(pos[0] / CELL_SIZE), round(pos[1] / CELL_SIZE)) == cell:
                    element.remove_prop(prop)
        # And draw our own, which is the same staircase kept clear of the
        # cell's edges - see _alcove_stairs_class.
        alcove.add_prop(_alcove_stairs_class().at_grid(
            cell[0], cell[1],
            rotations.get(stair_at[cell].direction, _Rotation.ROT_0)))

    # The door that opens the alcove is not drawn. It has to *exist* - closed,
    # tied to the passage that ends there - because that is what keeps the
    # alcove its own region and so its three walls. But no die ever rolled a
    # door here, and dungeongen draws its leaf in the middle of the cell,
    # squarely on top of the staircase: with it on, seed 72's stairs 23 show
    # two steps, with it off, three.
    #
    # Silencing it costs nothing, which is the part worth knowing. The opening
    # is not the glyph - it is the door's floor chip meeting the passage that
    # terminates there, and the region draws that itself
    # (`region.shape.draw`, independent of any element's own draw). Measured
    # on the same cell either way: north, south and west solid, east open at
    # 15%. That is only true in this arrangement; a chip with no passage
    # ending at it opens nothing at all, glyph or no glyph.
    # Which wall each alcove opens through, taken from the door we made for
    # it (it faces *into* the alcove, so the opening is the other way).
    opening = {}
    for door in dg_dungeon.doors.values():
        cell = (door.x + off_x, door.y + off_y)
        if cell in stair_at:
            opening[cell] = {"north": "S", "south": "N",
                             "east": "W", "west": "E"}.get(door.direction)

    for element in dg_map._elements:
        if not isinstance(element, _MapDoor):
            continue
        cell = (round(element._x / CELL_SIZE), round(element._y / CELL_SIZE))
        if cell not in alcoves:
            continue
        element.draw = lambda *args, **kwargs: None
        side = opening.get(cell)
        if side is None:
            continue
        # And a plain rectangular gap in place of dungeongen's own chip.
        #
        # The chip is not decoration - it *is* the opening, the piece of floor
        # that bridges the wall - but its shape is a rounded lobe a third of a
        # cell across, drawn to sit half-hidden inside a normal room. An alcove
        # is one cell, so there is nowhere for it to hide: it bulges into the
        # middle of the floor and reads as a pear stuck to the doorway. Moving
        # the door out to the boundary cell hides the lobe but seals the alcove
        # (measured: the wall comes out unbroken), so the shape has to change
        # rather than the position. A rectangle straddling the wall is the
        # plainest thing that still bridges it, and it leaves the cell square.
        # Asymmetric, and the outward reach is a measurement rather than a
        # taste: one wall thickness, which is the least that opens the way.
        #
        # The alcove and the corridor are separate regions - that is where the
        # alcove's walls come from - so each outlines what it owns, and
        # whatever of this chip lies past the wall is outlined too. It shows as
        # the alcove's north wall running a little into the corridor. Squaring
        # the chip off *at* the line would end that, but it also seals the
        # alcove: the region has to clear its own wall stroke to read as open,
        # and at half a thickness, or none, the doorway measures shut on every
        # side. So the overshoot is one `border_width` - the minimum that
        # works - and no more. Seed 72's stairs 23: its north wall reaches
        # 0.14 of a cell past the corner at 0.22, and 0.07 at this - the same
        # as its own south wall, which has no doorway at all.
        x0, y0 = cell[0] * CELL_SIZE, cell[1] * CELL_SIZE
        inside, outside = CELL_SIZE * 0.2, dg_map.options.border_width
        span = CELL_SIZE * 0.6
        inset = (CELL_SIZE - span) / 2
        if side in ("E", "W"):
            gap = _Rectangle(
                (x0 + CELL_SIZE - inside) if side == "E" else (x0 - outside),
                y0 + inset, inside + outside, span)
        else:
            gap = _Rectangle(
                x0 + inset,
                (y0 + CELL_SIZE - inside) if side == "S" else (y0 - outside),
                span, inside + outside)
        chip = _ShapeGroup(includes=[gap], excludes=[])
        element.get_side_shape = lambda connected, _chip=chip: _chip


def island_extent_map_units(island: dict) -> float:
    """The island's own footprint in dungeongen map units (grid units * CELL_SIZE),
    ignoring padding - i.e. how close a render of it would come to the crash limit.

    Measures everything that gets handed over, not just rooms and links. A
    room-less island is all corridors, so measuring rooms and links alone
    reported an extent of zero for it and waved it straight past the guard -
    and dungeongen's native side does not raise on an oversized shape, it
    segfaults. Seed 72's level 2 has such an island."""
    from dungeongen.constants import CELL_SIZE
    # Deliberately not seeded with the origin. Everything handed to dungeongen
    # is normalized first - by its own adapter for a room-bearing island, by us
    # for a room-less one - so what can trip its limit is how big the island is,
    # not how far along the level it happens to sit. Seeding with 0.0 measured
    # the distance from the origin instead, which grows with every island placed
    # to the left and refused perfectly renderable ones near the end of a level.
    xs: list[float] = []
    ys: list[float] = []
    for room in island["rooms"]:
        for cx, cy in room["corners"]:
            xs.append(cx); ys.append(cy)
    for route in [*island["links"], *island["corridors"]]:
        for px, py in route["points"]:
            xs.append(px); ys.append(py)
    for door in island["doors"]:
        xs += [door["x1"], door["x2"]]
        ys += [door["y1"], door["y2"]]
    for group in ("stairs", "portals", "caps"):
        for item in island[group]:
            xs.append(item["x"]); ys.append(item["y"])
    if not xs:
        return 0.0
    return max(max(xs) - min(xs), max(ys) - min(ys)) * SCALE * CELL_SIZE


def _island_min_cell(island: dict) -> tuple[int, int]:
    """The lowest cell the island occupies, by the same conversion the
    passages use - what has to come off its coordinates to sit at the origin."""
    xs, ys = [], []
    for route in [*island["links"], *island["corridors"]]:
        for px, py in route["points"]:
            xs.append(_grid(px)); ys.append(_grid(py))
    for room in island["rooms"]:
        for cx, cy in room["corners"]:
            xs.append(_grid(cx)); ys.append(_grid(cy))
    return (min(xs) if xs else 0, min(ys) if ys else 0)


def _translated_island(island: dict, dx: int, dy: int) -> dict:
    """A copy of the island moved by (dx, dy) whole grid units.

    Only the geometry `build_dungeongen_dungeon` reads is copied and moved;
    everything else is shared, because the copy exists solely to be handed to
    dungeongen and thrown away. The caller keeps using the original, so the
    overlay's coordinates never move."""
    moved = dict(island)
    moved["rooms"] = [
        {**room, "corners": [(cx + dx, cy + dy) for cx, cy in room["corners"]]}
        for room in island["rooms"]
    ]
    for key in ("links", "corridors"):
        moved[key] = [
            {**route, "points": [(px + dx, py + dy) for px, py in route["points"]]}
            for route in island[key]
        ]
    moved["doors"] = [
        {**door, "x1": door["x1"] + dx, "y1": door["y1"] + dy,
         "x2": door["x2"] + dx, "y2": door["y2"] + dy}
        for door in island["doors"]
    ]
    moved["room_exits"] = [
        {**ex, "x": ex["x"] + dx, "y": ex["y"] + dy} for ex in island.get("room_exits", [])
    ]
    return moved


def fits_size_limit(island: dict) -> bool:
    return island_extent_map_units(island) <= _MAX_MAP_UNITS


def render_island_svg(island: dict) -> tuple[str, float, float, float, int, int]:
    """Render one island's rooms/passages/doors to an SVG string via dungeongen.

    Returns (svg_markup, offset_x, offset_y, px_per_grid_unit, width, height):
    the canvas is sized so dungeongen renders at an exact 1:1 scale (no
    internal "fit" rescaling), so an overlay point at our own (x, y) in grid
    units lands at (offset_x + x * px_per_grid_unit, offset_y + y * px_per_grid_unit)
    in the same pixel space as the returned SVG (width x height).

    dungeongen's own conversion re-normalizes whatever it's given to start at
    its own local origin, so the overlay has to undo exactly that same
    normalization - and it has to undo the one dungeongen actually performed,
    not an equivalent-looking one of our own. Its adapter shifts by the
    *integer* `Dungeon.bounds` of the rooms/passages it was handed; our own
    continuous-coordinate bbox is a different number (a room wall at raw 17.5
    or a link starting at raw 1.0 does not have to agree with the rounded
    cell dungeongen placed it in), and using it put the whole overlay a full
    cell off - room hit-boxes, markers and all - on any island where the two
    disagree. `Map.render` then draws at `map_coord + pad - Map.bounds.x`
    (see calculate_fit_transform, at scale 1 because the canvas is sized to
    the padded bounds below), so that shift is undone here too.
    """
    from dungeongen.constants import CELL_SIZE
    from dungeongen.graphics.conversions import grid_to_map

    if not fits_size_limit(island):
        raise ValueError("island exceeds dungeongen's safe rendering size - caller should fall back")

    dg_dungeon = build_dungeongen_dungeon(island)
    shift_x = shift_y = 0
    if not dg_dungeon.rooms:
        # dungeongen's adapter normalizes what it is given by `-Dungeon.bounds[0]`,
        # and `Dungeon.bounds` is computed from rooms alone - with no rooms it is a
        # placeholder box at the origin, so nothing is normalized and the island is
        # rendered at its raw grid position. Islands are laid out side by side, so a
        # late one sits thousands of map units out and trips dungeongen's internal
        # +/-3200 limit, which on the native side is a segfault rather than an
        # exception. Doing the normalization ourselves puts it back at the origin;
        # the shift is then undone in the returned offset, exactly like the adapter's
        # own.
        shift_x, shift_y = _island_min_cell(island)
        if shift_x or shift_y:
            island = _translated_island(island, -shift_x, -shift_y)
            dg_dungeon = build_dungeongen_dungeon(island)
    dg_map = _convert_dungeon(dg_dungeon, show_numbers=False)
    _quieten_stair_alcoves(dg_map, dg_dungeon)
    bounds = dg_map.bounds
    pad_x, pad_y = grid_to_map(dg_map.options.map_border_cells, dg_map.options.map_border_cells)
    width = max(1, round(bounds.width + 2 * pad_x))
    height = max(1, round(bounds.height + 2 * pad_y))

    fd, path = tempfile.mkstemp(suffix=".svg")
    os.close(fd)
    try:
        dg_map.render_to_svg(path, width=width, height=height)
        with open(path, "r", encoding="utf-8") as fh:
            svg = fh.read()
    finally:
        os.unlink(path)
    px_per_grid_unit = SCALE * CELL_SIZE
    dg_min_x, dg_min_y, _, _ = dg_dungeon.bounds  # the very shift the adapter applied
    # ...plus whatever we normalized away above, which the adapter then saw as
    # already at the origin and left alone. Both are undone the same way.
    off_x = pad_x - bounds.x - (dg_min_x + shift_x) * CELL_SIZE
    off_y = pad_y - bounds.y - (dg_min_y + shift_y) * CELL_SIZE
    return svg, off_x, off_y, px_per_grid_unit, width, height
