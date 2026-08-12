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
"""

from __future__ import annotations

import os
import tempfile

try:
    from dungeongen.layout.models import (
        Dungeon as _DGDungeon,
        Door as _DGDoor,
        DoorType as _DGDoorType,
        Exit as _DGExit,
        ExitType as _DGExitType,
        Passage as _DGPassage,
        Room as _DGRoom,
        RoomShape as _DGRoomShape,
    )
    from dungeongen.webview.adapter import convert_dungeon as _convert_dungeon
    _IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - environment dependent
    _IMPORT_ERROR = exc

# Our grid unit is 10 ft; dungeongen wants integer grid coordinates, and
# room/door pushback can land things on a half unit (e.g. an odd-width room
# centered on a corridor), so coordinates are rounded to the nearest whole
# unit (SCALE=1) rather than doubled - dungeongen's own +/-3200 map-unit
# safety limit (see _MAX_MAP_UNITS below) is tight enough on our larger,
# more sprawling dungeons that doubling the footprint isn't affordable.
SCALE = 1

_SHAPE_MAP = {
    "rect": "RECT", "square": "SQUARE", "circle": "CIRCLE",
    "triangle": "RECT", "polygon": "OCTAGON", "trapezoid": "RECT", "cave": "RECT",
}

# Visual-only floor for dungeongen's background render - see the comment where
# it's applied in build_dungeongen_dungeon().
_MIN_ROOM_GRID_UNITS = 2

_COMPASS_TO_DG_DIRECTION = {"N": "north", "E": "east", "S": "south", "W": "west"}


def available() -> bool:
    return _IMPORT_ERROR is None


def _grid(v: float) -> int:
    return round(v * SCALE)


def _dedupe(points: list[tuple]) -> list[tuple]:
    deduped = [points[0]]
    for point in points[1:]:
        if point != deduped[-1]:
            deduped.append(point)
    return deduped


def _is_axis_aligned_path(waypoints) -> bool:
    return all(a[0] == b[0] or a[1] == b[1] for a, b in zip(waypoints, waypoints[1:]))


def _door_direction(point, x0: int, y0: int, x1: int, y1: int) -> str:
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = point[0] - cx, point[1] - cy
    if abs(dx) > abs(dy):
        return "east" if dx > 0 else "west"
    return "south" if dy > 0 else "north"


def _wall_for_approach(point, neighbor, bounds) -> str | None:
    """Which wall of `bounds` `point` is approached through, going by the
    *direction of travel* from `neighbor` rather than blind coordinate
    matching - a point can sit exactly on two bbox edges at once (e.g. a
    small room's bounds were widened by the size floor above and now
    coincide, on one axis, with the corridor's own coordinate), and matching
    by coordinate alone can pick the wrong one. Returns None - "don't know,
    leave it alone" - for anything that isn't a clean, unambiguous case,
    rather than guess: a wrong guess here previously produced a self-crossing
    waypoint list that made dungeongen's own layout code hang."""
    wx, wy = point
    nx, ny = neighbor
    x0, y0, x1, y1 = bounds
    if nx == wx and ny != wy:
        if wy == y0:
            return "north"
        if wy == y1:
            return "south"
    elif ny == wy and nx != wx:
        if wx == x0:
            return "west"
        if wx == x1:
            return "east"
    return None


def _ensure_perpendicular_approach(waypoints, bounds, at_start: bool):
    """layout.py's geometry is in continuous grid units (frequently landing on
    half units), but dungeongen wants integer cells - rounding two nearby
    points can collapse them onto the same integer, or onto the room wall's
    own coordinate. Either way the corridor ends up running parallel to the
    wall instead of meeting it head-on, and dungeongen silently fails to
    place a door there (the room then looks unconnected). Detect that and
    splice in a one-cell perpendicular stub so the last hop is always a
    proper, wall-normal approach."""
    point = waypoints[0] if at_start else waypoints[-1]
    neighbor = waypoints[1] if at_start else waypoints[-2]
    wall = _wall_for_approach(point, neighbor, bounds)
    if wall is not None:
        return waypoints  # already a clean, perpendicular approach
    # Not a recognizable perpendicular approach - but only patch it up when
    # `point` unambiguously sits on exactly one wall; anything else (a
    # corner, or floating off every wall entirely) is left untouched rather
    # than risked.
    wx, wy = point
    x0, y0, x1, y1 = bounds
    on_walls = [w for w, hit in (
        ("west", wx == x0), ("east", wx == x1), ("north", wy == y0), ("south", wy == y1),
    ) if hit]
    if len(on_walls) != 1:
        return waypoints
    wall = on_walls[0]
    stub = {
        "west": (wx - 1, wy), "east": (wx + 1, wy),
        "north": (wx, wy - 1), "south": (wx, wy + 1),
    }[wall]
    # A single stub can only be spliced in without creating a diagonal
    # (non-grid) segment if it shares an axis with `neighbor` - which isn't
    # guaranteed here (that's exactly why _wall_for_approach came back
    # empty-handed above). A diagonal waypoint is worse than the bug this is
    # trying to fix: dungeongen's own layout code has no concept of a
    # non-axis-aligned passage and can hang trying to route one. When a
    # clean, non-diagonal splice isn't possible, leave the approach as-is.
    if neighbor[0] != stub[0] and neighbor[1] != stub[1]:
        return waypoints
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
    for room in island["rooms"]:
        xs = [c[0] for c in room["corners"]]
        ys = [c[1] for c in room["corners"]]
        x0, y0, x1, y1 = _grid(min(xs)), _grid(min(ys)), _grid(max(xs)), _grid(max(ys))
        width, height = max(1, x1 - x0), max(1, y1 - y0)
        if width < _MIN_ROOM_GRID_UNITS or height < _MIN_ROOM_GRID_UNITS:
            # Some legitimate rolls (e.g. the Room Table's smallest circular
            # room, 10ft diameter) are exactly as wide as a standard corridor.
            # Drawn at their real size they're an unreadable pinch/bulge in
            # the corridor rather than a recognizable room. This only inflates
            # dungeongen's background art - the room's real recorded
            # dimensions, log text, and layout math are untouched.
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            width, height = max(width, _MIN_ROOM_GRID_UNITS), max(height, _MIN_ROOM_GRID_UNITS)
            x0, y0 = round(cx - width / 2), round(cy - height / 2)
        dg_id = f"r{room['id']}"
        shape_name = _SHAPE_MAP.get(room["shape"], "RECT")
        dungeon.add_room(_DGRoom(
            x=x0, y=y0, width=width, height=height,
            shape=getattr(_DGRoomShape, shape_name), z=0, id=dg_id, number=room["id"],
        ))
        room_bounds[room["id"]] = (dg_id, x0, y0, x0 + width, y0 + height)

    covered_exits: set[tuple] = set()
    for link in island["links"]:
        from_info = room_bounds.get(link["from_room"])
        to_info = room_bounds.get(link["to_room"])
        if from_info is None or to_info is None:
            continue
        covered_exits.add((link["from_room"], round(link["points"][0][0], 3), round(link["points"][0][1], 3)))

        points = _dedupe(link["points"])
        if len(points) < 2:
            continue
        waypoints = _dedupe([(_grid(px), _grid(py)) for px, py in points])
        if len(waypoints) < 2:
            continue
        waypoints = _ensure_perpendicular_approach(waypoints, from_info[1:], at_start=True)
        waypoints = _ensure_perpendicular_approach(waypoints, to_info[1:], at_start=False)
        if not _is_axis_aligned_path(waypoints):
            # Never hand dungeongen a diagonal waypoint - its own layout code
            # has no concept of one and has been observed to hang trying to
            # route it, rather than raising a catchable error. Fall back to
            # the pre-fixup, still axis-aligned waypoints instead.
            waypoints = _dedupe([(_grid(px), _grid(py)) for px, py in points])
            if len(waypoints) < 2:
                continue

        from_id, to_id = from_info[0], to_info[0]
        passage = _DGPassage(start_room=from_id, end_room=to_id, waypoints=waypoints, width=1)
        if not dungeon.add_passage(passage):
            continue  # duplicate room pair or self-loop - skip rather than crash

        door_type = _DGDoorType.CLOSED if link["doors"] else _DGDoorType.OPEN
        start_pt, end_pt = waypoints[0], waypoints[-1]
        dungeon.add_door(_DGDoor(
            x=start_pt[0], y=start_pt[1],
            direction=_door_direction(start_pt, *from_info[1:]),
            door_type=door_type, room_id=from_id, passage_id=passage.id,
        ))
        dungeon.add_door(_DGDoor(
            x=end_pt[0], y=end_pt[1],
            direction=_door_direction(end_pt, *to_info[1:]),
            door_type=door_type, room_id=to_id, passage_id=passage.id,
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
        dungeon.add_exit(_DGExit(
            x=_grid(room_exit["x"]), y=_grid(room_exit["y"]),
            direction=_COMPASS_TO_DG_DIRECTION.get(room_exit["direction"], "north"),
            exit_type=_DGExitType.EXIT, room_id=from_info[0],
        ))

    return dungeon


# dungeongen has a hard internal sanity limit around +/-3200 map units for any
# shape's bounds - go past it and it doesn't just refuse, it can segfault
# (a native Skia crash, not a catchable Python exception). Our own rulebook
# can produce dungeons much bigger than dungeongen's own generator ever
# would, so anything within reach of that limit is rejected up front rather
# than risking the crash.
_MAX_MAP_UNITS = 2800  # comfortably under the ~3200 limit, padding+inflation included


def island_extent_map_units(island: dict) -> float:
    """The island's own footprint in dungeongen map units (grid units * CELL_SIZE),
    ignoring padding - i.e. how close a render of it would come to the crash limit."""
    from dungeongen.constants import CELL_SIZE
    xs, ys = [0.0], [0.0]
    for room in island["rooms"]:
        for cx, cy in room["corners"]:
            xs.append(cx); ys.append(cy)
    for link in island["links"]:
        for px, py in link["points"]:
            xs.append(px); ys.append(py)
    return max(max(xs) - min(xs), max(ys) - min(ys)) * SCALE * CELL_SIZE


def fits_size_limit(island: dict) -> bool:
    return island_extent_map_units(island) <= _MAX_MAP_UNITS


def _island_grid_bbox(island: dict) -> tuple[float, float, float, float]:
    """Our own bounding box (grid units) over an island's rooms and links -
    the same footprint dungeongen is given to draw."""
    xs, ys = [], []
    for room in island["rooms"]:
        for cx, cy in room["corners"]:
            xs.append(cx); ys.append(cy)
    for link in island["links"]:
        for px_, py_ in link["points"]:
            xs.append(px_); ys.append(py_)
    return min(xs), min(ys), max(xs), max(ys)


def render_island_svg(island: dict) -> tuple[str, float, float, float, int, int]:
    """Render one island's rooms/passages/doors to an SVG string via dungeongen.

    Returns (svg_markup, offset_x, offset_y, px_per_grid_unit, width, height):
    the canvas is sized so dungeongen renders at an exact 1:1 scale (no
    internal "fit" rescaling), so an overlay point at our own (x, y) in grid
    units lands at (offset_x + x * px_per_grid_unit, offset_y + y * px_per_grid_unit)
    in the same pixel space as the returned SVG (width x height).

    dungeongen's own conversion re-normalizes whatever it's given to start at
    its own local origin - it ignores the absolute grid position we pass in -
    so the offset is computed from our own bbox, not from `dungeon_map.bounds`
    (which is only trustworthy for width/height, not x/y).
    """
    from dungeongen.constants import CELL_SIZE
    from dungeongen.graphics.conversions import grid_to_map

    if not fits_size_limit(island):
        raise ValueError("island exceeds dungeongen's safe rendering size - caller should fall back")

    isl_minx, isl_miny, _, _ = _island_grid_bbox(island)

    dg_dungeon = build_dungeongen_dungeon(island)
    dg_map = _convert_dungeon(dg_dungeon, show_numbers=False)
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
    off_x = pad_x - isl_minx * px_per_grid_unit
    off_y = pad_y - isl_miny * px_per_grid_unit
    return svg, off_x, off_y, px_per_grid_unit, width, height
