"""Turn the generated dungeon tree into a 2D layout (rooms, corridors, doors, stairs).

This walks the same tree the CLI/log renderer walks, but interprets each
node's `geo` data (lengths, turns, room footprints - see generator.py) as
turtle-graphics instructions: start at the origin facing north, and move/
turn/branch as each passage segment or room exit dictates. Grid units are
10 ft (matching the tables' own "x10 ft" convention).

The tree has no idea about physical space, so two unrelated branches can
easily land on the same spot. Whenever a room is about to be placed, this
walk checks it against every room already placed in the same island and,
if it would overlap, pushes it further along the direction it's arriving
from until it's clear - the connecting corridor/door simply stretches to
reach it. This is exactly the kind of adjustment the source material's own
"blanket rules" sanction (curtail/adjust features so the map stays legible)
so favoring readability over pixel-exact corridor lengths is intentional.

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
ROOM_MARGIN = 0.6  # minimum clear gap kept between two rooms' footprints, in grid units
_PUSH_STEP = 0.5
_CAP_STUB_LENGTH = 1.0  # length of the little corridor stub drawn before a dead-end/edge cap
_MAX_PUSH_ATTEMPTS = 160  # max push reach of _PUSH_STEP*_MAX_PUSH_ATTEMPTS = 80 grid units;
# denser islands (more evenly-explored branches competing for the same
# space) need more room to find genuinely clear ground - 80 attempts (40
# units) was observed to still leave rooms overlapping on some seeds.
_NOTABLE_PUSH_UNITS = 2.0  # 20ft - a push at least this large gets called out in the log (see _walk_room)

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


_WALL_INSET_FRAC = 0.2  # keep an exit within the middle 60% of the wall it's on,
# away from the corners


def _pseudo_unit(n: int) -> float:
    """Deterministic pseudo-random value in [0, 1) derived from an integer id.
    Where an exit sits along the wall it's on is cosmetic layout jitter, not
    a rulebook roll, so it doesn't need to come from the shared dice stream -
    but it must still be stable across re-renders of the same dungeon, hence
    a hash of the (stable, unique) node id rather than a fresh random draw."""
    return ((n * 2654435761) & 0xFFFFFFFF) / 0xFFFFFFFF


def _banded_wall_offset(index: int, count: int, wall_length: float, node_id: int) -> float:
    """A deterministic offset from the center of a wall of the given length,
    for the `index`-th of `count` exits sharing that wall. Each exit gets its
    own equal-width band along the wall - two same-wall exits independently
    randomized across the *whole* wall can still coincidentally land close
    enough to read as one (observed: two "forward" exits 6ft apart on a
    70ft-wide room). Confining each to its own band guarantees a minimum
    separation of one band width; _WALL_INSET_FRAC still keeps it off that
    band's own edges, so it doesn't crowd the wall's actual corners either."""
    band = wall_length / count
    band_start = -wall_length / 2 + index * band
    inset = band * _WALL_INSET_FRAC
    usable = max(0.0, band - 2 * inset)
    return band_start + inset + _pseudo_unit(node_id) * usable


def _new_island() -> dict:
    return {
        "rooms": [], "corridors": [], "doors": [], "stairs": [], "portals": [], "caps": [],
        "links": [], "room_exits": [], "origin": (0.0, 0.0), "is_entrance": False, "_occupied": [],
    }


def _room_aabb(entry_x, entry_y, dx, dy, px, py, w, depth):
    far_x, far_y = entry_x + dx * depth, entry_y + dy * depth
    corners = [
        (entry_x - px * w / 2, entry_y - py * w / 2),
        (entry_x + px * w / 2, entry_y + py * w / 2),
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
    bx0, by0, bx1, by1 = bbox
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

    def branch(self, start_point):
        return _Path(self.room_from, start_point)


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
        """Walk into `child`. Returns the (x, y) actually used for its entry point -
        which may be further along `heading` than requested if a room had to be
        pushed clear of something already on the map. Crossing into a new island
        (different level, or an explicit portal jump) never affects this island's
        coordinates, so the original (x, y) is echoed back unchanged."""
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
            length = node.geo.get("length_ft", 5) / FT_PER_UNIT
            dx, dy = _VECTORS[heading]
            nx, ny = x + dx * length, y + dy * length
            door = {"id": node.id, "x1": x, "y1": y, "x2": nx, "y2": ny, "lines": node.lines}
            island["doors"].append(door)
            path.points.append((nx, ny))
            path.doors.append(door)
            for child in node.children:
                ax, ay = self._enter(child, nx, ny, heading, level, island, False, path)
                if (ax, ay) != (nx, ny):
                    # Whatever's beyond (usually a room) had to be pushed
                    # clear of something else already on the map. Stretching
                    # the door's own glyph to bridge that gap would draw one
                    # absurdly long "door" - a door is a single fixture, not
                    # a corridor - so the gap gets its own plain connecting
                    # corridor instead, and the door stays its real size.
                    island["corridors"].append({
                        "id": f"stretch{node.id}", "points": [(nx, ny), (ax, ay)],
                        "width": DEFAULT_PASSAGE_WIDTH_FT / FT_PER_UNIT, "lines": [],
                    })
            return x, y
        if kind == "stairs":
            length = node.geo.get("length_ft", 10) / FT_PER_UNIT
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
                "width": DEFAULT_PASSAGE_WIDTH_FT / FT_PER_UNIT, "lines": [],
            })
            island["caps"].append({"id": node.id, "x": sx, "y": sy, "kind": kind, "lines": node.lines})
            return x, y
        return x, y

    def _walk_room(self, node, x, y, heading, level, island, path):
        w = node.geo.get("width_ft", 20) / FT_PER_UNIT
        depth = node.geo.get("length_ft", 20) / FT_PER_UNIT
        dx, dy = _VECTORS[heading]
        px, py = -dy, dx  # perpendicular

        occupied = island["_occupied"]
        pushed = 0.0
        placed = False
        for _ in range(_MAX_PUSH_ATTEMPTS):
            candidate = _room_aabb(x + dx * pushed, y + dy * pushed, dx, dy, px, py, w, depth)
            if not any(_overlaps(candidate, other, ROOM_MARGIN) for other in occupied):
                placed = True
                break
            pushed += _PUSH_STEP

        if not placed:
            # No amount of pushing along the approach direction found clear
            # ground - rather than accept an overlapping room (a map
            # correctness violation), drop it and stop this branch here, as
            # if it had dead-ended. The room's own roll/contents/children
            # are untouched in the tree - only the map (and the log, via
            # this note) reflect the failed placement.
            node.lines.append(
                "[Layout] Non c'e' spazio sulla mappa per posizionare questa stanza senza "
                "sovrapposizioni - il ramo si interrompe qui (il contenuto resta comunque nel registro)."
            )
            island["caps"].append({"id": node.id, "x": x, "y": y, "kind": "dead_end", "lines": node.lines})
            return x, y

        x, y = x + dx * pushed, y + dy * pushed
        if pushed >= _NOTABLE_PUSH_UNITS:
            # A small nudge to clear a neighbour is routine and not worth
            # mentioning, but a large one means the room ended up far from
            # where the roll "naturally" placed it - the connecting door or
            # passage stretches to match, which reads as an oddly long
            # corridor on the map unless the log explains why.
            node.lines.append(
                f"[Layout] Questa stanza e' stata spostata di circa {round(pushed * FT_PER_UNIT)}ft "
                "rispetto alla posizione naturale, per non sovrapporsi ad altre stanze gia' presenti "
                "sulla mappa - il corridoio/porta che la precede si allunga di conseguenza."
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

        occupied.append(candidate)

        far_x, far_y = x + dx * depth, y + dy * depth
        corners = [
            (x - px * w / 2, y - py * w / 2),
            (x + px * w / 2, y + py * w / 2),
            (far_x + px * w / 2, far_y + py * w / 2),
            (far_x - px * w / 2, far_y - py * w / 2),
        ]
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
        # An exit's position along its wall is randomized (deterministically,
        # keyed on the child's id) rather than fixed dead-center, and - when
        # more than one exit shares a wall (e.g. a room with two "forward"
        # slots) - confined to its own equal-width band along that wall.
        # Independent randomization alone isn't enough: two same-wall exits
        # can still coincidentally land close enough to read as a single
        # exit (observed: two "forward" exits only 6ft apart on a 70ft-wide
        # room); banding guarantees they can never be closer than one band.
        same_wall_count: dict[str, int] = {}
        for slot in slots:
            same_wall_count[slot] = same_wall_count.get(slot, 0) + 1
        band_index = {"forward": 0, "right": 0, "left": 0}
        for child, slot in zip(node.children, slots):
            index = band_index[slot]
            band_index[slot] += 1
            count = same_wall_count[slot]
            if slot == "forward":
                offset = _banded_wall_offset(index, count, w, child.id)
                ex, ey, eh = far_x + px * offset, far_y + py * offset, heading
            elif slot == "right":
                offset = _banded_wall_offset(index, count, depth, child.id)
                eh = _rotate(heading, "right")
                ex, ey = x + dx * (depth / 2 + offset) + px * w / 2, y + dy * (depth / 2 + offset) + py * w / 2
            else:  # left
                offset = _banded_wall_offset(index, count, depth, child.id)
                eh = _rotate(heading, "left")
                ex, ey = x + dx * (depth / 2 + offset) - px * w / 2, y + dy * (depth / 2 + offset) - py * w / 2
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
        width = node.geo.get("width_ft", DEFAULT_PASSAGE_WIDTH_FT) / FT_PER_UNIT
        runs = [{"width": width, "points": [(x, y)]}]
        children = iter(node.children)
        had_child = False
        moved = False  # has the *current* run actually advanced yet?

        def ensure_min_length():
            # Several rolls (a door/stairs "in the wall" with no length of
            # its own, "ends in an open entrance to a room", a resize with
            # nothing walked before it...) have no move event at all - the
            # passage would otherwise be a single point, occupying no real
            # space of its own. A passage is a place, not just a hinge
            # between two others, so it always advances by at least one 5ft
            # square before whatever comes next.
            nonlocal x, y, moved
            if moved:
                return
            dx, dy = _VECTORS[heading]
            x, y = x + dx * (DEFAULT_PASSAGE_WIDTH_FT / FT_PER_UNIT), y + dy * (DEFAULT_PASSAGE_WIDTH_FT / FT_PER_UNIT)
            runs[-1]["points"].append((x, y))
            path.points.append((x, y))
            moved = True

        for event in node.geo.get("events", []):
            etype = event["type"]
            if etype == "move":
                length = event["length_ft"] / FT_PER_UNIT
                dx, dy = _VECTORS[heading]
                x, y = x + dx * length, y + dy * length
                runs[-1]["points"].append((x, y))
                path.points.append((x, y))
                moved = True
            elif etype == "turn":
                heading = _rotate(heading, event["dir"])
                runs[-1]["points"].append((x, y))
                path.points.append((x, y))
            elif etype == "resize":
                ensure_min_length()
                # A rulebook "narrows" roll floors at 5ft and "widens" floors
                # at 10ft already (see generator.py) - DEFAULT_PASSAGE_WIDTH_FT
                # here is just a last-resort floor for values from elsewhere.
                width = max(event["width_ft"], DEFAULT_PASSAGE_WIDTH_FT) / FT_PER_UNIT
                runs.append({"width": width, "points": [(x, y)]})
                moved = False
            elif etype == "child":
                child = next(children, None)
                if child is None:
                    continue
                had_child = True
                ensure_min_length()
                turn = event.get("turn")
                child_heading = _rotate(heading, turn)
                child.geo["approach_heading"] = child_heading
                child_path = path.branch((x, y)) if turn is not None else path
                ax, ay = self._enter(child, x, y, child_heading, level, island,
                                      bool(event.get("portal")), child_path)
                if event.get("portal"):
                    island["portals"].append({"id": node.id, "x": x, "y": y, "lines": node.lines})
                elif turn is None and (ax, ay) != (x, y):
                    # A same-direction terminal dispatch (door/stairs/room/shaft) got
                    # pushed clear of something else - stretch our own last point to
                    # meet it. Branch takeoffs (turn is not None) never need this: the
                    # branch is a separate corridor that fixes up its own trailing
                    # point the same way, and the trunk itself hasn't moved.
                    runs[-1]["points"][-1] = (ax, ay)
                    x, y = ax, ay
        for child in children:  # any child without a matching event (shouldn't normally happen)
            had_child = True
            ensure_min_length()
            self._enter(child, x, y, heading, level, island, False, path)
        if not had_child:
            ensure_min_length()
            island["caps"].append({"id": node.id, "x": x, "y": y, "kind": "dead_end", "lines": node.lines})
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
    island["caps"] = [
        cap for cap in island["caps"]
        if not any(rx0 <= cap["x"] <= rx1 and ry0 <= cap["y"] <= ry1 for rx0, ry0, rx1, ry1 in room_rects)
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
