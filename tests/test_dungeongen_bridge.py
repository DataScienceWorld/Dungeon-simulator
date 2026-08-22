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
                    # An arm that never got to move - it ran into something at
                    # the moment it took off - is a single point, and nothing
                    # draws it. The crossing to check is one that is actually
                    # drawn, so those cases are not it.
                    if any(len(bridge._dedupe(a[0]["points"])) < 2 for a in [trunk, *arms]):
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
    # Excluding the stairs alcoves, which are rooms dungeongen is told
    # about but our layout does not count as rooms - they are the single
    # cell a staircase is drawn in.
    real_rooms = [r for r in dg.rooms if not r.startswith("stair")]
    assert len(real_rooms) == len(island["rooms"])
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
            # Two rooms at least: the guard measures the island's own extent,
            # not how far from the origin it sits, so stretching it needs
            # something to stretch *away from*.
            if len(island["rooms"]) < 2:
                continue
            oversized = dict(island)
            # push one room far away without touching the original fixture
            far_room = dict(island["rooms"][0])
            far_room["corners"] = [(x + 10_000, y + 10_000) for x, y in far_room["corners"]]
            oversized["rooms"] = [far_room, *island["rooms"][1:]]
            assert _dungeongen_level_svg([oversized]) is None
            return
    pytest.skip("no island with two or more rooms found for seed 1")


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
    # Searched for rather than pinned to a seed: seed 72 had such a level
    # until a change to the dice moved it, and what this is about is the shape
    # of the case, which turns up somewhere in any handful of seeds.
    islands = None
    for seed in range(20):
        layout = compute_layout(DungeonGenerator(seed=seed).generate())
        islands = next(
            (isl for _, isl in sorted(layout.items())
             if all(not i["rooms"] for i in isl)), None)
        if islands is not None:
            break
    assert islands is not None, "no level of room-less islands found in 20 seeds"
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
                built = bridge.build_dungeongen_dungeon(island)
                drawn = _passage_cells(built)
                # A stairs corridor reaches dungeongen as the one-cell
                # room its steps are drawn in, not as a passage - that
                # is what gives the alcove walls of its own. Still
                # drawn, so still counted.
                drawn |= {
                    (x, y)
                    for rid, room in built.rooms.items() if rid.startswith("stair")
                    for x in range(room.x, room.x + room.width)
                    for y in range(room.y, room.y + room.height)
                }
                # A stairs cell that fell inside a room keeps no alcove of its
                # own - that would be a room drawn inside a room - so it is the
                # room's floor that draws it. Still not rock, so still drawn,
                # but only this case gets the allowance.
                room_cells = {
                    (x, y)
                    for room in built.rooms.values()
                    for x in range(room.x, room.x + room.width)
                    for y in range(room.y, room.y + room.height)
                }
                for corridor in island["corridors"]:
                    points = bridge._dedupe(corridor["points"])
                    if len(points) < 2:
                        continue
                    want = bridge._path_cells(
                        bridge._pad_single_cell(bridge._grid_cell_path(points))
                    )
                    allowed = drawn | room_cells if str(corridor["id"]).startswith("stairs") else drawn
                    missing = want - allowed
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


def test_two_rooms_joined_by_a_door_keep_the_wall_between_them():
    """An open door is not just a different glyph in dungeongen: its own
    region tracing walks straight through one, so the two rooms collapse into
    a single region and the wall between them is never drawn - they read as
    one big room.

    Now that a door takes no cell of its own, two rooms joined by nothing but
    a door share a wall, and that is exactly when it matters. The link's own
    cell and the door's sit on opposite sides of that shared wall, so the
    cell comparison that decides the door's type never matched and every one
    of them came over OPEN. Seed 72's rooms 1 and 10 - joined by a *secret*
    door, of all things - were drawn merged.

    A secret door goes over *closed* too, and deliberately so. dungeongen has
    a SECRET type, but the webview adapter we render through folds it into an
    open door - and an open door is not a glyph, it is a hole. Handing it over
    honestly produced the one thing a secret door must not be: an opening,
    with the wall it hides in erased. The overlay draws the "S" mark instead.

    The match works because the route records crossing the threshold. A door
    takes no cell of its own, so without that step the link's path stopped on
    the near side of it and its end cell could never equal the door's - which
    is how seed 72's rooms 1 and 14, two rooms that merely share a wall, came
    out drawn as one."""
    checked = secrets = 0
    for seed in range(30):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                placed = {room["id"] for room in island["rooms"]}
                threshold_links = [
                    link for link in island["links"]
                    if link["from_room"] in placed and link["to_room"] in placed
                    and link["doors"]
                    and len(bridge._grid_cell_path(bridge._dedupe(link["points"]))) == 1
                ]
                if not threshold_links:
                    continue
                for link in threshold_links:
                    for end in bridge.link_end_cells(link):
                        kind = bridge._door_type_at(link, end)
                        assert kind.name != "OPEN", (
                            f"seed {seed}: rooms #{link['from_room']} and #{link['to_room']} are "
                            f"joined by a door but it is handed over OPEN, which erases their wall"
                        )
                        if link["doors"][0].get("secret"):
                            assert kind.name == "CLOSED", (
                                f"seed {seed}: a secret door came over as {kind.name}; "
                                f"anything but CLOSED loses the wall it is hidden in"
                            )
                            secrets += 1
                        checked += 1
    assert checked > 50, f"expected plenty of door-only links, found {checked}"
    assert secrets, "expected at least one secret door among them"


def test_a_secret_door_is_marked_by_the_overlay():
    """Since dungeongen cannot draw one on this path, the map has to say
    "secret" itself - otherwise a secret door is indistinguishable from any
    other closed door, which is the opposite of useful."""
    from dungeon_simulator.render_map import _dungeongen_overlay_for_island

    found = 0
    for seed in range(30):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                secret = [d for d in island["doors"] if d.get("secret")]
                if not secret:
                    continue
                overlay = _dungeongen_overlay_for_island(island, 0, 0, 64)
                assert overlay.count("Porta segreta.") >= len(secret), (
                    f"seed {seed}: {len(secret)} secret doors but the overlay marks fewer"
                )
                assert ">S</text>" in overlay
                found += len(secret)
    assert found, "expected at least one secret door across the sweep"


def test_a_secret_entrance_is_marked_by_the_overlay_too():
    """There are two different secret ways in, and only one of them is a door.

    A secret *door* comes off the door table and lives in `island["doors"]`.
    A secret *entrance* is the other case entirely: a passage runs into a room
    that is already drawn, stops at its wall and opens a way in nobody rolled
    for. It lives in `island["room_exits"]` with `secret` set, and the bridge
    hands it to dungeongen as a plain breach in the wall - which draws exactly
    like every ordinary exit. Seed 72's passage 15, which breaks into room 14
    from the south, is one of ten on that level alone: the log said "ingresso
    segreto" and the map showed a doorway.

    So the overlay has to mark these as well, and the tooltip has to name the
    room that was broken into - that is the only place the map says where the
    passage actually ended up."""
    from dungeon_simulator.render_map import _dungeongen_overlay_for_island

    scale = 64.0
    found = 0
    for seed in range(30):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                secret = [e for e in island.get("room_exits", []) if e.get("secret")]
                if not secret:
                    continue
                overlay = _dungeongen_overlay_for_island(island, 0.0, 0.0, scale)
                for entrance in secret:
                    tip = f"Ingresso segreto nella stanza #{entrance['room_id']}"
                    assert tip in overlay, (
                        f"seed {seed}: the passage that broke into room "
                        f"#{entrance['room_id']} is drawn as an ordinary doorway"
                    )
                    # And on the wall it broke through, not merely somewhere on
                    # the page: the hit rect is centred on the mark, so its own
                    # coordinates say where the "S" landed.
                    wall = entrance["direction"]
                    if wall in ("W", "E"):
                        cx, cy = entrance["x"], entrance["y"] + 0.5
                    else:
                        cx, cy = entrance["x"] + 0.5, entrance["y"]
                    want = (cx * scale - 14, cy * scale - 14)
                    stamp = f'<rect x="{want[0]}" y="{want[1]}" width="28" height="28"'
                    assert stamp in overlay, (
                        f"seed {seed}: room #{entrance['room_id']}'s secret entrance is "
                        f"marked, but not on the {wall} wall it was opened in"
                    )
                    found += 1
    assert found > 20, f"expected plenty of secret entrances, found {found}"


def test_a_secret_entrance_does_not_breach_the_wall_in_dungeongen():
    """The "S" has to be the *only* thing marking it, which means the wall
    behind it must still be there.

    An ordinary room exit goes over as a dungeongen `Exit`, which is the one
    thing in its model that opens a wall without needing a room on the far
    side. But an `Exit` is not a neutral breach - its own docstring calls it
    "a skewed inverted U archway extending away from the dungeon", and it
    draws exactly that: a perspective archway sticking out of the wall,
    announcing the way out. On a hidden way in that is the opposite of the
    truth, and it breaks the rule a secret *door* already follows here - the
    wall it hides in has to survive.

    So a secret entrance is handed over as nothing at all. The corridor still
    runs up to the wall (and gets its full length back, since a passage yields
    the cell an exit would have claimed), the wall stays solid, and the
    overlay draws the "S" on it."""
    checked = 0
    for seed in range(30):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                secret = [e for e in island.get("room_exits", []) if e.get("secret")]
                if not secret:
                    continue
                built = bridge.build_dungeongen_dungeon(island)
                # Keyed by room as well as cell, not cell alone: two rooms can
                # share a wall point, so one room's perfectly ordinary opening
                # can sit on the very cell another room's secret entrance does
                # (seed 0: room 53's west and north exits land on room 51's).
                number_of = {rid: room.number for rid, room in built.rooms.items()}
                breached = {
                    (number_of.get(e.room_id), e.x, e.y) for e in built.exits.values()
                }
                plain_cells = {
                    (e["room_id"], bridge._grid(e["x"]), bridge._grid(e["y"]))
                    for e in island["room_exits"] if not e.get("secret")
                }
                for entrance in secret:
                    cell = (entrance["room_id"],
                            bridge._grid(entrance["x"]), bridge._grid(entrance["y"]))
                    if cell in plain_cells:
                        # The room already declares an ordinary opening on this
                        # exact spot, so the breach here is that one's doing and
                        # is legitimate. That a break-in was *also* recorded on a
                        # hole the room already has is its own problem - it is
                        # not secret if you can see it - and it is a layout
                        # question, not a bridge one. 7 of 72 over 60 seeds; see
                        # TODO.md.
                        continue
                    assert cell not in breached, (
                        f"seed {seed}: room #{entrance['room_id']}'s secret entrance is "
                        f"handed to dungeongen as an Exit, which draws an archway through "
                        f"the wall it is supposed to be hidden in"
                    )
                    checked += 1
                # And the ordinary ones still are - this must not have turned
                # into "no room exit ever reaches dungeongen".
                plain = [e for e in island["room_exits"] if not e.get("secret")]
                if plain:
                    assert breached, (
                        f"seed {seed}: no room exit reached dungeongen at all, so the "
                        f"walls of {len(plain)} ordinary openings are drawn solid"
                    )
    assert checked > 20, f"expected plenty of secret entrances, found {checked}"


def test_stairs_get_an_alcove_of_their_own_with_the_steps_in_it():
    """The steps are drawn in a one-cell *room*, not a passage, and that is the
    whole point of it.

    dungeongen draws a wall only along the outline of a region, so two touching
    floor cells inside one region have no wall between them. As a passage, a
    stairs cell that ran alongside another corridor (32% of them do) simply had
    no wall on that flank - measured on seed 72's stairs 23, whose north edge
    carried 6.9% ink where a wall carries ~100%. A room draws its own outline
    whatever region it is in, which is where the three walls come from; with
    the alcove in place that same north edge measures 0% (solid) and only the
    entered side is open, at 15%.

    The way in is the same three pieces dungeongen uses for any room off a
    corridor, and all three are needed: the room, a passage that *ends* in it,
    and a closed door between them carrying that passage's id. A chip on its
    own opens nothing - it is made to sit in a wall two floors already reach -
    which is why an `Exit`, or a door with no passage terminating at it, left
    the alcove sealed on all four sides.

    What is asserted is what can silently go wrong: the alcove exists, it is
    exactly one cell, it has a way in, and the staircase is *in it*. That last
    one is not a given - `_convert_stair` looks for a passage before a room and
    falls back to `passages[0]`, so the steps can end up on an unrelated
    corridor or, on an island with no passages left, be dropped entirely."""
    from dungeongen.constants import CELL_SIZE
    from dungeongen.map.props import StairsProp
    from dungeongen.map.room import Room as _MapRoom

    checked = 0
    for seed in range(20):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                if not island["stairs"] or not bridge.fits_size_limit(island):
                    continue
                built = bridge.build_dungeongen_dungeon(island)
                assert len(built.stairs) == len(island["stairs"]), (
                    f"seed {seed}: {len(island['stairs'])} stairs in the layout but "
                    f"{len(built.stairs)} reached dungeongen"
                )
                alcoves = {
                    (room.x, room.y): room
                    for rid, room in built.rooms.items() if rid.startswith("stair")
                }
                for room in alcoves.values():
                    assert (room.width, room.height) == (1, 1), (
                        f"seed {seed}: a stairs alcove is {room.width}x{room.height}, "
                        f"not the single cell the steps occupy"
                    )
                for rid, room in built.rooms.items():
                    if not rid.startswith("stair"):
                        continue
                    doors = [d for d in built.doors.values() if d.room_id == rid]
                    ways_in = [p for p in built.passages.values() if p.end_room == rid]
                    assert len(ways_in) == 1, (
                        f"seed {seed}: the alcove {rid} has {len(ways_in)} passages "
                        f"ending in it; without exactly one there is no way in"
                    )
                    assert len(doors) == 1, (
                        f"seed {seed}: the alcove {rid} has {len(doors)} doors, so its "
                        f"wall is either unbroken or broken more than once"
                    )
                    assert doors[0].door_type == bridge._DGDoorType.CLOSED, (
                        f"seed {seed}: the alcove {rid}'s door is "
                        f"{doors[0].door_type.name}; an open one merges the regions "
                        f"and takes the alcove's walls with it"
                    )
                    assert doors[0].passage_id == ways_in[0].id, (
                        f"seed {seed}: the alcove {rid}'s door is not tied to the "
                        f"passage that ends there, so it is a chip in a wall nothing "
                        f"reaches and opens nothing"
                    )

                dg_map = bridge._convert_dungeon(built, show_numbers=False)
                bridge._quieten_stair_alcoves(dg_map, built)
                off_x = -built.bounds[0] if built.rooms else 0
                off_y = -built.bounds[1] if built.rooms else 0
                for cell in alcoves:
                    want = (cell[0] + off_x, cell[1] + off_y)
                    drawn = [
                        el for el in dg_map._elements
                        if isinstance(el, _MapRoom)
                        and (round(el.shape.bounds.x / CELL_SIZE),
                             round(el.shape.bounds.y / CELL_SIZE)) == want
                    ]
                    assert drawn, f"seed {seed}: the alcove at {cell} was not converted"
                    assert any(isinstance(prop, StairsProp) for prop in drawn[0].props), (
                        f"seed {seed}: the alcove at {cell} has no staircase in it - "
                        f"the adapter hung it somewhere else, or dropped it"
                    )
                    checked += 1
    assert checked > 50, f"expected plenty of stairs, found {checked}"


def test_the_alcove_door_is_not_drawn_but_still_opens_the_wall():
    """The door has to exist, and no leaf of dungeongen's may be drawn.

    It has to exist because it is what keeps the alcove its own region, and
    so its four walls. Its own drawing must go because no die rolled a door
    there, and because dungeongen draws the leaf in the *middle* of the cell,
    squarely over the staircase - seed 72's stairs 23 show two steps with it
    on and three with it off.

    What replaces it is not nothing: `_quieten_stair_alcoves` puts its own
    `draw` on the instance, which paints the doorway over the wall at
    `Layers.OVERLAY` - see
    `test_the_alcove_is_a_square_with_one_opening_and_nothing_in_it`. This
    test only pins down that alcove doors get a `draw` of their own and that
    ordinary doors keep dungeongen's."""
    from dungeongen.constants import CELL_SIZE
    from dungeongen.map.door import Door as _MapDoor

    silenced = untouched = 0
    for seed in range(20):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                if not island["stairs"] or not bridge.fits_size_limit(island):
                    continue
                built = bridge.build_dungeongen_dungeon(island)
                dg_map = bridge._convert_dungeon(built, show_numbers=False)
                bridge._quieten_stair_alcoves(dg_map, built)
                off_x = -built.bounds[0] if built.rooms else 0
                off_y = -built.bounds[1] if built.rooms else 0
                alcove_cells = {(s.x + off_x, s.y + off_y)
                                for s in built.stairs.values()}
                for element in dg_map._elements:
                    if not isinstance(element, _MapDoor):
                        continue
                    cell = (round(element._x / CELL_SIZE),
                            round(element._y / CELL_SIZE))
                    # Whether the instance carries a draw of its own, not
                    # `el.draw is not type(el).draw` - accessing the class
                    # attribute builds a fresh bound method every time, so
                    # that comparison is true for every door on the map.
                    hidden = "draw" in vars(element)
                    if cell in alcove_cells:
                        assert hidden, (
                            f"seed {seed}: the door at {cell} opens a stairs alcove "
                            f"but is still drawn, over the steps it shares the cell with"
                        )
                        silenced += 1
                    else:
                        # every other door on the map keeps its glyph - this
                        # must not become "no door is ever drawn"
                        assert not hidden, (
                            f"seed {seed}: an ordinary door at {cell} was silenced"
                        )
                        untouched += 1
    assert silenced > 20, f"expected plenty of alcove doors, found {silenced}"
    assert untouched > 20, f"expected plenty of ordinary doors, found {untouched}"


def test_the_alcove_staircase_stays_clear_of_the_cell_edges():
    """No tread may reach the wall, because on one side the wall is the door.

    dungeongen's own staircase is drawn to meet the walls: six treads across
    the full width, the widest sitting exactly on the cell boundary
    (`y = -CELL_SIZE/2`) with a small overhang past it to cover the grid dots.
    In a passage that is right. In the alcove the boundary the treads ascend
    toward *is* the doorway, so the top tread lands across the opening and
    closes it up again - the east edge measured 15% open with the steps
    stripped and 0% with them drawn, i.e. the staircase, not the wall, was
    what sealed it.

    Checked by capturing what the prop draws rather than by rendering: a pixel
    scan of this cell cannot tell a tread from a wall, which is the whole
    problem."""
    import skia
    from dungeongen.constants import CELL_SIZE

    class _Recorder:
        def __init__(self):
            self.lines = []

        def drawLine(self, x0, y0, x1, y1, paint):
            self.lines.append((x0, y0, x1, y1))

    class _Options:
        border_width = 3.0

    class _Map:
        options = _Options()

    stairs = bridge._alcove_stairs_class().at_grid(0, 0)
    stairs._map = _Map()
    canvas = _Recorder()
    from dungeongen.map.enums import Layers
    stairs._draw_content(canvas, None, Layers.PROPS)

    assert len(canvas.lines) >= 4, "expected a staircase, got almost nothing"
    half = CELL_SIZE / 2
    for x0, y0, x1, y1 in canvas.lines:
        for value in (x0, x1):
            assert abs(value) < half, (
                f"a tread reaches {value:.1f} from the cell centre, at or past "
                f"the wall at {half:.1f} - on the door's side that closes the way in"
            )
        for value in (y0, y1):
            assert abs(value) < half, (
                f"a tread sits at {value:.1f}, on the cell boundary at {half:.1f}"
            )
    # and it should still look like stairs: treads of differing lengths,
    # tapering, not a blob of equal bars
    lengths = sorted(abs(x1 - x0) for x0, _, x1, _ in canvas.lines)
    assert lengths[-1] > lengths[0] * 2, (
        f"the treads barely taper ({lengths[0]:.1f} to {lengths[-1]:.1f}); "
        f"the perspective that makes them read as stairs is gone"
    )


def _alcove_edge_ink(island):
    """Ink along each alcove's four cell edges, read off the render.

    A wall is what is actually drawn, so this asks the pixels rather than the
    geometry - the doorway is painted over the wall at `Layers.OVERLAY`, which
    no region shape knows anything about.

    Props go first. `StairsProp` draws its widest tread *on* the cell
    boundary, and a scan counts that as wall; and they have to go *after*
    `_quieten_stair_alcoves`, which puts a missing staircase back.

    Returns {(cell): {"N": inked fraction, ...}} in the map's own cell
    coordinates."""
    import numpy as np
    import skia
    from dungeongen.constants import CELL_SIZE
    from dungeongen.graphics.conversions import grid_to_map

    built = bridge.build_dungeongen_dungeon(island)
    with bridge._region_inflation():
        dg_map = bridge._convert_dungeon(built, show_numbers=False)
        bridge._square_off_doors(dg_map, built, island)
        bridge._quieten_stair_alcoves(dg_map, built)
        for element in dg_map._elements:
            for prop in list(getattr(element, "props", [])):
                element.remove_prop(prop)
        bounds = dg_map.bounds
        pad_x, pad_y = grid_to_map(dg_map.options.map_border_cells,
                                   dg_map.options.map_border_cells)
        width = max(1, round(bounds.width + 2 * pad_x))
        height = max(1, round(bounds.height + 2 * pad_y))
        surface = skia.Surface(width, height)
        dg_map.render(surface.getCanvas())
        pixels = surface.makeImageSnapshot().toarray()

    grey = pixels[:, :, :3].mean(axis=2)
    ox, oy = pad_x - bounds.x, pad_y - bounds.y
    off_x = -built.bounds[0] if built.rooms else 0
    off_y = -built.bounds[1] if built.rooms else 0
    inset = CELL_SIZE * 0.2  # clear of both corners, where the walls meet
    out = {}
    for stair in built.stairs.values():
        gx, gy = stair.x + off_x, stair.y + off_y
        edges = {}
        for side, (dx, dy) in (("N", (0, -1)), ("S", (0, 1)),
                               ("W", (-1, 0)), ("E", (1, 0))):
            if dx:
                x = ox + (gx + (1 if dx > 0 else 0)) * CELL_SIZE
                run = [(x, y) for y in np.arange(oy + gy * CELL_SIZE + inset,
                                                 oy + (gy + 1) * CELL_SIZE - inset)]
            else:
                y = oy + (gy + (1 if dy > 0 else 0)) * CELL_SIZE
                run = [(x, y) for x in np.arange(ox + gx * CELL_SIZE + inset,
                                                 ox + (gx + 1) * CELL_SIZE - inset)]
            dark = sum(1 for x, y in run
                       if 0 <= int(y) < height and 0 <= int(x) < width
                       and grey[int(y), int(x)] < 128)
            edges[side] = dark / len(run)
        out[(gx, gy)] = edges
    return out


def test_the_alcove_is_a_square_with_one_opening_and_nothing_in_it():
    """Three walls, one gap, and no door drawn anywhere near it.

    Measured on the pixels, because that is where the answer is. Two regions
    that meet on a grid line always get a wall between them, and no floor chip
    changes that - whatever either region owns past the line is simply
    outlined too. Before this, all 138 alcoves over 30 seeds were sealed on
    all four sides in region terms, and the only thing that read as a doorway
    was the outline of the chip we handed over, sticking out into the corridor
    like a little closed door.

    So the gap is painted rather than built, the way dungeongen's own door
    glyph is: `Door.draw` runs at `Layers.OVERLAY`, after `Map.render` has
    stroked the border, and fills in `room_color` straight over it. Ours fills
    and does not stroke.

    Over 20 seeds this ran to 112 alcoves, every one of them a square with one
    clear side, and that side the one its door faces. Against the chip it was
    0 of 112 - the doorway side came out between a third and two thirds inked,
    once fully."""
    away = {"north": "S", "south": "N", "east": "W", "west": "E"}
    checked = 0
    welded = []
    for seed in range(20):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                if not island["stairs"] or not bridge.fits_size_limit(island):
                    continue
                built = bridge.build_dungeongen_dungeon(island)
                off_x = -built.bounds[0] if built.rooms else 0
                off_y = -built.bounds[1] if built.rooms else 0
                facing = {(door.x + off_x, door.y + off_y): away[door.direction]
                          for door in built.doors.values()}
                alcoves = {(room.x + off_x, room.y + off_y)
                           for room in built.rooms.values()
                           if room.id.startswith("stair")}
                for cell, edges in _alcove_edge_ink(island).items():
                    # a stair whose cell fell inside a room has no alcove at
                    # all, and nothing here to say about it
                    if cell not in alcoves or cell not in facing:
                        continue
                    clear = sorted(s for s, v in edges.items() if v < 0.1)
                    walled = sorted(s for s, v in edges.items() if v > 0.9)
                    shown = {k: round(v, 2) for k, v in edges.items()}
                    assert clear == [facing[cell]], (
                        f"seed {seed}: the alcove at {cell} should open only to "
                        f"{facing[cell]}, the side its door faces, and opens "
                        f"{clear or 'nowhere'} instead: {shown}"
                    )
                    if len(walled) != 3:
                        welded.append((seed, cell, shown))
                    checked += 1
    assert checked > 40, f"expected plenty of alcoves, found {checked}"
    # Three solid walls is the rule, and a handful come out with a gap in a
    # second one: the alcove's cell is welded to a corridor running alongside,
    # so no wall is drawn between them. Measured over 40 seeds it is 2 of 168
    # here and 1 of 174 before any of this, so it is not new - it is rare
    # enough that a 20-seed window used to miss it. See TODO.md.
    assert len(welded) <= 2, (
        f"{len(welded)} of {checked} alcoves have a second side open, more than the "
        f"known residue: {welded[:3]}"
    )


def test_the_alcove_has_no_corner_decoration():
    """A one-cell room has no room for the corner marks a room normally gets.

    `Room.draw` brackets its four corners: `CORNER_SIZE` long (0.35 of a cell)
    set `CORNER_INSET` in from the edges (0.12). Across four or five cells
    that reads as decoration. In one cell the bracket lands 7.7px from a wall
    whose stroke already occupies 4.6 of them, and the two run together into a
    single fat band - measured along the alcove's north wall, the wall itself
    is 9.2px centred exactly on the grid line, the same as any room's, with
    the bracket as a second band beside it and the pair merging to 20px
    towards the corner. It is what makes the alcove look swollen where it
    meets the corridor.

    Only the brackets go: the room still draws its walls, and still draws the
    staircase it holds."""
    ordinary = alcoves = 0
    for seed in range(15):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                if not island["stairs"] or not bridge.fits_size_limit(island):
                    continue
                built = bridge.build_dungeongen_dungeon(island)
                try:
                    dg_map = bridge._convert_dungeon(built, show_numbers=False)
                except Exception:
                    continue
                bridge._quieten_stair_alcoves(dg_map, built)
                off_x = -built.bounds[0] if built.rooms else 0
                off_y = -built.bounds[1] if built.rooms else 0
                cells = {(s.x + off_x, s.y + off_y) for s in built.stairs.values()}
                for element in dg_map._elements:
                    cell = bridge._alcove_cell_of(element, cells)
                    silenced = "draw_corners" in element.__dict__
                    if cell is not None:
                        assert silenced, (
                            f"seed {seed}: the alcove at {cell} still draws its corner "
                            f"brackets, which merge with its own wall at this size"
                        )
                        alcoves += 1
                    elif hasattr(element, "draw_corners"):
                        assert not silenced, (
                            f"seed {seed}: an ordinary room lost its corner marks"
                        )
                        ordinary += 1
    assert alcoves > 30, f"expected plenty of alcoves, found {alcoves}"
    assert ordinary > 30, f"expected plenty of ordinary rooms, found {ordinary}"


def test_without_region_inflation_an_alcove_measures_like_a_closed_square():
    """With the inflation off, asking a region where it ends means something.

    dungeongen inflates every region by `REGION_INFLATE` (1.6px) before
    drawing, so "does this region reach past that wall" answered yes on all
    four sides of every alcove - 42 of 43 over eight seeds. `_region_inflation`
    turns it off, and with it off the answer is the true one: an alcove is its
    own region and ends at all four of its walls. The way in is not a gap in
    the region, it is paint laid over the wall afterwards - see
    `test_the_alcove_is_a_square_with_one_opening_and_nothing_in_it`.

    So this fails in both directions: with the inflation left on, every side
    reads open.

    Also checks the constant is put back. It is a module global in someone
    else's library, and it has to stay swapped for the whole render because
    `_make_regions` runs inside `Map.render` - patching around the conversion
    alone does nothing, which is how this setting first looked inert."""
    import dungeongen.map.map as dg_map_module
    from dungeongen.constants import CELL_SIZE
    from dungeongen.map.room import Room as _MapRoom

    before = dg_map_module.REGION_INFLATE
    checked = 0
    for seed in range(8):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                if not island["stairs"] or not bridge.fits_size_limit(island):
                    continue
                with bridge._region_inflation():
                    assert dg_map_module.REGION_INFLATE == 0.0, (
                        "the override is not in effect during the render"
                    )
                    built = bridge.build_dungeongen_dungeon(island)
                    try:
                        dg_map = bridge._convert_dungeon(built, show_numbers=False)
                    except Exception:
                        continue
                    bridge._quieten_stair_alcoves(dg_map, built)
                    off_x = -built.bounds[0] if built.rooms else 0
                    off_y = -built.bounds[1] if built.rooms else 0
                    alcoves = {(room.x + off_x, room.y + off_y)
                               for room in built.rooms.values()
                               if room.id.startswith("stair")}
                    # By the alcove's own Room element, not by "the first
                    # region containing this point": the passage that ends
                    # there covers the same cell, and its region gets picked
                    # about half the time.
                    holder = {}
                    for region in dg_map._make_regions():
                        for element in region.elements:
                            holder[id(element)] = region
                    for element in dg_map._elements:
                        if not isinstance(element, _MapRoom):
                            continue
                        eb = element.shape.bounds
                        cell = (round(eb.x / CELL_SIZE), round(eb.y / CELL_SIZE))
                        if cell not in alcoves or id(element) not in holder:
                            continue
                        cx = (cell[0] + 0.5) * CELL_SIZE
                        cy = (cell[1] + 0.5) * CELL_SIZE
                        shape = holder[id(element)].shape
                        step = CELL_SIZE * 0.55
                        past = sorted(
                            name for name, (dx, dy) in
                            (("N", (0, -1)), ("S", (0, 1)),
                             ("W", (-1, 0)), ("E", (1, 0)))
                            if shape.contains(cx + dx * step, cy + dy * step)
                        )
                        assert not past, (
                            f"seed {seed}: the alcove at {cell} reaches past its "
                            f"{', '.join(past)} wall; with the inflation off it "
                            f"should end at all four"
                        )
                        checked += 1
        assert dg_map_module.REGION_INFLATE == before, (
            "the inflation was left swapped after the render"
        )
    assert checked > 20, f"expected plenty of alcoves, found {checked}"


class _RecordingCanvas:
    """A canvas that only remembers the rectangles drawn on it.

    Enough for `Door.draw`, which draws one `Rectangle` and nothing else, and
    it keeps the door's glyph measurable without rendering a page."""

    def __init__(self):
        self.rects = []

    def drawRect(self, rect, paint):
        self.rects.append((rect.x(), rect.y(), rect.width(), rect.height()))

    def drawRRect(self, rrect, paint):
        rect = rrect.rect()
        self.rects.append((rect.x(), rect.y(), rect.width(), rect.height()))

    def drawPath(self, path, paint):
        # dungeongen's own `Exit` archway comes through here. Counted like the
        # rest so a test that expects nothing fails on the assertion rather
        # than on a missing method.
        rect = path.computeTightBounds()
        self.rects.append((rect.x(), rect.y(), rect.width(), rect.height()))


def _doors_on_walls(island):
    """Every *closed* door of this island that sits on a wall, with the wall.

    Open ones are left out on purpose: an open door is a hole rather than a
    glyph, and has its own test below.

    Yields (element, cell, side, far, secret) after the real drawing passes
    have run, in the order `render_island_svg` runs them."""
    from dungeongen.constants import CELL_SIZE
    from dungeongen.map.door import Door as _MapDoor

    built = bridge.build_dungeongen_dungeon(island)
    with bridge._region_inflation():
        dg_map = bridge._convert_dungeon(built, show_numbers=False)
        bridge._square_off_doors(dg_map, built, island)
        bridge._quieten_stair_alcoves(dg_map, built)
        off_x = -built.bounds[0] if built.rooms else 0
        off_y = -built.bounds[1] if built.rooms else 0
        secret_cells = {
            (cx + off_x, cy + off_y)
            for door in island.get("doors", []) if door.get("secret")
            for cx, cy in bridge.door_cells(door)
        }
        # A stairs alcove's door is not one of these. `_quieten_stair_alcoves`
        # takes it over afterwards and paints the doorway itself, on the side
        # the alcove opens through - see the alcove's own tests.
        alcoves = {(stair.x + off_x, stair.y + off_y)
                   for stair in built.stairs.values()}
        for element in dg_map._elements:
            if not isinstance(element, _MapDoor):
                continue
            cell = (round(element._x / CELL_SIZE), round(element._y / CELL_SIZE))
            if cell in alcoves or element.open:
                continue
            placed = bridge._door_sides(element, cell, CELL_SIZE)
            if placed is None or placed[0] != "wall":
                continue
            yield element, cell, placed[1], placed[2], cell in secret_cells


def test_a_doors_chip_stays_on_its_own_side_of_the_wall():
    """Neither half of a door may reach back across the wall it sits in.

    dungeongen hands each side a chip that runs from the middle of the door's
    *own cell* out to one of its walls. That is right where a door has a cell
    to itself; ours sit on the wall and take no cell, so the chip handed to
    the element across the wall reached half a cell into a region that is not
    its own - and a region outlines whatever it owns, so it came out as a
    rounded box hanging off the wall with the leaf floating in the middle of
    it. 95 of 95 closed doors on walls over 12 seeds, every one reaching the
    full 0.50 of a cell.

    Measured on the shapes rather than the render: dungeongen's decoration is
    not reproducible from one process to the next (see LESSONS.md), but its
    geometry is."""
    from dungeongen.constants import CELL_SIZE

    checked = 0
    for seed in range(20):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                if not bridge.fits_size_limit(island):
                    continue
                for element, cell, side, far, _ in _doors_on_walls(island):
                    bounds = element.get_side_shape(far).bounds
                    x0, y0 = cell[0] * CELL_SIZE, cell[1] * CELL_SIZE
                    back = {
                        "E": (x0 + CELL_SIZE) - bounds.x,
                        "W": (bounds.x + bounds.width) - x0,
                        "S": (y0 + CELL_SIZE) - bounds.y,
                        "N": (bounds.y + bounds.height) - y0,
                    }[side]
                    assert back <= 0.01 * CELL_SIZE, (
                        f"seed {seed}: the door at {cell} hands the element past its "
                        f"{side} wall a chip reaching {back / CELL_SIZE:.2f} of a cell "
                        f"back across it - that is the box that gets outlined"
                    )
                    checked += 1
    assert checked > 40, f"expected plenty of doors on walls, found {checked}"


def test_a_doors_glyph_is_drawn_on_the_wall_it_sits_in():
    """And centred on it, not half a cell away.

    dungeongen draws the leaf in the middle of the door's own cell, which for
    a door of ours is the middle of the corridor beside the wall. Measured
    over the same 12 seeds: every one of 95 leaves sat 0.50 of a cell off, and
    all 93 that are not secret are now on the line."""
    from dungeongen.constants import CELL_SIZE
    from dungeongen.map.enums import Layers

    checked = 0
    for seed in range(20):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                if not bridge.fits_size_limit(island):
                    continue
                for element, cell, side, _far, secret in _doors_on_walls(island):
                    if secret:
                        continue
                    canvas = _RecordingCanvas()
                    element.draw(canvas, Layers.OVERLAY)
                    assert canvas.rects, (
                        f"seed {seed}: the door at {cell} draws nothing at all"
                    )
                    x, y, w, h = canvas.rects[0]
                    along_y = side in ("N", "S")
                    middle = (y + h / 2) if along_y else (x + w / 2)
                    wall = {"N": cell[1], "S": cell[1] + 1,
                            "W": cell[0], "E": cell[0] + 1}[side] * CELL_SIZE
                    assert abs(middle - wall) <= 0.01 * CELL_SIZE, (
                        f"seed {seed}: the door at {cell} draws its leaf "
                        f"{abs(middle - wall) / CELL_SIZE:.2f} of a cell off the "
                        f"{side} wall it sits in"
                    )
                    checked += 1
    assert checked > 40, f"expected plenty of doors on walls, found {checked}"


def test_a_secret_door_has_no_door_drawn_in_it():
    """The whole point of a secret door is that the wall looks untouched.

    It goes over to dungeongen *closed* so the wall survives - handing over
    its real type folds to OPEN in the webview adapter, which is a hole, not a
    glyph (`_door_kind`). But closed still means dungeongen draws a door leaf
    on that wall, so a secret door was rendering with a door plainly drawn in
    it, and the overlay's "S" went on top of that. Nothing is drawn now."""
    from dungeongen.map.enums import Layers

    checked = 0
    for seed in range(30):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                if not bridge.fits_size_limit(island):
                    continue
                if not any(door.get("secret") for door in island["doors"]):
                    continue
                for element, cell, _side, _far, secret in _doors_on_walls(island):
                    if not secret:
                        continue
                    canvas = _RecordingCanvas()
                    element.draw(canvas, Layers.OVERLAY)
                    assert not canvas.rects, (
                        f"seed {seed}: the secret door at {cell} draws a door glyph "
                        f"in the wall it is supposed to be hidden in"
                    )
                    checked += 1
    assert checked > 3, f"expected a few secret doors, found {checked}"


def test_an_open_door_is_a_hole_and_draws_nothing():
    """dungeongen's open door is not a different glyph, it is the absence of
    one: `Map._trace_connected_region` walks straight through it, so the two
    sides are one region and there is no wall between them at all.

    Worth a test of its own because the first version of `_square_off_doors`
    dropped the `if not self._open` guard that `Door.draw` opens with, and so
    drew a door across every one of them - including the join between seed
    72's passages 3 and 8, where nothing had ever been drawn."""
    from dungeongen.constants import CELL_SIZE
    from dungeongen.map.door import Door as _MapDoor
    from dungeongen.map.enums import Layers

    checked = 0
    for seed in range(8):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                if not bridge.fits_size_limit(island):
                    continue
                built = bridge.build_dungeongen_dungeon(island)
                with bridge._region_inflation():
                    dg_map = bridge._convert_dungeon(built, show_numbers=False)
                    bridge._square_off_doors(dg_map, built, island)
                    bridge._quieten_stair_alcoves(dg_map, built)
                    for element in dg_map._elements:
                        if not isinstance(element, _MapDoor) or not element.open:
                            continue
                        canvas = _RecordingCanvas()
                        element.draw(canvas, Layers.OVERLAY)
                        cell = (round(element._x / CELL_SIZE),
                                round(element._y / CELL_SIZE))
                        assert not canvas.rects, (
                            f"seed {seed}: the open door at {cell} draws a door glyph, "
                            f"on a join where there is no wall"
                        )
                        checked += 1
    assert checked > 20, f"expected plenty of open doors, found {checked}"


def _room_exit_drawings(island):
    """What each of this island's room-exit archways draws, after the passes.

    Yields (exit_spec, side, cell, dug_beyond, has_door, calls) where `calls`
    counts the paint operations the element performs at `Layers.OVERLAY` - a
    painted gap fills once, a door fills and strokes, an untouched wall does
    nothing."""
    from dungeongen.constants import CELL_SIZE
    from dungeongen.map.exit import Exit as _MapExit
    from dungeongen.map.enums import Layers

    built = bridge.build_dungeongen_dungeon(island)
    if not built.exits:
        return
    door_at = {(door["x1"], door["y1"]): door for door in island["doors"]}
    with bridge._region_inflation():
        dg_map = bridge._convert_dungeon(built, show_numbers=False)
        bridge._square_off_doors(dg_map, built, island)
        bridge._square_off_room_exits(dg_map, built, island)
        off_x = -built.bounds[0] if built.rooms else 0
        off_y = -built.bounds[1] if built.rooms else 0
        elements = [el for el in dg_map._elements if isinstance(el, _MapExit)]
        for spec, element in zip(built.exits.values(), elements):
            side = {"north": "N", "south": "S", "east": "E", "west": "W"}[spec.direction]
            cell = (spec.x - (1 if side == "E" else 0) + off_x,
                    spec.y - (1 if side == "S" else 0) + off_y)
            step = {"N": (0, -1), "S": (0, 1), "W": (-1, 0), "E": (1, 0)}[side]
            beyond = (cell[0] + step[0], cell[1] + step[1])
            canvas = _RecordingCanvas()
            element.draw(canvas, Layers.OVERLAY)
            # A stairs alcove gets its one opening from
            # `_quieten_stair_alcoves` and must not be given a second one, so
            # an exit backing onto one counts as leading nowhere here.
            alcoves = {(stair.x + off_x, stair.y + off_y)
                       for stair in built.stairs.values()}
            yield (spec, side, cell,
                   dg_map.is_occupied(*beyond) and beyond not in alcoves,
                   door_at.get((spec.x, spec.y)), len(canvas.rects))


def test_a_room_exit_is_drawn_as_what_the_roll_said_not_as_an_archway():
    """dungeongen's `Exit` draws "a skewed inverted U archway extending away
    from the dungeon" - a black blob in perspective, standing inside the room
    against the wall - and it opens nothing: the wall behind it stays solid.

    Seed 72's room 6 opens west onto passage 13 with, by its own roll, "an
    open way through, no door", and came out with that blob drawn inside the
    room and an unbroken wall behind it.

    What is drawn now is what the roll said: a door where our layout put a
    door node at that exit, a painted gap where it did not, and nothing at all
    where the cell beyond is not dug - there the branch is not on the map and
    the wall is the truth. Over 20 seeds: 68 doors, 213 gaps, 8 left whole."""
    doors = gaps = whole = 0
    for seed in range(20):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                if not bridge.fits_size_limit(island):
                    continue
                for spec, side, cell, dug, door, calls in _room_exit_drawings(island):
                    if not dug or (door is not None and door["secret"]):
                        assert calls == 0, (
                            f"seed {seed}: the exit at {cell} {side} opens onto rock, "
                            f"onto a stairs alcove, or hides a secret door, and still "
                            f"draws {calls} times"
                        )
                        whole += 1
                    elif door is not None:
                        assert calls == 2, (
                            f"seed {seed}: the exit at {cell} {side} has a door behind it, "
                            f"so it should be filled and stroked, not drawn {calls} times"
                        )
                        doors += 1
                    else:
                        assert calls == 1, (
                            f"seed {seed}: the exit at {cell} {side} is a plain opening, "
                            f"so it should be a filled gap and nothing else, not {calls}"
                        )
                        gaps += 1
    assert doors > 30 and gaps > 100 and whole > 3, (
        f"doors {doors}, gaps {gaps}, whole {whole}"
    )


def test_a_room_exit_contributes_no_chip_of_its_own():
    """An `Exit`'s chip cannot open anything - nothing can, two regions that
    meet on a grid line are both outlined along it - and left in place it is
    one more shape to be outlined somewhere it is not wanted. The opening is
    painted instead, so the chip goes."""
    checked = 0
    for seed in range(12):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                if not bridge.fits_size_limit(island):
                    continue
                built = bridge.build_dungeongen_dungeon(island)
                if not built.exits:
                    continue
                from dungeongen.map.exit import Exit as _MapExit
                with bridge._region_inflation():
                    dg_map = bridge._convert_dungeon(built, show_numbers=False)
                    bridge._square_off_room_exits(dg_map, built, island)
                    for element in dg_map._elements:
                        if not isinstance(element, _MapExit):
                            continue
                        assert "get_side_shape" in vars(element), (
                            f"seed {seed}: a room exit still has dungeongen's own chip"
                        )
                        assert not element.get_side_shape(None).includes, (
                            f"seed {seed}: a room exit still hands over a chip"
                        )
                        checked += 1
    assert checked > 40, f"expected plenty of room exits, found {checked}"


def test_a_door_the_bridge_draws_is_not_marked_again_by_the_overlay():
    """The overlay marks with a rust bar every door dungeongen leaves without
    a glyph. Since the bridge started drawing the doors on a room's own
    openings - the ones no room-to-room link covers - that set is smaller, and
    it had no way of knowing: seed 72's door 54 came out marked twice, our
    rectangle on room 36's wall and a rust bar a cell away inside passage 71.

    `_square_off_room_exits` records what it drew on the island, and this
    checks the two do not overlap by reading the bars back out of the overlay
    it produces."""
    import re
    from dungeon_simulator.render_map import _dungeongen_overlay_for_island

    checked = 0
    for seed in range(12):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                if not bridge.fits_size_limit(island):
                    continue
                _svg, off_x, off_y, scale, _w, _h = bridge.render_island_svg(island)
                drawn = island.get("_doors_drawn") or set()
                if not drawn:
                    continue
                overlay = _dungeongen_overlay_for_island(island, off_x, off_y, scale)
                bars = [
                    ((float(x1) + float(x2)) / 2, (float(y1) + float(y2)) / 2)
                    for x1, y1, x2, y2 in re.findall(
                        r'<line x1="([-\d.]+)" y1="([-\d.]+)" '
                        r'x2="([-\d.]+)" y2="([-\d.]+)" stroke="[^"]*" stroke-width="5">',
                        overlay)
                ]
                for door_x, door_y in drawn:
                    px = off_x + door_x * scale
                    py = off_y + door_y * scale
                    for bar_x, bar_y in bars:
                        assert abs(bar_x - px) > scale or abs(bar_y - py) > scale, (
                            f"seed {seed}: the door at {(door_x, door_y)} is drawn by the "
                            f"bridge and marked again by the overlay"
                        )
                    checked += 1
    assert checked > 15, f"expected plenty of doors drawn on room exits, found {checked}"
