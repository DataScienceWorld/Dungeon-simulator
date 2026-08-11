"""Turn the generated dungeon tree into a 2D layout (rooms, corridors, doors, stairs).

This walks the same tree the CLI/log renderer walks, but interprets each
node's `geo` data (lengths, turns, room footprints - see generator.py) as
turtle-graphics instructions: start at the origin facing north, and move/
turn/branch as each passage segment or room exit dictates. Grid units are
10 ft (matching the tables' own "x10 ft" convention).

A level can have more than one disconnected "island" (e.g. two different
staircases both landing on level 2, or a magical portal jump) - these are
laid out side by side rather than overlapping.
"""

from __future__ import annotations

FT_PER_UNIT = 10.0

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


def _new_island() -> dict:
    return {
        "rooms": [], "corridors": [], "doors": [], "stairs": [], "portals": [], "caps": [],
        "origin": (0.0, 0.0), "is_entrance": False,
    }


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
        self._walk(node, 0.0, 0.0, "N", node.level, island)

    def _enter(self, child, x: float, y: float, heading: str, level: int, island: dict, force_new_island: bool) -> None:
        if force_new_island or child.level != level:
            new_island = self._add_island(child.level)
            self._walk(child, 0.0, 0.0, "N", child.level, new_island)
        else:
            self._walk(child, x, y, heading, level, island)

    def _walk(self, node, x: float, y: float, heading: str, level: int, island: dict) -> None:
        kind = node.kind
        if kind == "start":
            for child in node.children:
                self._enter(child, x, y, heading, level, island, force_new_island=False)
            return
        if kind == "room":
            self._walk_room(node, x, y, heading, level, island)
            return
        if kind == "passage":
            self._walk_passage(node, x, y, heading, level, island)
            return
        if kind == "door":
            length = node.geo.get("length_ft", 5) / FT_PER_UNIT
            dx, dy = _VECTORS[heading]
            nx, ny = x + dx * length, y + dy * length
            island["doors"].append({"id": node.id, "x1": x, "y1": y, "x2": nx, "y2": ny, "lines": node.lines})
            for child in node.children:
                self._enter(child, nx, ny, heading, level, island, force_new_island=False)
            return
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
                self._enter(child, nx, ny, heading, level, island, force_new_island=True)
            return
        if kind in ("edge", "dead_end"):
            island["caps"].append({"id": node.id, "x": x, "y": y, "kind": kind, "lines": node.lines})
            return

    def _walk_room(self, node, x, y, heading, level, island) -> None:
        w = node.geo.get("width_ft", 20) / FT_PER_UNIT
        depth = node.geo.get("length_ft", 20) / FT_PER_UNIT
        dx, dy = _VECTORS[heading]
        px, py = -dy, dx  # perpendicular
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
        slots = node.geo.get("exit_slots", [])
        for child, slot in zip(node.children, slots):
            if slot == "forward":
                ex, ey, eh = far_x, far_y, heading
            elif slot == "right":
                eh = _rotate(heading, "right")
                ex, ey = x + dx * depth / 2 + px * w / 2, y + dy * depth / 2 + py * w / 2
            else:  # left
                eh = _rotate(heading, "left")
                ex, ey = x + dx * depth / 2 - px * w / 2, y + dy * depth / 2 - py * w / 2
            self._enter(child, ex, ey, eh, level, island, force_new_island=False)

    def _walk_passage(self, node, x, y, heading, level, island) -> None:
        points = [(x, y)]
        children = iter(node.children)
        had_child = False
        for event in node.geo.get("events", []):
            etype = event["type"]
            if etype == "move":
                length = event["length_ft"] / FT_PER_UNIT
                dx, dy = _VECTORS[heading]
                x, y = x + dx * length, y + dy * length
                points.append((x, y))
            elif etype == "turn":
                heading = _rotate(heading, event["dir"])
                points.append((x, y))
            elif etype == "resize":
                continue
            elif etype == "child":
                child = next(children, None)
                if child is None:
                    continue
                had_child = True
                child_heading = _rotate(heading, event.get("turn"))
                self._enter(child, x, y, child_heading, level, island, force_new_island=bool(event.get("portal")))
                if event.get("portal"):
                    island["portals"].append({"id": node.id, "x": x, "y": y, "lines": node.lines})
        for child in children:  # any child without a matching event (shouldn't normally happen)
            had_child = True
            self._enter(child, x, y, heading, level, island, force_new_island=False)
        if not had_child:
            island["caps"].append({"id": node.id, "x": x, "y": y, "kind": "dead_end", "lines": node.lines})
        island["corridors"].append({"id": node.id, "points": points, "lines": node.lines})


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
    for group in ("stairs", "portals", "caps"):
        for item in island[group]:
            item["x"] += shift_x
            item["y"] += shift_y
    ox, oy = island["origin"]
    island["origin"] = (ox + shift_x, oy + shift_y)


def compute_layout(dungeon) -> dict[int, list[dict]]:
    """Return {level: [island, ...]} with islands translated so they never overlap."""
    layout = _Layout()
    layout.walk_root(dungeon.root)

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
