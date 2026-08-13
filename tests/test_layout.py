import math

from dungeon_simulator.generator import DungeonGenerator
from dungeon_simulator.layout import compute_layout
from dungeon_simulator.render_map import _level_payload, render_map_section


def _bbox(island):
    xs, ys = [], []
    for room in island["rooms"]:
        for cx, cy in room["corners"]:
            xs.append(cx); ys.append(cy)
    for corridor in island["corridors"]:
        for cx, cy in corridor["points"]:
            xs.append(cx); ys.append(cy)
    for group in ("stairs", "portals", "caps"):
        for item in island[group]:
            xs.append(item["x"]); ys.append(item["y"])
    ox, oy = island["origin"]
    xs.append(ox); ys.append(oy)
    return min(xs), max(xs)


_BRANCH_STOPS = "il ramo si interrompe qui"


def test_every_room_is_placed_or_accounted_for_and_no_negative_bbox_after_translation():
    """A room may legitimately not reach the map: it may not fit anywhere
    along its own entry wall, or the wall it hangs off may have no cell left
    for another 10ft opening. Either way the branch stops there and says so.
    What must never happen is a room quietly vanishing - every room the
    generator rolled is either drawn, or carries the note itself, or sits
    behind a node that does.

    Keyed on the note's shared closing phrase rather than on either specific
    wording, and checked on every node rather than only on rooms: a branch can
    be cut at a passage or a door, and the rooms beyond it are then never
    walked at all.

    The log is the source of truth here, not the map's own dead-end markers:
    a marker that would land inside a room's floor is cleaned up as noise
    (_drop_caps_inside_rooms), so it cannot be relied on to account for the
    room. The note on the node is what the reader actually gets."""
    for seed in range(60):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        layout = compute_layout(dungeon)
        placed = {
            room["id"] for islands in layout.values() for island in islands
            for room in island["rooms"]
        }
        accounted: set[int] = set()

        def mark(node, cut):
            stops = any(_BRANCH_STOPS in line for line in node.lines)
            if node.kind == "room" and (cut or stops):
                accounted.add(node.id)
            for child in node.children:
                mark(child, cut or stops)

        mark(dungeon.root, False)
        assert not (placed & accounted), (
            f"seed {seed}: a room cannot be both drawn and reported as not drawn"
        )
        rooms_in_tree = {n.id for n in dungeon.all_nodes() if n.kind == "room"}
        assert len(rooms_in_tree) == dungeon.room_count
        assert rooms_in_tree == placed | accounted, (
            f"seed {seed}: rooms unaccounted for: {sorted(rooms_in_tree - placed - accounted)}"
        )

        for islands in layout.values():
            for island in islands:
                minx, _ = _bbox(island)
                assert minx >= -0.01  # translated so nothing sits left of the level's own origin


def test_islands_on_the_same_level_do_not_overlap():
    # A seed with multiple disconnected islands on one level (verified offline).
    dungeon = DungeonGenerator(seed=75).generate()
    layout = compute_layout(dungeon)
    for islands in layout.values():
        if len(islands) < 2:
            continue
        spans = sorted(_bbox(isl) for isl in islands)
        for (_, prev_max), (next_min, _) in zip(spans, spans[1:]):
            assert next_min >= prev_max  # islands are laid out left-to-right, never overlapping


def _room_rect(room):
    xs = [c[0] for c in room["corners"]]
    ys = [c[1] for c in room["corners"]]
    return min(xs), min(ys), max(xs), max(ys)


def _rects_overlap(a, b, margin=-0.01):
    return not (a[2] + margin <= b[0] or b[2] + margin <= a[0]
                or a[3] + margin <= b[1] or b[3] + margin <= a[1])


def test_rooms_in_the_same_island_never_overlap():
    for seed in range(80):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        layout = compute_layout(dungeon)
        for islands in layout.values():
            for island in islands:
                rects = [_room_rect(r) for r in island["rooms"]]
                for i, a in enumerate(rects):
                    for b in rects[i + 1:]:
                        assert not _rects_overlap(a, b), f"seed {seed}: two rooms overlap"


def test_door_stubs_never_have_negative_length():
    for seed in range(40):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        layout = compute_layout(dungeon)
        for level, islands in layout.items():
            for island in islands:
                payload = _level_payload(level, [island])
                for door in payload["doors"]:
                    total = math.hypot(door["x2"] - door["x1"], door["y2"] - door["y1"])
                    stub1 = math.hypot(door["gx1"] - door["x1"], door["gy1"] - door["y1"])
                    stub2 = math.hypot(door["x2"] - door["gx2"], door["y2"] - door["gy2"])
                    assert stub1 <= total / 2 + 1e-6
                    assert stub2 <= total / 2 + 1e-6


def test_no_dead_end_or_edge_cap_lands_inside_a_room():
    for seed in range(80):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        layout = compute_layout(dungeon)
        for islands in layout.values():
            for island in islands:
                rects = [_room_rect(r) for r in island["rooms"]]
                for cap in island["caps"]:
                    for rx0, ry0, rx1, ry1 in rects:
                        assert not (rx0 <= cap["x"] <= rx1 and ry0 <= cap["y"] <= ry1), (
                            f"seed {seed}: a '{cap['kind']}' marker landed inside a room's floor"
                        )


def test_corridor_points_have_no_consecutive_duplicates():
    for seed in range(80):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        layout = compute_layout(dungeon)
        for islands in layout.values():
            for island in islands:
                for corridor in island["corridors"]:
                    points = corridor["points"]
                    for a, b in zip(points, points[1:]):
                        assert a != b, f"seed {seed}: corridor {corridor['id']} has a zero-length segment"


def test_root_island_is_flagged_as_entrance():
    dungeon = DungeonGenerator(seed=3).generate()
    layout = compute_layout(dungeon)
    root_islands = layout[dungeon.root.level]
    assert any(isl["is_entrance"] for isl in root_islands)


def _first_room_node(node):
    if node.kind == "room":
        return node
    for child in node.children:
        found = _first_room_node(child)
        if found is not None:
            return found
    return None


def test_render_map_section_escapes_content_and_has_svg():
    dungeon = DungeonGenerator(seed=81).generate()
    room = _first_room_node(dungeon.root)
    assert room is not None
    room.lines.append('</script><script>alert(1)</script>')
    html = render_map_section(dungeon)
    assert "<svg" in html
    # Room/corridor/door/stairs content only ever reaches the page as JSON
    # fed through `textContent`, never as raw HTML - so injecting a
    # "</script>" must not be able to close our own data/vendor/render
    # <script> tags early. There are exactly 3 legitimate closing tags.
    assert html.count("</script>") == 3


def test_render_map_section_never_crashes_across_many_seeds():
    for seed in range(150):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=15).generate()
        html = render_map_section(dungeon)
        assert isinstance(html, str) and html
