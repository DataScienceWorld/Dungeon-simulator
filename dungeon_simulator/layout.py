"""Turn the generated dungeon tree into a 2D layout (rooms, corridors, doors, stairs).

This walks the same tree the CLI/log renderer walks, but interprets each
node's `geo` data (lengths, turns, room footprints - see generator.py) as
turtle-graphics instructions: start at the origin facing north, and move/
turn/branch as each passage segment or room exit dictates.

Grid units are 10 ft (matching the tables' own "x10 ft" convention) and
every measurement is quantized to whole units as it is walked - see
_cells(). The map is therefore built *on* the grid, in the order the walk
visits things: a room simply begins after the passage that leads to it, so
nothing ever has to be nudged into agreement afterwards. A 5ft feature
becomes one full 10ft cell rather than half of one; the log still reports
the feet the tables actually rolled.

The tree has no idea about physical space, so two unrelated branches can
easily land on the same spot. Whenever a room is about to be placed, this
walk checks it against every room already placed in the same island and
tries each position along its own entry wall. A room that fits nowhere is
left off the map entirely, with a note saying so, rather than being shoved
somewhere the roll never put it; the same goes for an exit when its wall
has no cell left for another 10ft opening.

A level can also have more than one disconnected "island" (e.g. two
different staircases both landing on level 2, or a magical portal jump) -
these are laid out side by side rather than overlapping.

Alongside the drawable shapes, each island also collects `links`: every
direct room-to-room connection (the doors/corridor in between), used to
feed the dungeongen rendering bridge (see dungeongen_bridge.py). A link is
only recorded when a chain of doors/passages actually starts and ends at a
room - dead ends, map edges, stairs and portals never resolve into one.
"""

from __future__ import annotations

FT_PER_UNIT = 10.0
DEFAULT_PASSAGE_WIDTH_FT = 5.0  # a passage's width before any "widens"/"narrows" roll - one full 5ft square
ROOM_MARGIN = 0.0  # rooms may share a wall, they just may not overlap. A gap is not
# something to enforce here: the passage between two connected rooms already occupies at
# least one whole cell of its own, so it is the passage that separates them. Demanding a
# further clear cell only rejected real placements - a room reached through a door that sits
# against a neighbour's wall has nowhere else to be, and was simply dropped instead. Across
# 60 seeds x 2 depths, dropping the requirement places 599 rooms of 713 rather than 560, with
# the unplaceable ones down from 21.5% to 16.0% and still no two rooms overlapping.
# Any margin at all costs the same: coordinates are whole cells, so anything in (0, 1] rejects
# exactly the placements that share a wall, and 0.5 and 1.0 measure identically.
# (Re-measure with __pycache__ cleared - flipping this constant does not change the file's
# size, so a same-second edit can leave a stale .pyc in place and every value read as 0.0.)
_CAP_STUB_LENGTH = 1.0  # length of the little corridor stub drawn before a dead-end/edge cap
_NOTABLE_SLIDE_UNITS = 2.0  # 20ft - an offset at least this large gets called out in the log

_HEADINGS = ["N", "E", "S", "W"]
_VECTORS = {"N": (0.0, -1.0), "E": (1.0, 0.0), "S": (0.0, 1.0), "W": (-1.0, 0.0)}


def _rotate(heading: str, direction: str | None) -> str:
    if direction is None:
        return heading
    idx = _HEADINGS.index(heading)
    if direction == "left":
        return _HEADINGS[(idx - 1) % 4]
    if direction == "right":
        return _HEADINGS[(idx + 1) % 4]
    return heading


def _cells(feet: float) -> int:
    """A measurement the tables rolled, in feet, as whole 10ft cells.

    This map's smallest unit is one 10ft cell, so a 5ft feature - and the
    rulebook rolls plenty of them: a passage's minimum length, a door's own
    width - becomes one full cell rather than half of one. Nothing the tables
    produced can round away to nothing.

    Quantizing here, as the layout is walked, is what keeps the map coherent:
    every room, passage and door is placed on the grid *by construction*, in
    the order the walk visits them, so a room simply starts after the passage
    that leads to it. Computing continuous coordinates and rounding them
    afterwards instead left rooms and corridors disagreeing about which cell
    they own, which no amount of nudging afterwards can reconcile - a room's
    own corridor could round into its wall, or two neighbours into each other.
    The log still reports the real feet the tables rolled."""
    return max(1, round(feet / FT_PER_UNIT))


def _pseudo_unit(n: int) -> float:
    """Deterministic pseudo-random value in [0, 1) derived from an integer id.
    Where an exit sits along the wall it's on is cosmetic layout jitter, not
    a rulebook roll, so it doesn't need to come from the shared dice stream -
    but it must still be stable across re-renders of the same dungeon, hence
    a hash of the (stable, unique) node id rather than a fresh random draw."""
    return ((n * 2654435761) & 0xFFFFFFFF) / 0xFFFFFFFF


def _banded_wall_offset(index: int, count: int, wall_cells: int, node_id: int):
    """Which cell of the wall the `index`-th of `count` exits sits in, counted
    from the wall's low end - or None if the wall has no cell left for it.

    Counted from the low end rather than as a signed offset from the middle:
    the sign of a room's perpendicular axis flips with the heading it was
    entered from, so a signed offset lands correctly for rooms facing one way
    and a cell off for rooms facing the other.

    An exit is a 10ft opening, so it occupies one whole cell and two exits
    cannot share one. Each gets its own band of the wall and, within it, a
    deterministic cell (jitter keyed on the node id, so it's stable across
    re-renders but two exits on a long wall don't line up). Bands are carved
    by integer division, so the cells they pick are always distinct.

    A wall with fewer cells than exits simply cannot hold them all: the ones
    that don't fit get None, and the caller drops those branches rather than
    stacking two openings on one cell."""
    if index >= wall_cells:
        return None
    low = index * wall_cells // count
    high = ((index + 1) * wall_cells // count) - 1
    if high < low:
        high = low
    cell = low + int(_pseudo_unit(node_id) * (high - low + 1))
    return min(cell, high)


_NOT_DRAWN = (
    "[Layout] Questa voce non e' disegnata sulla mappa: si trova oltre un punto in cui il "
    "tracciato si e' interrotto. Il tiro e il contenuto restano comunque nel registro."
)


def _mark_branch_not_drawn(node) -> None:
    """Say, on every entry beyond a branch that was cut, that it isn't drawn.

    When a room can't be placed - or a wall has no cell left for another
    opening - the walk stops there, so nothing past that point is ever
    reached, and nothing past that point would otherwise say a word about it.
    The note on the node that failed explains *itself*, but a reader looking
    up one particular room's entry would have to trace back up the tree to
    discover it is not on the map at all. Everything the dice produced stays
    in the log either way; what this adds is that each entry states its own
    status rather than relying on a note somewhere above it."""
    for child in node.children:
        for descendant in child.walk():
            if descendant.kind in ("room", "passage", "door", "stairs"):
                descendant.lines.append(_NOT_DRAWN)


def _segment_cells(a, b):
    """The cells an axis-aligned segment between two lattice points occupies.

    Same convention as everything else here: a run from lattice 4 to 7 claims
    cells 4, 5 and 6 - the cell is the square *after* the line."""
    (ax, ay), (bx, by) = a, b
    if ay == by and ax != bx:
        return {(gx, int(ay)) for gx in range(int(min(ax, bx)), int(max(ax, bx)))}
    if ax == bx and ay != by:
        return {(int(ax), gy) for gy in range(int(min(ay, by)), int(max(ay, by)))}
    return set()


def _clip_at_placed_room(x, y, nx, ny, occupied):
    """Stop a move at the wall of the first already-placed room it runs into.

    Returns (cx, cy, room_id, wall) - or (nx, ny, None, None) when the move
    reaches nothing. `wall` is the compass side of the room that was struck.

    Worked in cells, because that is what gets drawn: a run east from lattice
    x to nx claims columns x..nx-1, and a room with corners [rx0, rx1] owns
    columns rx0..rx1-1. The corridor is therefore stopped at the lattice line
    of the first room column it would otherwise claim, which is exactly the
    room's wall - it arrives against it rather than eating into the floor.

    Only rooms already on the map count. Draw order is the whole point: a room
    that comes later has to find space around what is already there (it is not
    placed if it can't), while a passage arriving afterwards is the one that
    has to stop."""
    if (nx, ny) == (x, y):
        return nx, ny, None, None
    best = None
    for rx0, ry0, rx1, ry1, room_id in occupied:
        if ny == y:
            if not (ry0 <= y < ry1):  # different row: cannot meet
                continue
            if nx > x:
                hit = max(x, rx0)                      # first room column claimed
                if hit > min(nx - 1, rx1 - 1):
                    continue
                edge, wall = hit, "W"
            else:
                hit = min(x - 1, rx1 - 1)              # travelling the other way
                if hit < max(nx, rx0):
                    continue
                edge, wall = hit + 1, "E"
            candidate = (edge, y, room_id, wall)
            key = abs(edge - x)
        elif nx == x:
            if not (rx0 <= x < rx1):
                continue
            if ny > y:
                hit = max(y, ry0)
                if hit > min(ny - 1, ry1 - 1):
                    continue
                edge, wall = hit, "N"
            else:
                hit = min(y - 1, ry1 - 1)
                if hit < max(ny, ry0):
                    continue
                edge, wall = hit + 1, "S"
            candidate = (x, edge, room_id, wall)
            key = abs(edge - y)
        else:
            continue
        if best is None or key < best[0]:
            best = (key, candidate)
    if best is None:
        return nx, ny, None, None
    return best[1]


def _new_island() -> dict:
    return {
        "rooms": [], "corridors": [], "doors": [], "stairs": [], "portals": [], "caps": [],
        "links": [], "room_exits": [], "origin": (0.0, 0.0), "is_entrance": False, "_occupied": [],
        "_route_cells": set(),
        # child node id -> the cell of the corridor it branches off from. The
        # renderer needs to know which cell a branch takes off from to draw a
        # crossing rather than two corridors that merely touch, and guessing it
        # from the branch's own shape gets it wrong both ways round: the cell
        # behind it may belong to a corridor passing by, and the cell beside it
        # may be its own trunk. The walk knows for certain, so it says.
        "_takeoff": {},
    }


def _room_aabb(entry_x, entry_y, dx, dy, px, py, w, depth, lateral=0.0):
    """The room's footprint when the doorway sits `lateral` units off the
    middle of the wall it's punched into. The doorway itself stays at
    (entry_x, entry_y); the room slides sideways around it, which is what
    lets a blocked room find clear ground beside an obstacle without the
    corridor leading to it having to stretch."""
    mid_x, mid_y = entry_x + px * lateral, entry_y + py * lateral
    far_x, far_y = mid_x + dx * depth, mid_y + dy * depth
    corners = [
        (mid_x - px * w / 2, mid_y - py * w / 2),
        (mid_x + px * w / 2, mid_y + py * w / 2),
        (far_x + px * w / 2, far_y + py * w / 2),
        (far_x - px * w / 2, far_y - py * w / 2),
    ]
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    return min(xs), min(ys), max(xs), max(ys)


def _overlaps(a, b, margin: float) -> bool:
    return not (a[2] + margin <= b[0] or b[2] + margin <= a[0]
                or a[3] + margin <= b[1] or b[3] + margin <= a[1])


def _segment_crosses_room(p0, p1, bbox, pad: float = 0.05) -> bool:
    """True if the axis-aligned segment p0->p1 passes through the *interior*
    of bbox (touching its edge doesn't count - that's how every corridor
    meets the room it's actually going to)."""
    x0, y0 = p0
    x1, y1 = p1
    bx0, by0, bx1, by1 = bbox[:4]
    if abs(x0 - x1) < 1e-9:
        if not (bx0 + pad < x0 < bx1 - pad):
            return False
        lo, hi = min(y0, y1), max(y0, y1)
        return lo < by1 - pad and hi > by0 + pad
    if abs(y0 - y1) < 1e-9:
        if not (by0 + pad < y0 < by1 - pad):
            return False
        lo, hi = min(x0, x1), max(x0, x1)
        return lo < bx1 - pad and hi > bx0 + pad
    return False


_DETOUR_MARGIN = 1.0
_DETOUR_MIN_LEG = 0.6  # keep at least this much of the *original* approach axis
# right before prev and right after entry - dungeongen (and a human reading
# the map) expects a corridor to meet a room head-on, perpendicular to its
# wall. A jog that runs all the way up to the wall's own coordinate arrives
# parallel to it instead.
#
# A larger value here (>1.0) survives dungeongen's integer-cell rounding
# more reliably and fixes a few more "room reads as unconnected" cases, but
# it also measurably increases how often the jog itself cuts through some
# *other* room on a crowded island (0.6 -> ~15 such crossings across a
# 150-seed sweep; 1.1+ -> ~74) - a much more common and more visible defect
# than the rounding corner case it would fix. dungeongen_bridge.py's own
# _ensure_perpendicular_approach() is the second line of defense for the
# rounding case specifically (and the hang-safety net is independent of
# this value either way - see _is_axis_aligned_path), so this stays small.


def _detour_around(prev, entry, blockers, margin: float = _DETOUR_MARGIN):
    """A room can end up pushed clear of every *other room* yet still have
    its straight connecting corridor cut through some third room that
    happened to sit between the door and its new position (the push-back in
    _walk_room only checks the room's own footprint, not the path leading to
    it). Route around the union of whatever it crosses instead: a sideways
    jog wide enough to clear them, added to the trunk `path.points` so it
    renders as a corridor bend rather than a line straight through someone
    else's walls. `prev` and `entry` keep their original approach axis (only
    the middle of the path moves sideways) so both ends still meet their
    room's wall perpendicular, the way a door needs to."""
    x0, y0 = prev
    x1, y1 = entry
    if abs(x0 - x1) < 1e-9 and abs(y0 - y1) > 1e-9:
        bx0 = min(b[0] for b in blockers)
        bx1 = max(b[2] for b in blockers)
        left, right = bx0 - margin, bx1 + margin
        jog_x = left if abs(x0 - left) <= abs(x0 - right) else right
        by0 = min(b[1] for b in blockers)
        by1 = max(b[3] for b in blockers)
        if y0 < y1:
            near, far = by0 - margin, by1 + margin
            near = min(near, y0 + _DETOUR_MIN_LEG)
            far = min(max(far, near + _DETOUR_MIN_LEG), y1 - _DETOUR_MIN_LEG)
        else:
            near, far = by1 + margin, by0 - margin
            near = max(near, y0 - _DETOUR_MIN_LEG)
            far = max(min(far, near - _DETOUR_MIN_LEG), y1 + _DETOUR_MIN_LEG)
        return [(x0, near), (jog_x, near), (jog_x, far), (x1, far)]
    if abs(y0 - y1) < 1e-9 and abs(x0 - x1) > 1e-9:
        by0 = min(b[1] for b in blockers)
        by1 = max(b[3] for b in blockers)
        top, bottom = by0 - margin, by1 + margin
        jog_y = top if abs(y0 - top) <= abs(y0 - bottom) else bottom
        bx0 = min(b[0] for b in blockers)
        bx1 = max(b[2] for b in blockers)
        if x0 < x1:
            near, far = bx0 - margin, bx1 + margin
            near = min(near, x0 + _DETOUR_MIN_LEG)
            far = min(max(far, near + _DETOUR_MIN_LEG), x1 - _DETOUR_MIN_LEG)
        else:
            near, far = bx1 + margin, bx0 - margin
            near = max(near, x0 - _DETOUR_MIN_LEG)
            far = max(min(far, near - _DETOUR_MIN_LEG), x1 + _DETOUR_MIN_LEG)
        return [(near, y0), (near, jog_y), (far, jog_y), (far, y1)]
    return []


class _Path:
    """Accumulates waypoints/doors between the last room and whatever comes next.

    Discarded (never turned into a link) if the chain doesn't end at a room."""

    def __init__(self, room_from, start_point):
        self.room_from = room_from
        self.points = [start_point]
        self.doors = []

    def branch(self, start_point, corner=None):
        """A side branch leaving this route at `start_point`.

        It keeps the whole way walked so far, not just the room it started
        from. Dropping the points and keeping only `room_from` - what this
        used to do - declared a link between two rooms whose recorded path
        began nowhere near the first of them: over 40 seeds, 21% of links had
        their starting end off its own room's wall. dungeongen believes the
        declaration, so it punched a door into that room at a point out on
        some distant corridor and spliced a stub to reach it - room 6 of seed
        72 got a corridor that ran west and doubled straight back onto itself.

        `corner` is the intermediate point where the branch's takeoff needed a
        correction on both axes at once; without it the route would jump
        diagonally off the trunk, which is not a corridor anyone can walk."""
        forked = _Path(self.room_from, self.points[0])
        points = list(self.points)
        for point in (corner, start_point):
            if point is not None and point != points[-1]:
                points.append(point)
        forked.points = points
        forked.doors = list(self.doors)
        return forked


class _Layout:
    def __init__(self):
        self.levels: dict[int, list[dict]] = {}

    def _add_island(self, level: int) -> dict:
        island = _new_island()
        self.levels.setdefault(level, []).append(island)
        return island

    def walk_root(self, node) -> None:
        island = self._add_island(node.level)
        island["is_entrance"] = True
        self._walk(node, 0.0, 0.0, "N", node.level, island, _Path(None, (0.0, 0.0)))

    def _enter(self, child, x: float, y: float, heading: str, level: int, island: dict,
               force_new_island: bool, path: "_Path"):
        """Walk into `child`, starting it at (x, y) facing `heading`. Crossing
        into a new island (a different level, or an explicit portal jump) starts
        that island at its own origin instead.

        The (x, y) that comes back is where the walk *ended up*, which is only
        meaningful for a passage (the far end of everything it walked) - no
        caller uses it, and none should start: it used to be read as "where the
        child actually put its entry point", back when a room that didn't fit
        was pushed along the heading until it did. Rooms are never pushed now,
        so nothing downstream needs reconciling, and reading a passage's far end
        as an entry point is what drew diagonals across the map."""
        if force_new_island or child.level != level:
            new_island = self._add_island(child.level)
            self._walk(child, 0.0, 0.0, "N", child.level, new_island, _Path(None, (0.0, 0.0)))
            return x, y
        return self._walk(child, x, y, heading, level, island, path)

    def _walk(self, node, x: float, y: float, heading: str, level: int, island: dict, path: "_Path"):
        kind = node.kind
        if kind == "start":
            for child in node.children:
                self._enter(child, x, y, heading, level, island, False, path)
            return x, y
        if kind == "room":
            return self._walk_room(node, x, y, heading, level, island, path)
        if kind == "passage":
            return self._walk_passage(node, x, y, heading, level, island, path)
        if kind == "door":
            # A door goes *on the wall*: it is the threshold you cross, not a
            # stretch of corridor, so it claims no cell of its own and the
            # walk does not advance through it.
            #
            # It used to. Every door the tables roll is 5ft (419 of 419 across
            # 40 seeds), and the rule that a 5ft feature becomes a full 10ft
            # cell was being applied to them too - so a door in a wall, a
            # passage with no length of its own, and a second door came out as
            # three separate 10ft cells in a row. That is the "strettoia"
            # reported west of seed 72's room 6, and it is 30ft of map for
            # what the dice called 5 + 0 + 5.
            #
            # The recorded segment is unchanged - still one grid unit along
            # the heading - because that is what tells the marker which wall
            # line it sits on, and what every reader of a door (the overlay's
            # marker geometry, the bridge's door_cells and _door_type_at)
            # already expects. What changed is only that the door shares that
            # cell with whatever is beyond it, rather than taking it first.
            dx, dy = _VECTORS[heading]
            door = {"id": node.id, "x1": x, "y1": y, "x2": x + dx, "y2": y + dy,
                    "secret": bool(node.geo.get("secret")), "lines": node.lines}
            island["doors"].append(door)
            path.doors.append(door)
            for child in node.children:
                # No gap can open up here to be bridged. This used to append a
                # connecting corridor when the child came back at a different
                # spot, because a room that didn't fit was pushed along until
                # it did. Rooms are never pushed now - one that doesn't fit is
                # simply not placed - and a room reports back the entry it was
                # handed, unchanged. The only node kind that ever answers with
                # a different position is a passage, which reports the far end
                # of everything it walked; joining the door to *that* drew a
                # diagonal across the map, which is not a corridor at all.
                self._enter(child, x, y, heading, level, island, False, path)
            return x, y
        if kind == "stairs":
            length = _cells(node.geo.get("length_ft", 10))
            dx, dy = _VECTORS[heading]
            nx, ny = x + dx * length, y + dy * length
            island["stairs"].append({
                "id": node.id, "x": nx, "y": ny,
                "delta": node.geo.get("level_delta", 0), "to_level": node.geo.get("to_level"),
                "lines": node.lines,
            })
            for child in node.children:
                self._enter(child, nx, ny, heading, level, island, True, path)
            return x, y
        if kind in ("edge", "dead_end"):
            # A branch taken off a T-junction/four-way intersection that
            # immediately dead-ends (most often because the room budget ran
            # out) would otherwise place its cap right on top of the trunk
            # corridor, with nothing to show a branch was ever taken. A
            # short stub - rendered as its own tiny corridor segment, same
            # as any other passage - makes the junction visible even when
            # there's nothing beyond it.
            dx, dy = _VECTORS[heading]
            sx, sy = x + dx * _CAP_STUB_LENGTH, y + dy * _CAP_STUB_LENGTH
            island["corridors"].append({
                "id": f"cap{node.id}", "points": [(x, y), (sx, sy)],
                "width": _cells(DEFAULT_PASSAGE_WIDTH_FT), "lines": [],
            })
            island["_route_cells"] |= _segment_cells((x, y), (sx, sy))
            island["caps"].append({"id": node.id, "x": sx, "y": sy, "kind": kind, "lines": node.lines})
            return x, y
        return x, y

    def _walk_room(self, node, x, y, heading, level, island, path):
        w = _cells(node.geo.get("width_ft", 20))
        depth = _cells(node.geo.get("length_ft", 20))
        dx, dy = _VECTORS[heading]
        px, py = -dy, dx  # perpendicular

        occupied = island["_occupied"]
        # A room is placed where the roll actually put it - at the end of the
        # corridor that leads to it - and the only freedom taken is *where
        # along its own entry wall* that corridor arrives. Offset 0 is the
        # natural result (doorway in the middle of the wall); sliding towards
        # either corner moves the room sideways while the doorway stays put,
        # so a room blocked on one side can sit beside the obstacle instead.
        # The doorway can travel as far as the wall's own corners, no further
        # - past that it would no longer be on the wall at all.
        # One candidate per cell of the entry wall. Enumerated as the room's
        # own low edge rather than as a signed offset from the doorway: the
        # perpendicular axis points the other way for half the headings, so a
        # signed range that is right for one is a cell out for the other.
        #
        # The condition is that the doorway's *cell* is one of the room's, not
        # merely that the doorway sits somewhere on the wall line - a room
        # whose far edge lands exactly on the doorway looks attached but
        # occupies a column the corridor doesn't, so the two only touch at a
        # corner. Hence low edge in [entry - w + 1, entry]: exactly w
        # placements, all of them real.
        entry_perp, perp_sign = (x, px) if px else (y, py)
        offsets = sorted(
            (perp_sign * (low + w / 2 - entry_perp)
             for low in range(round(entry_perp) - w + 1, round(entry_perp) + 1)),
            key=abs,
        )

        # Every corridor cell already drawn, this room's own approach
        # included. Excluding its own route was tried and is not worth it: a
        # corridor stops at the wall, so the leg leading in never overlaps the
        # room anyway, and all the exclusion really permitted was a room
        # landing on an *earlier* stretch of the same corridor - the one that
        # ran past the spot and turned. It saved 7 rooms of 713 and tripled
        # the cells left sitting inside a floor, 0.8% to 2.2%.
        blocking = island["_route_cells"]

        def _sits_on_a_corridor(rect):
            """Whether a candidate footprint would cover a cell some corridor
            already runs down.

            The other half of the same draw-order rule: a passage laid first
            owns the ground, and a room that would have to be built on top of
            it is simply not placed. Checked against the corridor's *cells*,
            so a corridor merely arriving at the room's wall - which is what
            every entrance looks like - does not count as being under it.

            Without this, 103 of the 147 remaining corridor cells inside a
            room's floor came from a room dropped on top of a corridor that
            was already there."""
            rx0, ry0, rx1, ry1 = rect
            return any(
                (gx, gy) in blocking
                for gx in range(int(rx0), int(rx1))
                for gy in range(int(ry0), int(ry1))
            )

        def first_clear(entry_x, entry_y):
            for offset in offsets:
                candidate = _room_aabb(entry_x, entry_y, dx, dy, px, py, w, depth, offset)
                if any(_overlaps(candidate, other, ROOM_MARGIN) for other in occupied):
                    continue
                if _sits_on_a_corridor(candidate):
                    continue
                return offset, candidate
            return None, None

        lateral, footprint = first_clear(x, y)

        if lateral is None:
            # The room does not fit here in any position along its own entry
            # wall. Rather than shove it away down the corridor - which put it
            # somewhere the roll never said, and stretched the passage to
            # reach - it simply isn't placed, and the branch stops here as if
            # it had dead-ended. The room's own roll, contents and children
            # stay in the tree and in the log; only the map loses it.
            node.lines.append(
                "[Layout] Non c'e' spazio sulla mappa per posizionare questa stanza senza "
                "sovrapposizioni - il ramo si interrompe qui (il contenuto resta comunque nel registro)."
            )
            island["caps"].append({"id": node.id, "x": x, "y": y, "kind": "dead_end", "lines": node.lines})
            _mark_branch_not_drawn(node)
            return x, y

        # The doorway keeps the position the corridor arrived at; the room is
        # what moved, so nothing before it has to stretch.
        mid_x, mid_y = x + px * lateral, y + py * lateral
        if abs(lateral) >= _NOTABLE_SLIDE_UNITS:
            node.lines.append(
                f"[Layout] L'ingresso di questa stanza si apre a circa {round(abs(lateral) * FT_PER_UNIT)}ft "
                "dal centro della parete, invece che al centro: la stanza e' stata spostata di lato per non "
                "sovrapporsi ad altre gia' presenti sulla mappa, mantenendo pero' la posizione della porta."
            )

        if path.room_from is not None and path.points:
            prev = path.points[-1]
            blockers = [other for other in occupied if _segment_crosses_room(prev, (x, y), other)]
            if blockers:
                # The detour is only computed to clear its *own* blockers - on
                # a crowded island the jog can occasionally still graze a
                # room that was never checked. Rejecting the detour whenever
                # that happens was tried and made things measurably worse in
                # aggregate (falling back to the original straight line,
                # which is what needed fixing in the first place, tends to
                # cross even more) - a detour that clears the room it was
                # built for is still a net improvement even on the rare
                # occasion it doesn't clear everything.
                path.points.extend(_detour_around(prev, (x, y), blockers))

        # Kept with the room's own id: a passage that later runs into this
        # footprint has to be able to say *which* room it broke into.
        occupied.append((*footprint, node.id))

        # Everything below is the room's own geometry, so it hangs off the
        # middle of its entry wall (mid_x, mid_y) rather than off the doorway
        # - the two coincide only when the room didn't have to slide.
        far_x, far_y = mid_x + dx * depth, mid_y + dy * depth
        corners = [
            (mid_x - px * w / 2, mid_y - py * w / 2),
            (mid_x + px * w / 2, mid_y + py * w / 2),
            (far_x + px * w / 2, far_y + py * w / 2),
            (far_x - px * w / 2, far_y - py * w / 2),
        ]
        rx0, ry0 = min(c[0] for c in corners), min(c[1] for c in corners)
        rx1, ry1 = max(c[0] for c in corners), max(c[1] for c in corners)
        island["rooms"].append({
            "id": node.id, "corners": corners, "shape": node.geo.get("shape", "rect"),
            "content_tag": node.geo.get("content_tag"), "lines": node.lines,
        })

        if path.room_from is not None:
            path.points.append((x, y))
            island["links"].append({
                "from_room": path.room_from, "to_room": node.id,
                "points": list(path.points), "doors": list(path.doors),
            })

        slots = node.geo.get("exit_slots", [])
        # An exit is a 10ft opening, so it takes a whole cell of the wall it's
        # punched into and no two can share one. Each gets its own band of the
        # wall, with a deterministic cell inside it (keyed on the child's id,
        # so it's stable across re-renders but two exits on a long wall don't
        # line up). A wall with fewer cells than exits can't hold them all -
        # those that don't fit are dropped, along with everything beyond them.
        same_wall_count: dict[str, int] = {}
        for slot in slots:
            same_wall_count[slot] = same_wall_count.get(slot, 0) + 1
        band_index = {"forward": 0, "right": 0, "left": 0}
        for child, slot in zip(node.children, slots):
            index = band_index[slot]
            band_index[slot] += 1
            count = same_wall_count[slot]
            # Which way this exit faces decides which wall it's in, and the
            # wall is then read straight off the room's own box. Deriving it
            # from a signed offset around the wall's midpoint instead was
            # wrong for half the rooms: the sign of the perpendicular axis
            # flips with the heading, so a room entered from the south put its
            # side exits one row past its own last row - the corridor then ran
            # alongside the room instead of into it, and dungeongen drew the
            # doorway chip stranded in the rock beside it.
            eh = heading if slot == "forward" else _rotate(heading, slot)
            along_x = eh in ("N", "S")
            wall_cells = int(round(rx1 - rx0 if along_x else ry1 - ry0))
            cell = _banded_wall_offset(index, count, wall_cells, child.id)
            if cell is None:
                child.lines.append(
                    "[Layout] La parete di questa stanza non ha abbastanza spazio per un'altra "
                    "apertura da 10ft - il ramo si interrompe qui (il contenuto resta comunque "
                    "nel registro)."
                )
                _mark_branch_not_drawn(child)
                continue
            # The wall the exit faces, then the cell along it. Both read off
            # the room's box, so the result never depends on which way the
            # room happens to be facing.
            if eh == "N":
                ex, ey = rx0 + cell, ry0
            elif eh == "S":
                ex, ey = rx0 + cell, ry1
            elif eh == "E":
                ex, ey = rx1, ry0 + cell
            else:  # W
                ex, ey = rx0, ry0 + cell
            # "left"/"right" in the log are relative to the direction of
            # travel (matching the rulebook's own narrative convention -
            # tables say things like "a side passage leads off to the
            # left"), which is *not* the same as left/right on a fixed,
            # north-up map once a room isn't itself facing north. Recording
            # the actual compass heading here lets the log clarify which way
            # an exit really points on the map, instead of just repeating a
            # direction that can visually be on the opposite side.
            child.geo["approach_heading"] = eh
            # Recorded regardless of what this exit leads to (room, passage,
            # stairs, dead end...) so a renderer that can only draw actual
            # room-to-room links (dungeongen) still knows every wall this
            # room truly has a breach in, and can punch an opening there even
            # when nothing beyond it ever resolves into a link.
            island["room_exits"].append({"room_id": node.id, "x": ex, "y": ey, "direction": eh})
            self._enter(child, ex, ey, eh, level, island, False, _Path(node.id, (ex, ey)))
        return x, y

    def _walk_passage(self, node, x, y, heading, level, island, path):
        # A passage's width isn't fixed for its whole length - a "narrows"/
        # "widens" roll partway through changes it from that point on - so
        # the walked points are split into separate width-tagged runs rather
        # than one corridor at a single, uniform width (which would either
        # under- or over-state most of its own length).
        width = _cells(node.geo.get("width_ft", DEFAULT_PASSAGE_WIDTH_FT))
        runs = [{"width": width, "points": [(x, y)]}]
        children = iter(node.children)
        pending = None  # a child pulled from the iterator but not dispatched
        had_child = False
        moved = False  # has the *current* run actually advanced yet?

        broke_into = None  # (room_id, wall) once this passage reaches a room already drawn

        def advance(length):
            """Walk `length` cells along the heading, stopping at the wall of
            any room already on the map.

            Draw order decides who gives way. A room is placed only where it
            fits around what is already there; a passage laid down afterwards
            has to stop at the first room it reaches instead of running
            through its floor. It used to run straight on: 318 of 2673
            corridor cells across 40 seeds (11.9%) sat inside a room's floor,
            which dungeongen then drew as passage - a notch eaten out of the
            wall, opening onto nothing."""
            nonlocal x, y, moved, broke_into
            dx, dy = _VECTORS[heading]
            nx, ny = x + dx * length, y + dy * length
            cx, cy, room_id, wall = _clip_at_placed_room(x, y, nx, ny, island["_occupied"])
            if (cx, cy) != (x, y):
                # Claimed as it is walked, not when the node finishes: a room
                # placed by one of this passage's own children would otherwise
                # not see the corridor it is standing on.
                island["_route_cells"] |= _segment_cells((x, y), (cx, cy))
                x, y = cx, cy
                runs[-1]["points"].append((x, y))
                path.points.append((x, y))
                moved = True
            if room_id is not None:
                broke_into = (room_id, wall, (cx, cy))
            return room_id is None

        def ensure_min_length():
            # Several rolls (a door/stairs "in the wall" with no length of
            # its own, "ends in an open entrance to a room", a resize with
            # nothing walked before it...) have no move event at all - the
            # passage would otherwise be a single point, occupying no real
            # space of its own. A passage is a place, not just a hinge
            # between two others, so it always advances by at least one 5ft
            # square before whatever comes next.
            if moved:
                return True
            before = (x, y)
            carried_on = advance(_cells(DEFAULT_PASSAGE_WIDTH_FT))
            if (x, y) != before:
                # Said out loud, because the reader cannot get it from the
                # rolls: a passage whose first roll is a feature in its own
                # wall has no length anywhere in its entry, and looks like a
                # door hanging in nothing. This is the line that gives it a
                # body - and where a "widens"/"narrows" roll comes before any
                # movement, it is also the first of the two 10ft stretches
                # that end up drawn.
                node.lines.append(
                    f"[Layout] Il tiro non dava lunghezza propria al passaggio: sulla mappa "
                    f"percorre comunque il minimo di {round(FT_PER_UNIT)}ft "
                    f"prima di cio' che segue."
                )
            return carried_on

        for event in node.geo.get("events", []):
            etype = event["type"]
            if etype == "move":
                if not advance(_cells(event["length_ft"])):
                    break
            elif etype == "turn":
                # A turn with nothing walked yet ("door in the left wall",
                # rolled with no length of its own) still means the passage
                # itself is a real 5ft space *in its original heading* -
                # the door is a feature found on one of its walls, not the
                # reason the passage has no footprint of its own. Applying
                # the minimum-length floor in the *new* heading instead would
                # put the passage on top of the door's own far side, with
                # nothing distinct at the room's exit at all.
                if not ensure_min_length():
                    break
                heading = _rotate(heading, event["dir"])
                runs[-1]["points"].append((x, y))
                path.points.append((x, y))
                # The passage now has to actually go somewhere in its new
                # direction before anything else happens to it. Leaving
                # `moved` set meant a turn immediately followed by another
                # turn, or by a feature, produced no leg at all in the new
                # heading: the two turns cancelled out on the map and the
                # feature hung off the corner, so "turns left, then an
                # opening on the right" drew as a single 10ft stub.
                moved = False
            elif etype == "resize":
                if not ensure_min_length():
                    break
                # A rulebook "narrows" roll floors at 5ft and "widens" floors
                # at 10ft already (see generator.py) - DEFAULT_PASSAGE_WIDTH_FT
                # here is just a last-resort floor for values from elsewhere.
                width = _cells(max(event["width_ft"], DEFAULT_PASSAGE_WIDTH_FT))
                runs.append({"width": width, "points": [(x, y)]})
                moved = False
            elif etype == "child":
                child = next(children, None)
                if child is None:
                    continue
                had_child = True
                if not ensure_min_length():
                    # Already pulled off the iterator, so the cleanup below
                    # would never see it: hand it back explicitly or this one
                    # child ends up neither drawn nor accounted for.
                    pending = child
                    break
                turn = event.get("turn")
                child_heading = _rotate(heading, turn)
                child.geo["approach_heading"] = child_heading
                bx, by = x, y
                corner = None
                if turn is not None:
                    # A branch leaves through the *side wall of the cell the
                    # passage is standing in*, not from the lattice point its
                    # last step ended on - those differ by a cell, and taking
                    # the endpoint put the branch diagonally off the corner of
                    # the passage instead of against its flank. Two corrections,
                    # on different axes, so they don't interact: step back onto
                    # the last cell along the direction of travel, then leave
                    # from that cell's far edge when the branch heads the
                    # positive way (its near edge when it heads the negative
                    # way, which is already where we are).
                    tdx, tdy = _VECTORS[heading]
                    bdx, bdy = _VECTORS[child_heading]
                    bx += (1 if bdx > 0 else 0) - (1 if tdx > 0 else 0)
                    by += (1 if bdy > 0 else 0) - (1 if tdy > 0 else 0)
                    if bx != x and by != y:
                        # Both corrections fired at once, so the takeoff is
                        # diagonally off the trunk's last point. The route that
                        # records this branch has to bend at a right angle
                        # instead of cutting that corner: back along the
                        # trunk's own axis first, then out to the side.
                        corner = (bx, y) if tdx else (x, by)
                # The trunk's own last cell, which is what the branch leaves
                # from: travelling in the positive direction the cell is behind
                # the lattice point, travelling in the negative one it is the
                # point's own cell.
                tdx, tdy = _VECTORS[heading]
                island["_takeoff"][child.id] = (
                    int(x - (1 if tdx > 0 else 0)), int(y - (1 if tdy > 0 else 0))
                )
                child_path = path.branch((bx, by), corner) if turn is not None else path
                self._enter(child, bx, by, child_heading, level, island,
                            bool(event.get("portal")), child_path)
                # Nothing to reconcile after the child: it is walked from the
                # point we handed it and the trunk has not moved. There used to
                # be a "stretch our last point to meet the child" branch here,
                # for a time when a room that didn't fit was pushed along the
                # heading until it did. Rooms are never pushed now - one that
                # doesn't fit is not placed at all - and instrumenting _enter
                # over the seed sweep showed the *only* kind that ever answers
                # with a different position is a passage, which reports the far
                # end of everything it walked. Stretching to that dragged the
                # trunk's last point across the map and left it diagonal to the
                # one before it, which is not a corridor and is exactly what
                # dungeongen cannot route.
                if event.get("portal"):
                    island["portals"].append({"id": node.id, "x": x, "y": y, "lines": node.lines})
        if broke_into is None:
            for child in children:  # a child with no matching event (shouldn't normally happen)
                had_child = True
                if not ensure_min_length():
                    pending = child
                    break
                self._enter(child, x, y, heading, level, island, False, path)
            if not had_child and ensure_min_length():
                island["caps"].append({"id": node.id, "x": x, "y": y, "kind": "dead_end",
                                       "lines": node.lines})
        # Checked after those too, not only after the event loop. Both of them
        # can be the moment the passage first tries to move, so both can be
        # where it runs into a room - and a break-in reported nowhere left the
        # entry with neither a length nor a reason for not having one.
        if broke_into is not None:
            # The passage has reached a room that was already on the map. It
            # stops against that wall and opens into it - a way in nobody
            # planned, so a secret one, which is what the rules call a passage
            # you arrive at a room by from an unexpected side.
            #
            # Recorded as one of that room's exits so the renderer punches a
            # real breach in the wall, exactly as it does for the room's own
            # openings. Everything past this point of the branch is not drawn:
            # it would carry on inside the room.
            room_id, wall, stop = broke_into
            rect = next((r for r in island["_occupied"] if r[4] == room_id), None)
            # Against the wall actually struck, not just any edge. Accepting
            # any of the four let a passage that began inside the room report
            # a west entrance at a point that merely happened to sit on the
            # room's north edge.
            on_wall = rect is not None and stop[
                {"W": 0, "E": 0, "N": 1, "S": 1}[wall]
            ] == rect[{"W": 0, "E": 2, "N": 1, "S": 3}[wall]]
            if on_wall:
                island["room_exits"].append(
                    # `wall` is already the room's own side - the passage arrives
                    # heading east and strikes the room's *west* wall - and an exit's
                    # direction is the way its opening faces out of the room, so it is
                    # that side verbatim. Recording the opposite put every one of these
                    # openings on the far wall of the room.
                    {"room_id": room_id, "x": stop[0], "y": stop[1],
                     "direction": wall, "secret": True}
                )
                node.lines.append(
                    f"[Layout] Questo passaggio arriva contro la parete {wall} della stanza "
                    f"#{room_id}, gia' disegnata sulla mappa: vi si apre come ingresso segreto "
                    f"e il ramo si interrompe qui (il contenuto resta comunque nel registro)."
                )
            else:
                # No wall to stop against: this passage began inside the room's
                # own floor, because whatever dispatched it was already in
                # there. There is no breach to punch - it is simply somewhere
                # the map has no room for.
                node.lines.append(
                    f"[Layout] Questo passaggio parte gia' dentro la stanza #{room_id}, "
                    f"gia' disegnata sulla mappa: non viene tracciato e il ramo si interrompe "
                    f"qui (il contenuto resta comunque nel registro)."
                )
            # Only what is left to walk. Children dispatched before the passage
            # ran into the room are on the map already, and marking the whole
            # node's subtree told 43 rooms across the sweep that they were not
            # drawn while they plainly were.
            for remaining in ([pending] if pending is not None else []) + list(children):
                for descendant in remaining.walk():
                    if descendant.kind in ("room", "passage", "door", "stairs"):
                        descendant.lines.append(_NOT_DRAWN)
        for i, run in enumerate(runs):
            # A "turn" records a point without moving (it just changes heading
            # in place), so a passage that turns before its first move - or one
            # cut short right after a turn - ends up with the same point twice
            # in a row; RoughJS draws a zero-length segment like that as a
            # stray blob.
            pts = run["points"]
            deduped = [pts[0]]
            for point in pts[1:]:
                if point != deduped[-1]:
                    deduped.append(point)
            # Only the first run keeps this node's own log lines attached -
            # duplicating them on every width-change run would repeat the
            # same tooltip/log text several times over for one passage.
            island["corridors"].append({
                "id": node.id, "points": deduped, "width": run["width"],
                "lines": node.lines if i == 0 else [],
            })
        return x, y


def _island_bbox(island: dict):
    xs, ys = [], []
    for room in island["rooms"]:
        for cx, cy in room["corners"]:
            xs.append(cx); ys.append(cy)
    for corridor in island["corridors"]:
        for cx, cy in corridor["points"]:
            xs.append(cx); ys.append(cy)
    for group in ("doors",):
        for item in island[group]:
            xs += [item["x1"], item["x2"]]
            ys += [item["y1"], item["y2"]]
    for group in ("stairs", "portals", "caps"):
        for item in island[group]:
            xs.append(item["x"]); ys.append(item["y"])
    ox, oy = island["origin"]
    xs.append(ox); ys.append(oy)
    return min(xs), min(ys), max(xs), max(ys)


def _translate_island(island: dict, shift_x: float, shift_y: float) -> None:
    for room in island["rooms"]:
        room["corners"] = [(cx + shift_x, cy + shift_y) for cx, cy in room["corners"]]
    for corridor in island["corridors"]:
        corridor["points"] = [(cx + shift_x, cy + shift_y) for cx, cy in corridor["points"]]
    for door in island["doors"]:
        door["x1"] += shift_x; door["y1"] += shift_y
        door["x2"] += shift_x; door["y2"] += shift_y
    for group in ("stairs", "portals", "caps", "room_exits"):
        for item in island[group]:
            item["x"] += shift_x
            item["y"] += shift_y
    for link in island["links"]:
        link["points"] = [(cx + shift_x, cy + shift_y) for cx, cy in link["points"]]
    # The cell bookkeeping moves with everything else. It used to be left
    # behind: the renderer reads _takeoff *after* this translation, so every
    # branch reported a takeoff cell in pre-translation coordinates - a cell
    # nowhere near it, often at negative y - and not one was ever claimed.
    dx_cells, dy_cells = int(shift_x), int(shift_y)
    island["_takeoff"] = {
        node_id: (cx + dx_cells, cy + dy_cells)
        for node_id, (cx, cy) in island["_takeoff"].items()
    }
    island["_route_cells"] = {
        (cx + dx_cells, cy + dy_cells) for cx, cy in island["_route_cells"]
    }
    ox, oy = island["origin"]
    island["origin"] = (ox + shift_x, oy + shift_y)


def _drop_caps_inside_rooms(island: dict) -> None:
    """A dead-end/edge marker that lands inside a room's own floor is just
    noise (the room already fully accounts for that spot) - it only ever
    happens because caps don't otherwise avoid room interiors like rooms
    avoid each other."""
    if not island["caps"] or not island["rooms"]:
        return
    room_rects = []
    for room in island["rooms"]:
        xs = [c[0] for c in room["corners"]]
        ys = [c[1] for c in room["corners"]]
        room_rects.append((min(xs), min(ys), max(xs), max(ys)))
    # Compared with a small tolerance: a cap frequently sits exactly *on* a
    # room's wall (the corridor arrived there and went no further), and the
    # island is translated afterwards - adding the same shift to two values
    # that differ only in their last bits can round them either way, so an
    # exact comparison here can keep a cap that later reads as inside.
    eps = 1e-6
    island["caps"] = [
        cap for cap in island["caps"]
        if not any(rx0 - eps <= cap["x"] <= rx1 + eps and ry0 - eps <= cap["y"] <= ry1 + eps
                   for rx0, ry0, rx1, ry1 in room_rects)
    ]


def compute_layout(dungeon) -> dict[int, list[dict]]:
    """Return {level: [island, ...]} with islands translated so they never overlap."""
    layout = _Layout()
    layout.walk_root(dungeon.root)

    for islands in layout.levels.values():
        for island in islands:
            _drop_caps_inside_rooms(island)

    result: dict[int, list[dict]] = {}
    for level, islands in sorted(layout.levels.items()):
        offset_x = 0.0
        placed = []
        for island in islands:
            bbox = _island_bbox(island)
            if bbox is None:
                continue
            minx, miny, maxx, maxy = bbox
            _translate_island(island, offset_x - minx, -miny)
            placed.append(island)
            offset_x += (maxx - minx) + 4.0  # margin between islands, in grid units
        result[level] = placed
    return result
