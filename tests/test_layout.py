from dungeon_simulator.generator import DungeonGenerator
from dungeon_simulator.layout import compute_layout
from dungeon_simulator.render_map import render_map_section


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


def test_compute_layout_has_every_room_and_no_negative_bbox_after_translation():
    for seed in range(60):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        layout = compute_layout(dungeon)
        total_rooms = sum(len(isl["rooms"]) for islands in layout.values() for isl in islands)
        assert total_rooms == dungeon.room_count
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


def test_root_island_is_flagged_as_entrance():
    dungeon = DungeonGenerator(seed=3).generate()
    layout = compute_layout(dungeon)
    root_islands = layout[dungeon.root.level]
    assert any(isl["is_entrance"] for isl in root_islands)


def test_render_map_section_escapes_content_and_has_svg():
    dungeon = DungeonGenerator(seed=81).generate()
    dungeon.root.lines.append('<script>alert(1)</script>')
    html = render_map_section(dungeon)
    assert "<svg" in html
    assert "<script>alert" not in html


def test_render_map_section_never_crashes_across_many_seeds():
    for seed in range(150):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=15).generate()
        html = render_map_section(dungeon)
        assert isinstance(html, str) and html
