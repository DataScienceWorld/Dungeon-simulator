from dungeon_simulator.generator import DungeonGenerator
from dungeon_simulator.render import render_html, render_html_body, render_text, to_dict


def test_generate_produces_rooms_up_to_target():
    gen = DungeonGenerator(seed=1)
    dungeon = gen.generate()
    assert dungeon.room_count >= 1
    assert dungeon.room_count <= dungeon.target_rooms + 1  # +1: the room that meets the target may still resolve
    assert dungeon.root.children


def test_generate_is_reproducible_with_same_seed():
    d1 = DungeonGenerator(seed=555).generate()
    d2 = DungeonGenerator(seed=555).generate()
    assert to_dict(d1) == to_dict(d2)


def test_generate_varies_across_seeds():
    d1 = DungeonGenerator(seed=1).generate()
    d2 = DungeonGenerator(seed=2).generate()
    assert to_dict(d1) != to_dict(d2)


def test_render_text_contains_header_and_rooms():
    dungeon = DungeonGenerator(seed=3).generate()
    text = render_text(dungeon)
    assert "DUNGEON SIMULATOR" in text
    assert "ROOM" in text or "EDGE OF DUNGEON" in text


def test_many_seeds_do_not_crash_and_respect_node_cap():
    for seed in range(30):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=15).generate()
        assert dungeon.node_count <= 4000
        assert dungeon.room_count <= dungeon.target_rooms + 1


def test_render_html_is_a_full_document_containing_the_tree():
    dungeon = DungeonGenerator(seed=5).generate()
    page = render_html(dungeon)
    assert page.startswith("<!doctype html>")
    assert "<html" in page and "</html>" in page
    assert "dg-tree" in page
    assert dungeon.dungeon_type in page


def test_render_html_body_has_no_document_wrapper():
    dungeon = DungeonGenerator(seed=6).generate()
    fragment = render_html_body(dungeon)
    assert "<!doctype" not in fragment.lower()
    assert "<html" not in fragment.lower()
    assert "<body" not in fragment.lower()
    assert "dg-tree" in fragment


def test_render_html_escapes_generated_content():
    dungeon = DungeonGenerator(seed=6).generate()
    dungeon.root.lines.append('<script>alert("x")</script> & "quotes"')
    page = render_html(dungeon)
    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page


def test_limitless_size_is_capped():
    # Seed chosen offline for a d20 size roll of 20 ("Limitless").
    found_limitless = False
    for seed in range(200):
        gen = DungeonGenerator(seed=seed, limitless_room_cap=5)
        dungeon = gen.generate()
        if "Limitless" in dungeon.size_label:
            found_limitless = True
            assert dungeon.target_rooms == 5
    assert found_limitless, "expected at least one 'Limitless' roll across 200 seeds"


import re as _re

_WALL_FEATURE_ROWS = (12, 13, 14, 17, 18)
_CLAUSE_ROLL = _re.compile(r"\[Passage d100=(\d+) vs 50%\] The passage (ends here|continues past it)\.")
_TABLE_ROLL = _re.compile(r"\[Passage d20=(\d+)\]")


def _passage_nodes(dungeon):
    return [n for n in dungeon.all_nodes() if n.kind == "passage"]


def test_the_wall_feature_roll_is_always_written_down():
    """Standing rule for this project: whatever the dice decided has to be
    recoverable from the log. "The passage stops here" is precisely the kind
    of decision a reader of the map cannot otherwise account for, so the roll
    and its outcome are both written out."""
    seen = 0
    for seed in range(40):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for node in _passage_nodes(dungeon):
            rows = [int(m.group(1)) for line in node.lines for m in [_TABLE_ROLL.match(line)] if m]
            clauses = [line for line in node.lines if _CLAUSE_ROLL.match(line)]
            wall_rows = [r for r in rows if r in _WALL_FEATURE_ROWS]
            assert len(clauses) == len(wall_rows), (
                f"seed {seed} passage #{node.id}: rolled rows {wall_rows} but the log "
                f"records {len(clauses)} end/continue rolls"
            )
            seen += len(clauses)
    assert seen > 100, "expected the sweep to hit plenty of wall features"


def test_both_outcomes_of_the_wall_feature_roll_actually_happen():
    """A 50% that always lands the same way would pass every other test here
    while quietly reinstating the old fixed behaviour."""
    ends = carries_on = 0
    for seed in range(40):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for node in _passage_nodes(dungeon):
            for line in node.lines:
                match = _CLAUSE_ROLL.match(line)
                if match:
                    if match.group(2) == "ends here":
                        ends += 1
                    else:
                        carries_on += 1
    total = ends + carries_on
    assert total > 100
    # Loose bounds: this pins "both happen, roughly evenly", not the exact
    # stream. Measured over 60 seeds it is 50.5% / 49.5%.
    assert 0.35 < ends / total < 0.65, f"{ends} ended vs {carries_on} carried on"


def test_a_found_secret_door_hangs_off_a_wall_not_straight_ahead():
    """The secret door is "on a passage wall", so it is a side branch like the
    other two wall doors. It used to be dispatched straight ahead, which only
    worked because finding it ended the passage; now that the passage can carry
    on past it, straight ahead would run the branch down the trunk's own cells.

    The side is rolled (the table doesn't say which wall) and written down."""
    checked = 0
    for seed in range(40):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for node in _passage_nodes(dungeon):
            if not any("Secret door found" in line for line in node.lines):
                continue
            if not any("Secret door on a passage wall" in line for line in node.lines):
                continue  # the dead-end table's secret door is a different row
            wall = [line for line in node.lines if "The secret door is in the" in line]
            assert wall, f"seed {seed} passage #{node.id}: the wall was never recorded"
            assert any(w in wall[0] for w in ("left wall", "right wall"))
            turns = [e.get("turn") for e in node.geo.get("events", []) if e["type"] == "child"]
            assert any(t in ("left", "right") for t in turns), (
                f"seed {seed} passage #{node.id}: the secret door is not a side branch"
            )
            checked += 1
    assert checked, "expected at least one found secret door across the sweep"


_EXIT_ROLL = _re.compile(r"\[Room d100=(\d+) vs 50%\] Exit (\d+) of (\d+): (a door|an open way)")


def test_every_room_exit_records_its_door_roll():
    """The Room Table's rule: each exit gets a d100, 50% that it is a door,
    and a door then rolls on the Door Table.

    The rule was being followed - 50.8% doors over 1178 rolls - but only the
    door case left a trace, in the child's own "[Door d100=...]" line. An exit
    that came up a plain opening recorded nothing, and neither did one whose
    child was never filled in because the room budget ran out first, which is
    436 of 1155 exits over 60 seeds. The roll decides what a room's wall
    opens into, so it belongs in the room's own entry.

    The outcome is checked against what was actually built, not just counted:
    a roll of 50 or less has to produce a door."""
    rolls = doors = 0
    for seed in range(40):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for node in dungeon.all_nodes():
            if node.kind != "room":
                continue
            recorded = [_EXIT_ROLL.match(line) for line in node.lines]
            recorded = [m for m in recorded if m]
            if any("non vengono esplorate" in line for line in node.lines):
                # The room turned out to have nowhere to go, so its exits were
                # cut rather than explored. The rolls stay in the log - they
                # happened - but there are no children left to match them
                # against.
                assert not node.children
                continue
            assert len(recorded) == len(node.children), (
                f"seed {seed} room #{node.id}: {len(node.children)} exits but "
                f"{len(recorded)} rolls recorded"
            )
            for match, child in zip(recorded, node.children):
                value, said_door = int(match.group(1)), match.group(4) == "a door"
                assert said_door == (value <= 50), (
                    f"seed {seed} room #{node.id}: d100={value} but the entry says "
                    f"{'a door' if said_door else 'no door'}"
                )
                rolls += 1
                doors += said_door
                # An exit whose child never got filled in - the room budget ran
                # out - comes back as an edge, and either roll can end there.
                if child.kind == "door":
                    assert said_door, f"seed {seed}: a door where the roll said otherwise"
                    assert any(line.startswith("[Door d100=") for line in child.lines), (
                        f"seed {seed}: door #{child.id} never rolled on the Door Table"
                    )
                elif child.kind == "passage":
                    assert not said_door, f"seed {seed}: a passage where the roll said door"
    assert rolls > 500
    assert 0.4 < doors / rolls < 0.6, f"{doors} doors out of {rolls} rolls"


def test_a_side_passage_forks_two_ways():
    """"Passage continues N ft, then a side passage leads off to the left" is
    a junction: you take the side passage or you carry straight on past it.

    Carrying on used to be folded back into the same node - the passage simply
    took its next roll - so the log recorded the side passage as the only
    thing that happened and the choice was nowhere to be read. Both ways on
    are branches now, the same as at a T-junction or a four-way, and the
    passage ends at the junction."""
    checked = 0
    for seed in range(40):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for node in dungeon.all_nodes():
            if node.kind != "passage":
                continue
            if not any("side passage leads off" in line for line in node.lines):
                continue
            turns = [e.get("turn") for e in node.geo.get("events", []) if e["type"] == "child"]
            assert turns[-2:] == ["left", None] or turns[-2:] == ["right", None], (
                f"seed {seed} passage #{node.id}: a side passage should fork into the side "
                f"and the way straight on, got {turns}"
            )
            assert len(node.children) == len(turns)
            checked += 1
    assert checked > 20, f"expected plenty of side passages, found {checked}"


def test_a_wall_feature_that_lets_the_passage_carry_on_forks_in_two():
    """When the 50% says the passage carries on past a door in its wall,
    that is a choice - through the door, or straight on - so it is two nodes
    and this passage ends at the fork.

    It used to keep rolling in the same node, which put everything that
    happened *after* the fork inside the entry for the stretch before it: seed
    72's passage 3 recorded the door, then three more rolls belonging to the
    corridor beyond, all in one entry.

    When the roll says the passage ends instead, there is only the feature and
    no way straight on - that case must not sprout a second child."""
    forked = ended = 0
    for seed in range(40):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for node in dungeon.all_nodes():
            if node.kind != "passage":
                continue
            clause = [line for line in node.lines if _CLAUSE_ROLL.match(line)]
            if not clause:
                continue
            carries_on = _CLAUSE_ROLL.match(clause[-1]).group(2) == "continues past it"
            turns = [e.get("turn") for e in node.geo.get("events", []) if e["type"] == "child"]
            # The feature itself is a side branch, except for a secret door
            # nobody noticed - that one leaves nothing behind at all, so the
            # rule to check is only about the way *straight on*: it is there
            # exactly when the roll said the passage carries on.
            if carries_on:
                assert turns and turns[-1] is None, (
                    f"seed {seed} passage #{node.id}: carried on past a wall feature but "
                    f"there is no way straight on among {turns}"
                )
                forked += 1
            else:
                assert not turns or turns[-1] is not None, (
                    f"seed {seed} passage #{node.id}: ended at a wall feature but still "
                    f"has a way straight on: {turns}"
                )
                ended += 1
    assert forked > 20 and ended > 20, f"forked {forked}, ended {ended}"


def test_a_room_with_nowhere_to_go_does_not_have_its_branches_explored():
    """A room that fits nowhere is not on the map, and exploring past it
    spends the room budget on branches nobody will ever see. Over 40 seeds it
    was 1038 nodes of 3003 (34.6%), and 87 of the 136 rooms that never reached
    the map existed only because an unplaceable ancestor was explored anyway.

    The generator now checks placement between breadth-first waves and cuts
    there, which hands that budget back: 4.6% of nodes behind an unplaced
    room, 9 such rooms, and 47 more rooms actually drawn.

    Both halves are pinned: the cut room really has no children left, and its
    own entry says why - the rolls that produced it stay in the log, it is the
    exploration past it that stops."""
    from dungeon_simulator.layout import compute_layout

    cut = behind = total_nodes = 0
    for seed in range(40):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        placed = {
            room["id"] for islands in compute_layout(dungeon).values()
            for island in islands for room in island["rooms"]
        }
        nodes = list(dungeon.all_nodes())
        total_nodes += len(nodes)
        for node in nodes:
            if node.kind != "room" or node.id in placed:
                continue
            behind += sum(1 for child in node.children for _ in child.walk())
            if any("non vengono esplorate" in line for line in node.lines):
                assert not node.children, (
                    f"seed {seed}: room #{node.id} says its exits were not explored "
                    f"but still has {len(node.children)} of them"
                )
                assert node.geo.get("exit_slots") == []
                cut += 1
    assert cut > 20, f"expected plenty of cut rooms, found {cut}"
    # A judgement made on the tree so far, so the final layout can disagree
    # and leave a little behind - but nothing like the third of the tree it
    # used to be.
    assert behind / total_nodes < 0.10, f"{behind} of {total_nodes} nodes behind unplaced rooms"
