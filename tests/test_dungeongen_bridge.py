import pytest

from dungeon_simulator import dungeongen_bridge as bridge
from dungeon_simulator.generator import DungeonGenerator
from dungeon_simulator.layout import compute_layout
from dungeon_simulator.render_map import _dungeongen_level_svg, render_map_section

pytestmark = pytest.mark.skipif(not bridge.available(), reason="dungeongen (or skia-python) is not installed here")


def _first_populated_level(dungeon, min_rooms=2, max_units=None):
    layout = compute_layout(dungeon)
    for level, islands in layout.items():
        if any(not isl["rooms"] for isl in islands):
            continue
        total_rooms = sum(len(isl["rooms"]) for isl in islands)
        if total_rooms < min_rooms:
            continue
        if max_units is not None and not all(bridge.island_extent_map_units(isl) <= max_units for isl in islands):
            continue
        return level, islands
    return None, None


def test_fits_size_limit_agrees_with_extent():
    dungeon = DungeonGenerator(seed=1).generate()
    layout = compute_layout(dungeon)
    for islands in layout.values():
        for island in islands:
            assert bridge.fits_size_limit(island) == (bridge.island_extent_map_units(island) <= bridge._MAX_MAP_UNITS)


def test_build_dungeongen_dungeon_matches_room_and_link_counts():
    dungeon = DungeonGenerator(seed=1).generate()
    _, islands = _first_populated_level(dungeon)
    assert islands is not None, "expected at least one populated level for seed 1"
    island = islands[0]
    dg = bridge.build_dungeongen_dungeon(island)
    assert len(dg.rooms) == len(island["rooms"])
    # every link with both ends resolved to a real room becomes exactly one
    # passage. Counted over room-to-room passages only: dead-end branches are
    # handed to dungeongen as passages too, with a synthetic far end that is
    # deliberately not a room, so they are not links and must not be counted.
    room_ids = {f"r{room['id']}" for room in island["rooms"]}
    resolvable_links = [
        link for link in island["links"]
        if any(r["id"] == link["from_room"] for r in island["rooms"])
        and any(r["id"] == link["to_room"] for r in island["rooms"])
    ]
    room_to_room = [
        p for p in dg.passages.values()
        if p.start_room in room_ids and p.end_room in room_ids
    ]
    assert len(room_to_room) <= len(resolvable_links)


def test_render_island_svg_offset_places_a_room_correctly():
    dungeon = DungeonGenerator(seed=1).generate()
    _, islands = _first_populated_level(dungeon, max_units=bridge._MAX_MAP_UNITS)
    assert islands is not None
    island = islands[0]
    svg, off_x, off_y, scale, width, height = bridge.render_island_svg(island)
    assert "<svg" in svg
    assert width > 0 and height > 0
    room = island["rooms"][0]
    xs = [c[0] for c in room["corners"]]
    ys = [c[1] for c in room["corners"]]
    px_x0, px_y0 = off_x + min(xs) * scale, off_y + min(ys) * scale
    px_x1, px_y1 = off_x + max(xs) * scale, off_y + max(ys) * scale
    # the room's projected pixel box must land fully inside the rendered canvas
    assert 0 <= px_x0 < px_x1 <= width
    assert 0 <= px_y0 < px_y1 <= height


def test_dungeongen_level_svg_returns_none_for_oversized_island():
    dungeon = DungeonGenerator(seed=1).generate()
    layout = compute_layout(dungeon)
    for islands in layout.values():
        for island in islands:
            if not island["rooms"]:
                continue
            oversized = dict(island)
            # push one room far away without touching the original fixture
            far_room = dict(island["rooms"][0])
            far_room["corners"] = [(x + 10_000, y + 10_000) for x, y in far_room["corners"]]
            oversized["rooms"] = [far_room, *island["rooms"][1:]]
            assert _dungeongen_level_svg([oversized]) is None
            return
    pytest.skip("no island with rooms found for seed 1")


def test_dungeongen_level_svg_returns_none_when_any_island_has_no_rooms():
    empty_island = {
        "rooms": [], "corridors": [], "doors": [], "stairs": [], "portals": [],
        "caps": [{"id": 1, "x": 0.0, "y": 0.0, "kind": "dead_end", "lines": []}],
        "links": [], "origin": (0.0, 0.0), "is_entrance": True,
    }
    assert _dungeongen_level_svg([empty_island]) is None


def test_render_map_section_uses_dungeongen_when_it_fits():
    dungeon = DungeonGenerator(seed=1).generate()
    html = render_map_section(dungeon)
    assert 'class="dg-map-svg dg-map-svg-dungeongen"' in html, (
        "expected at least one level to render through dungeongen for seed 1"
    )


def test_render_map_section_falls_back_when_dungeongen_forced_unavailable(monkeypatch):
    monkeypatch.setattr(bridge, "_IMPORT_ERROR", RuntimeError("forced unavailable for this test"))
    dungeon = DungeonGenerator(seed=1).generate()
    html = render_map_section(dungeon)
    assert 'class="dg-map-svg dg-map-svg-dungeongen"' not in html
    assert "<svg" in html


def test_overlay_offset_matches_where_dungeongen_actually_draws():
    """The overlay's grid->pixel transform must undo the exact normalization
    dungeongen's own adapter applied (its integer Dungeon.bounds), not an
    equivalent-looking one derived from our continuous coordinates. When the
    two disagreed the whole overlay - room hit-boxes, door markers, stair
    icons - sat a full cell away from the art it annotates."""
    from dungeongen.graphics.conversions import grid_to_map

    checked = 0
    for seed in (1, 2, 4, 8, 72):
        dungeon = DungeonGenerator(seed=seed).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                if not island["rooms"] or not bridge.fits_size_limit(island):
                    continue
                _, off_x, off_y, scale, _, _ = bridge.render_island_svg(island)
                dg = bridge.build_dungeongen_dungeon(island)
                dg_map = bridge._convert_dungeon(dg, show_numbers=False)
                pad_x, pad_y = grid_to_map(
                    dg_map.options.map_border_cells, dg_map.options.map_border_cells
                )
                bounds = dg_map.bounds
                # where dungeongen really drew each room, in the SVG's own pixels
                drawn = set()
                for room in dg_map.rooms:
                    bbox = room.shape.bounds
                    drawn.add((round(bbox.x + pad_x - bounds.x, 3),
                               round(bbox.y + pad_y - bounds.y, 3)))
                for layout_room in dg.rooms.values():
                    projected = (round(off_x + layout_room.x * scale, 3),
                                 round(off_y + layout_room.y * scale, 3))
                    assert projected in drawn, (
                        f"seed {seed}: overlay projects room to {projected}, "
                        f"but dungeongen drew rooms at {sorted(drawn)}"
                    )
                    checked += 1
    assert checked, "expected at least one island to render through dungeongen"


def test_short_links_still_become_passages():
    """Two rooms 5ft apart are joined by a corridor that fits inside a single
    10ft cell, so its cell path is one cell long. Such a link must still reach
    dungeongen: dropping it (as a `len(waypoints) < 2` guard once did) left the
    rooms drawn with no connection between them at all."""
    seen_single_cell = False
    for seed in (72, 1, 2, 4, 8, 15):
        dungeon = DungeonGenerator(seed=seed, max_depth=5).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                if not island["rooms"] or not bridge.fits_size_limit(island):
                    continue
                placed = {room["id"] for room in island["rooms"]}
                linked_pairs = {
                    (link["from_room"], link["to_room"]) for link in island["links"]
                    if link["from_room"] in placed and link["to_room"] in placed
                }
                if not linked_pairs:
                    continue
                dg = bridge.build_dungeongen_dungeon(island)
                built = {(p.start_room, p.end_room) for p in dg.passages.values()}
                for from_room, to_room in linked_pairs:
                    assert (f"r{from_room}", f"r{to_room}") in built, (
                        f"seed {seed}: link {from_room}->{to_room} never became a passage"
                    )
                for link in island["links"]:
                    if (link["from_room"], link["to_room"]) in linked_pairs:
                        if len(bridge._grid_cell_path(bridge._dedupe(link["points"]))) == 1:
                            seen_single_cell = True
    assert seen_single_cell, "expected at least one link short enough to occupy a single cell"


def test_dungeongen_rooms_never_overlap_each_other():
    """Our own layout guarantees rooms don't overlap. The minimum-size floor
    that makes a 10ft room legible must not overrun that guarantee: grown into
    a neighbour it draws two rooms on top of each other (observed on seed 72,
    where a 10ft circular room 5ft from its neighbour grew a full cell into
    it). Where there is no space to grow, the room stays its true size."""
    for seed in range(40):
        dungeon = DungeonGenerator(seed=seed).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                if not island["rooms"] or not bridge.fits_size_limit(island):
                    continue
                dg = bridge.build_dungeongen_dungeon(island)
                rects = [
                    (r.x, r.y, r.x + r.width, r.y + r.height) for r in dg.rooms.values()
                ]
                for i, a in enumerate(rects):
                    for b in rects[i + 1:]:
                        assert not bridge._cell_rects_overlap(a, b), (
                            f"seed {seed}: dungeongen rooms {a} and {b} overlap"
                        )


def test_rooms_are_not_drawn_wider_than_they_are():
    """A room's cell rect must not claim more ground than the room really
    covers. It did: `round()` is banker's rounding, so a room from 6.5 to 9.5
    had its ends rounded in opposite directions and came out 4 cells wide when
    it is 3 - and the extra cell was one the corridor leaving its own wall
    needed, which is how 10ft of a 70ft passage ended up inside room 6.

    Rooms small enough for the legibility floor to inflate are exempt: that
    inflation is deliberate, and is covered by the overlap test above.
    """
    import math

    checked = 0
    # (seed, max_depth) - seed 72 at depth 5 is the case that exposed this:
    # room 6 runs 6.5..9.5, whose ends banker's rounding sends opposite ways.
    cases = [(seed, None) for seed in range(40)] + [(72, 5), (1, 5), (8, 5)]
    for seed, max_depth in cases:
        dungeon = DungeonGenerator(seed=seed, max_depth=max_depth).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                if not island["rooms"] or not bridge.fits_size_limit(island):
                    continue
                dg = bridge.build_dungeongen_dungeon(island)
                for room in island["rooms"]:
                    drawn = dg.rooms.get(f"r{room['id']}")
                    if drawn is None:
                        continue
                    xs = [c[0] for c in room["corners"]]
                    ys = [c[1] for c in room["corners"]]
                    real_w, real_h = max(xs) - min(xs), max(ys) - min(ys)
                    if real_w < bridge._MIN_ROOM_GRID_UNITS or real_h < bridge._MIN_ROOM_GRID_UNITS:
                        continue  # the legibility floor may legitimately grow it
                    assert drawn.width <= math.ceil(real_w - 1e-9), (
                        f"seed {seed} room {room['id']}: drawn {drawn.width} cells wide "
                        f"but only {real_w} cells of room"
                    )
                    assert drawn.height <= math.ceil(real_h - 1e-9), (
                        f"seed {seed} room {room['id']}: drawn {drawn.height} cells tall "
                        f"but only {real_h} cells of room"
                    )
                    checked += 1
    assert checked, "expected at least one room to check"

