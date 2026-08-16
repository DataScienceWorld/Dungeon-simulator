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
_NOT_DRAWN = "non e' disegnata sulla mappa"


def _says_it_is_not_drawn(node) -> bool:
    return any(_BRANCH_STOPS in line or _NOT_DRAWN in line for line in node.lines)


def test_every_room_is_placed_or_says_so_itself_and_no_negative_bbox_after_translation():
    """A room may legitimately not reach the map: it may not fit anywhere
    along its own entry wall, or the wall it hangs off may have no cell left
    for another 10ft opening, or it may sit behind something that hit one of
    those. In every one of those cases the room's *own* log entry has to say
    so.

    Deliberately stronger than "somewhere up the tree there's a note": a
    reader looks up one room, and should learn from that entry alone whether
    it is on the map. Requiring it here is what keeps _mark_branch_not_drawn
    honest - without it 28 rooms across this sample were explained only by an
    ancestor's note.

    The log is the source of truth, not the map's own dead-end markers: a
    marker that would land inside a room's floor is cleaned up as noise
    (_drop_caps_inside_rooms), so it cannot account for anything."""
    for seed in range(60):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        layout = compute_layout(dungeon)
        placed = {
            room["id"] for islands in layout.values() for island in islands
            for room in island["rooms"]
        }
        rooms = [n for n in dungeon.all_nodes() if n.kind == "room"]
        assert len({n.id for n in rooms}) == dungeon.room_count

        for room in rooms:
            if room.id in placed:
                assert not _says_it_is_not_drawn(room), (
                    f"seed {seed}: room {room.id} is drawn but its entry says it isn't"
                )
            else:
                assert _says_it_is_not_drawn(room), (
                    f"seed {seed}: room {room.id} never reaches the map and its own "
                    f"entry never says so"
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


def test_no_corridor_or_link_segment_runs_diagonally():
    """Every segment has to be axis-aligned. A diagonal is not a corridor:
    dungeongen routes cell by cell and cannot follow one, and the fallback
    renderer draws it as a line cutting across whatever is in between.

    They used to come from a "stretch our last point to meet the child" rule,
    written for a time when a room that didn't fit was pushed along until it
    did. Rooms are not pushed any more, and the only node kind that ever
    answers with a position other than the one it was handed is a passage,
    which reports the far end of everything it walked - so the rule only ever
    fired on the one case where it was wrong, dragging a trunk's last point
    across the map.

    Verified to fail on the state before that removal: 34 diagonal segments
    over this same sweep, and not only the `stretch*` corridors it created -
    trunk corridors were bent too, because the rule rewrote their last point
    in place."""
    checked = 0
    for seed in range(60):
        for max_depth in (None, 5):
            kwargs = {"seed": seed, "limitless_room_cap": 20}
            if max_depth is not None:
                kwargs["max_depth"] = max_depth
            dungeon = DungeonGenerator(**kwargs).generate()
            layout = compute_layout(dungeon)
            for islands in layout.values():
                for island in islands:
                    for route in [*island["corridors"], *island.get("links", [])]:
                        points = route["points"]
                        for a, b in zip(points, points[1:]):
                            checked += 1
                            assert a[0] == b[0] or a[1] == b[1], (
                                f"seed {seed} (max_depth={max_depth}): "
                                f"{route['id']} runs diagonally from {a} to {b}"
                            )
    assert checked > 4000  # the sweep really did walk the map, not an empty layout


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
    """Log text reaches the page two different ways and neither may let it
    become markup: through dungeongen's overlay it is escaped into SVG
    <title> elements, and through the RoughJS fallback it is JSON fed to
    `textContent`. A "</script>" in a room's log line must not be able to
    close one of our own script tags early either way.

    Asserted as "the payload never comes back through intact" rather than by
    counting closing tags. The old test pinned that count at exactly 3, which
    stopped meaning anything the moment every level started rendering through
    dungeongen: there were then no script tags at all, and a count of 0 would
    have satisfied a test whose whole point was that the injected one is
    absent. Counting `<script` openings is no good either - the escaped
    payload legitimately contains one, inert, inside a JSON string."""
    payload = '</script><script>alert(1)</script>'
    for seed in (81, 7):
        dungeon = DungeonGenerator(seed=seed).generate()
        room = _first_room_node(dungeon.root)
        assert room is not None
        room.lines.append(payload)
        html = render_map_section(dungeon)
        assert "<svg" in html
        assert payload not in html, (
            f"seed {seed}: the injected payload came back verbatim, so its "
            f"'</script>' can close whatever block it landed in"
        )
        assert "alert(1)" in html, (
            f"seed {seed}: the log text vanished entirely - escaped is the point, "
            f"dropped is a different bug"
        )


def test_render_map_section_escapes_content_in_the_roughjs_fallback(monkeypatch):
    """The same, pinned on the fallback specifically. It is the path that
    embeds log text in a <script> block, so it is the one an injected
    "</script>" could actually break out of - and it is now rare enough
    (levels only fall back when an island is too big for dungeongen) that the
    test above can no longer be relied on to exercise it."""
    from dungeon_simulator import dungeongen_bridge as bridge

    monkeypatch.setattr(bridge, "_IMPORT_ERROR", RuntimeError("forced off for this test"))
    dungeon = DungeonGenerator(seed=81).generate()
    room = _first_room_node(dungeon.root)
    assert room is not None
    room.lines.append('</script><script>alert(1)</script>')
    html = render_map_section(dungeon)
    assert "<script" in html  # the fallback really is the path under test
    assert '</script><script>alert(1)</script>' not in html
    # JSON-escaped, so the sequence that would terminate our block is broken up
    assert r"<\/script>" in html
    assert "alert(1)" in html


def test_render_map_section_never_crashes_across_many_seeds():
    for seed in range(150):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=15).generate()
        html = render_map_section(dungeon)
        assert isinstance(html, str) and html


def _room_rects(island):
    rects = {}
    for room in island["rooms"]:
        xs = [c[0] for c in room["corners"]]
        ys = [c[1] for c in room["corners"]]
        rects[room["id"]] = (min(xs), min(ys), max(xs), max(ys))
    return rects


def _on_boundary(point, rect, tol=1e-6):
    x, y = point
    x0, y0, x1, y1 = rect
    inside = x0 - tol <= x <= x1 + tol and y0 - tol <= y <= y1 + tol
    on_edge = (abs(x - x0) < tol or abs(x - x1) < tol
               or abs(y - y0) < tol or abs(y - y1) < tol)
    return inside and on_edge


def test_every_link_starts_and_ends_on_its_own_rooms_wall():
    """A link says "these two rooms are joined, and here is the way between
    them". Both claims have to hold: if the recorded way doesn't start on the
    first room's wall, the connection is asserted where no corridor arrives.

    dungeongen believes the assertion. It punches a door into the room at the
    link's first point and splices a stub to reach it, so a link starting out
    on some distant corridor drew a corridor into a wall from nowhere - seed
    72's room 6 got one that ran west and doubled straight back onto itself.

    The cause was a branch keeping the room it came from while throwing away
    the path walked to get there. Verified to fail before the fix: 30 of 141
    links (21%) had an end off its room's wall, always the starting one."""
    checked = 0
    for seed in range(40):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for islands in compute_layout(dungeon).values():
            for island in islands:
                rects = _room_rects(island)
                for link in island["links"]:
                    a = rects.get(link["from_room"])
                    b = rects.get(link["to_room"])
                    if a is None or b is None:
                        continue  # a room that never made it onto the map
                    checked += 1
                    assert _on_boundary(link["points"][0], a), (
                        f"seed {seed}: link #{link['from_room']}->#{link['to_room']} "
                        f"starts at {link['points'][0]}, off room {link['from_room']}'s "
                        f"wall {a}"
                    )
                    assert _on_boundary(link["points"][-1], b), (
                        f"seed {seed}: link #{link['from_room']}->#{link['to_room']} "
                        f"ends at {link['points'][-1]}, off room {link['to_room']}'s "
                        f"wall {b}"
                    )
    assert checked > 100, "expected the sweep to find plenty of links"
