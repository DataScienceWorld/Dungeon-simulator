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
    # every link with both ends resolved to a real room becomes exactly one passage
    resolvable_links = [
        link for link in island["links"]
        if any(r["id"] == link["from_room"] for r in island["rooms"])
        and any(r["id"] == link["to_room"] for r in island["rooms"])
    ]
    assert len(dg.passages) <= len(resolvable_links)


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
