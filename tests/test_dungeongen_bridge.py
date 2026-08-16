import html as _html

import pytest

from dungeon_simulator import dungeongen_bridge as bridge
from dungeon_simulator.generator import DungeonGenerator
from dungeon_simulator.layout import compute_layout
from dungeon_simulator.render_map import (
    _dungeongen_level_svg,
    _full_text,
    render_map_section,
)

pytestmark = pytest.mark.skipif(not bridge.available(), reason="dungeongen (or skia-python) is not installed here")


def _first_populated_level(dungeon, min_rooms=2, max_units=None):
    """A level with enough rooms on it for the caller to have something to
    check. It used to skip any level carrying a room-less island, back when
    one of those forced the whole level to the fallback renderer. That is no
    longer true, and the filter had become a way to reject most levels for no
    reason - 57% of islands have no rooms, so seeds stopped qualifying at all
    as the generator explored more."""
    layout = compute_layout(dungeon)
    for level, islands in layout.items():
        total_rooms = sum(len(isl["rooms"]) for isl in islands)
        if total_rooms < min_rooms:
            continue
        if max_units is not None and not all(bridge.island_extent_map_units(isl) <= max_units for isl in islands):
            continue
        return level, islands
    return None, None


def _rooms_island(islands):
    """The first island on the level that actually has rooms in it."""
    return next(isl for isl in islands if isl["rooms"])


def _find_four_way(seeds=range(40)):
    """Locate a four-way intersection the generator actually rolled, and
    report the cells its four arms occupy.

    Deliberately searched for rather than pinned to coordinates. The two
    tests below used to name seed 72's cell (14,15) outright, which held only
    as long as nothing upstream touched the dice: one clause added to the
    passage table shifted the whole stream and left them asserting things
    about a dungeon that no longer exists. What they are really about is the
    shape of a crossing, and that can be found wherever it turns up.

    Returns (island, junction_cell, arm_cells) or None."""
    for seed in seeds:
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        four_ways = {
            n.id: n for n in dungeon.all_nodes()
            if n.kind == "passage" and any("four-way intersection" in line for line in n.lines)
        }
        if not four_ways:
            continue
        for islands in compute_layout(dungeon).values():
            for island in islands:
                if not island["rooms"] or not bridge.fits_size_limit(island):
                    continue
                corridors = {}
                for corridor in island["corridors"]:
                    corridors.setdefault(corridor["id"], []).append(corridor)
                for node_id, node in four_ways.items():
                    trunk = corridors.get(node_id)
                    arms = [corridors.get(c.id) for c in node.children]
                    if trunk is None or not all(arms):
                        continue
                    junction = bridge._grid_cell_path(trunk[-1]["points"])[-1]
                    arm_cells = [bridge._grid_cell_path(a[0]["points"])[0] for a in arms]
                    # only the clean case: three distinct arms, each starting
                    # on a cell next to the junction
                    if len(set(arm_cells)) != len(arm_cells):
                        continue
                    if not all(abs(c[0] - junction[0]) + abs(c[1] - junction[1]) <= 1
                               for c in arm_cells):
                        continue
                    return island, junction, arm_cells
    return None


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
    island = _rooms_island(islands)
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


def test_a_level_with_a_room_less_island_still_gets_dungeongen_art():
    """A room-less island - a dead end, or a stub behind a stairs/portal jump
    that went nowhere - used to drop the *entire level* to the RoughJS
    renderer. Those islands are the majority (54% of islands across 40 seeds),
    so most levels never got dungeongen's art: 35% did before this, 100% after.

    The island itself has to survive the change, which is the part worth
    pinning: its dead-end and stairs markers live only in the overlay, and an
    island quietly left out of the composition would take them with it."""
    dungeon = DungeonGenerator(seed=72).generate()
    layout = compute_layout(dungeon)
    level, islands = next(
        (lv, isl) for lv, isl in sorted(layout.items())
        if any(not i["rooms"] for i in isl) and any(i["rooms"] for i in isl)
    )
    result = _dungeongen_level_svg(islands)
    assert result is not None, f"level {level} still falls back despite fitting"

    checked = 0
    for island in islands:
        if island["rooms"]:
            continue
        # A cap's marker is labelled with its own id - deliberately not with
        # its log text, which is what the id is there to let you look up.
        for cap in island["caps"]:
            assert f'>#{cap["id"]}</text>' in result["svg"], (
                f"a '{cap['kind']}' marker (#{cap['id']}) on the room-less island "
                f"is not in the composed SVG"
            )
            checked += 1
        for stair in island["stairs"]:
            assert f'L{stair.get("to_level")}' in result["svg"], (
                "a stairs marker on the room-less island is not in the composed SVG"
            )
            checked += 1
    assert checked, "expected the room-less island to carry at least one marker"


def test_a_level_of_nothing_but_room_less_islands_renders_too():
    """The degenerate end of the same case, and the one that exercises our own
    normalization on its own: with no rooms anywhere, dungeongen's adapter
    normalizes by a placeholder box and leaves the island at its raw grid
    position - which for an island late in a level is thousands of map units
    out, past a limit its native side answers with a segfault."""
    dungeon = DungeonGenerator(seed=72).generate()
    layout = compute_layout(dungeon)
    islands = next(
        isl for _, isl in sorted(layout.items()) if all(not i["rooms"] for i in isl)
    )
    assert _dungeongen_level_svg(islands) is not None


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



def _passage_cells(dg):
    cells = set()
    for passage in dg.passages.values():
        cells |= bridge._path_cells(list(passage.waypoints))
    return cells


def test_every_corridor_the_layout_drew_reaches_dungeongen():
    """A corridor that dungeongen is never told about is simply not on the
    map: nothing else draws it (the overlay stopped inking corridors of its
    own), so the branch it belongs to vanishes into the rock.

    A corridor may legitimately be skipped when it is already covered - a
    room-to-room link and the corridors it is made of are the same geometry
    handed over twice. What decides that has to be the *cells*, though. The
    old test was "does this corridor's first point coincide with a point of
    some link", and a four-way intersection is precisely where that lies: its
    arms leave from a cell the through-route passes through, so the arms were
    dropped as already-drawn while nothing drew them.

    Verified to fail on the state before the fix - seed 72's four-way lost
    its north arm - and across 40 seeds the fix adds 38 cells over 14 islands
    while losing none."""
    for seed in range(40):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                if not island["rooms"] or not bridge.fits_size_limit(island):
                    continue
                drawn = _passage_cells(bridge.build_dungeongen_dungeon(island))
                for corridor in island["corridors"]:
                    points = bridge._dedupe(corridor["points"])
                    if len(points) < 2:
                        continue
                    want = bridge._path_cells(
                        bridge._pad_single_cell(bridge._grid_cell_path(points))
                    )
                    missing = want - drawn
                    assert not missing, (
                        f"seed {seed}: corridor {corridor['id']} covers {sorted(want)} "
                        f"but dungeongen was never told about {sorted(missing)}"
                    )


def test_a_four_way_intersection_reaches_dungeongen_with_all_four_arms():
    """A crossing the generator rolled has to arrive at dungeongen whole: the
    junction cell, and the cell each of the three arms leaves through.

    Only the sweep above proves no corridor is missing; this states what the
    crossing itself has to look like once it gets there, which is what the
    map is actually judged on."""
    found = _find_four_way()
    assert found is not None, "no four-way intersection found across the sweep"
    island, junction, arms = found
    cells = _passage_cells(bridge.build_dungeongen_dungeon(island))
    assert junction in cells, f"the junction {junction} never reaches dungeongen"
    for arm in arms:
        assert arm in cells, f"the arm at {arm} never reaches dungeongen"


def test_the_four_way_is_one_connected_region_in_dungeongens_own_model():
    """Reaching dungeongen is not the same as being drawn as a crossing.

    Its adapter calls a cell a crossing only when two passages *occupy the
    same cell*: it splits both there and connects the pieces. An arm that
    merely runs up against the flank of the through-route shares no cell with
    it, so the adapter treats them as unrelated, puts them in separate
    connected regions, and inks a wall between - the arm renders as a sealed
    stub beside the crossing.

    Asked of dungeongen itself rather than of the picture: Map's own
    _trace_connected_region walks what is actually reachable, and every arm
    has to come back sharing a region with the junction.

    Deliberately not "all of them in one region". Arm-to-arm *through* the
    crossing does not hold yet on every shape: where several passages overlap
    the junction cell, dungeongen's adapter sometimes leaves their segments
    unconnected to each other even though each is connected to the trunk. That
    is inside its own splitting logic and is written up in TODO.md; what this
    pins is the part that is ours - no arm is walled off from the crossing it
    leaves.

    Verified to fail without _claim_takeoff_cell: the side arms came back as
    regions of their own, sharing nothing with the junction."""
    from dungeongen.constants import CELL_SIZE

    found = _find_four_way()
    assert found is not None, "no four-way intersection found across the sweep"
    island, junction, arms = found
    dg = bridge.build_dungeongen_dungeon(island)
    dungeon_map = bridge._convert_dungeon(dg, show_numbers=False)

    visited, regions = set(), []
    for element in dungeon_map._elements:
        if element in visited:
            continue
        region = []
        dungeon_map._trace_connected_region(element, visited, region)
        regions.append(region)

    bx, by = dg.bounds[0], dg.bounds[1]  # dungeongen re-normalises to its own bounds

    def regions_at(cell):
        mx = (cell[0] - bx) * CELL_SIZE + CELL_SIZE / 2
        my = (cell[1] - by) * CELL_SIZE + CELL_SIZE / 2
        hits = set()
        for i, region in enumerate(regions):
            for element in region:
                b = getattr(element, "bounds", None)
                if b and b.x <= mx <= b.x + b.width and b.y <= my <= b.y + b.height:
                    hits.add(i)
                    break
        return hits

    at = {cell: regions_at(cell) for cell in [junction, *arms]}
    for cell, hits in at.items():
        assert hits, f"{cell} is not covered by any element"
    junction_regions = at[junction]
    for cell, hits in at.items():
        assert hits & junction_regions, (
            f"the arm at {cell} is walled off from the junction {junction}: "
            f"it is in {sorted(hits)}, the junction in {sorted(junction_regions)}"
        )
