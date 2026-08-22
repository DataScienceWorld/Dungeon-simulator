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
            if any("non vengono esplorate" in line or "non prosegue" in line
                   for line in node.lines):
                # The room turned out to have nowhere to go, so its exits were
                # cut rather than explored. The rolls stay in the log - they
                # happened - but there are no children left to match them
                # against.
                assert len(node.children) < len(recorded)
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
            # Children can be fewer than the ways on: a branch the map will
            # never reach is cut, and its event stays behind in the log.
            assert len(node.children) <= len(turns)
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
    exploration past it that stops.

    The cut is not about rooms only. The layout also stops where a passage
    runs into a room already drawn, where it begins inside one, and where a
    room's wall has no cell left for another opening; it reports every one of
    those, which is what takes the residue to zero."""
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
            if any("non vengono esplorate" in line or "non prosegue" in line
                   for line in node.lines):
                assert not node.children, (
                    f"seed {seed}: room #{node.id} says its exits were not explored "
                    f"but still has {len(node.children)} of them"
                )
                assert node.geo.get("exit_slots") == []
                cut += 1
    assert cut > 20, f"expected plenty of cut rooms, found {cut}"
    # Nothing at all, not "not much". The cut used to be judged on unplaceable
    # rooms alone, which left 4.6% of the tree behind one - a room can also
    # lose its footing later, and a branch can be stopped by a passage running
    # into a room rather than by a room of its own. The layout reports every
    # place it stops, so there is no residue.
    assert behind == 0, f"{behind} of {total_nodes} nodes sit behind an unplaced room"


def _floor_openings(seeds=range(60)):
    """Every passage whose roll put an opening in its floor."""
    for seed in seeds:
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for node in dungeon.all_nodes():
            if node.kind != "passage":
                continue
            if any("Opening in the floor" in line for line in node.lines):
                yield seed, node


def test_an_opening_in_the_floor_forks_down_and_straight_on():
    """A hole in the floor is a choice, not a one-way trip.

    It used to send you down and stop the passage there, so the corridor
    *past* the opening simply did not exist - and nothing in the log said why
    the gallery ended. Same rule as the T-junction and the side passage: two
    ways on, two entries. The way down is at the level below, so the layout
    starts it on an island of its own.

    Both ways are there whatever the opening turns out to be, a secret
    trapdoor nobody spotted included: what the party notices does not decide
    what the dungeon contains."""
    forked = 0
    for seed, node in _floor_openings():
        turns = [e.get("turn") for e in node.geo.get("events", []) if e["type"] == "child"]
        assert turns == [None, None], (
            f"seed {seed} passage #{node.id}: an opening in the floor is down *and* "
            f"straight on, got {turns}"
        )
        # Down first, then on. Children can be fewer than the ways on - a
        # branch the map will never reach is cut and its event stays behind in
        # the log - so this is only checked when both survived.
        levels = [child.level for child in node.children]
        assert len(levels) <= 2
        if len(levels) == 2:
            assert levels[0] > node.level and levels[1] == node.level, (
                f"seed {seed} passage #{node.id}: expected the way down then the way "
                f"on, got levels {levels} from a passage on level {node.level}"
            )
        forked += 1
    assert forked > 40, f"forked {forked}"


def test_what_the_opening_in_the_floor_is_gets_rolled_and_written_down():
    """The table row says there is an opening, not what it is. That is a d3 of
    its own - a trap, a secret trapdoor, or a floor that has given way - and
    the roll goes in the log like every other, because a reader cannot get it
    from anywhere else."""
    kinds = set()
    checked = 0
    for seed, node in _floor_openings():
        rolled = [line for line in node.lines if line.startswith("[Opening d3=")]
        assert len(rolled) == 1, (
            f"seed {seed} passage #{node.id}: expected exactly one opening roll, "
            f"got {rolled}"
        )
        kinds.add(rolled[0].split("] ", 1)[1])
        checked += 1
    assert checked > 40, f"expected plenty of openings, found {checked}"
    assert len(kinds) == 3, f"all three d3 results should turn up, saw {kinds}"


def test_a_secret_trapdoor_is_there_whether_or_not_anyone_notices_it():
    """A Perception roll is a fact about the party, not about the floor.

    It used to decide whether the trapdoor existed at all: a failed check
    quietly deleted the branch under it, dice, rooms and everything. Now the
    roll only says whether anyone spotted it, and what is underneath is
    explored either way."""
    found = missed = 0
    for seed, node in _floor_openings():
        if not any("trapdoor" in line for line in node.lines):
            continue
        # Only when both ways on survived: a branch the map will never reach
        # is cut, and then the way down is missing for a reason that has
        # nothing to do with the trapdoor.
        if len(node.children) == 2:
            below = [child for child in node.children if child.level > node.level]
            assert below, (
                f"seed {seed} passage #{node.id}: there is a trapdoor here and no way "
                f"down through it"
            )
        if any("nobody notices" in line for line in node.lines):
            missed += 1
        else:
            assert any("The trapdoor is found" in line for line in node.lines)
            found += 1
    assert found > 3 and missed > 5, f"found {found}, missed {missed}"


def test_a_secret_door_is_explored_whether_or_not_anyone_finds_it():
    """A Perception roll says what the party noticed, not what is behind the
    wall.

    It used to decide both: a failed check meant no child was dispatched at
    all, so a whole branch of the dungeon - its rooms, its contents, its own
    rolls - was quietly deleted by one bad d20. Seed 72's passage 13 rolled a
    secret door in its left wall, missed the check at 13 vs 15, and the room
    behind it never existed.

    Both places the Passage Table puts one: in a wall (row 14) and at a dead
    end (row 6, once the 40% says there is one)."""
    found = missed = 0
    for seed in range(40):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for node in dungeon.all_nodes():
            if node.kind != "passage":
                continue
            noticed = [line for line in node.lines
                       if "secret door" in line.lower() and "Perception" in line]
            if not noticed:
                continue
            line = noticed[-1]
            # A branch the map will never reach is cut after the fact, so the
            # rule is about the event: the way through the secret door was
            # dispatched.
            ways = [e for e in node.geo.get("events", []) if e["type"] == "child"]
            assert ways, (
                f"seed {seed} passage #{node.id}: there is a secret door here and "
                f"nothing was explored beyond it - {line!r}"
            )
            if "goes unnoticed" in line or "nobody notices" in line:
                missed += 1
            else:
                found += 1
    assert found > 5 and missed > 10, f"found {found}, missed {missed}"


def test_a_widened_passage_stays_wide_down_the_way_it_carries_on():
    """"Passage widens to N ft" is about the passage, not about the stretch
    of it before the next fork.

    The width used to be lost the moment the passage ended and dispatched a
    child: a corridor rolled 30ft wide went back to the ordinary 10 at the
    first side passage. It carries now down the way that goes *straight on* -
    the same corridor - and not down a branch that turns, which is a new one.

    Over 20 seeds it takes the wide runs the layout draws from 53 to 71.

    The width itself is `(1d6 ÷ 2) x 10`, floored at 10ft for a widening and
    5ft for a narrowing: measured over 40 seeds, widening gives 10/20/30 and
    nothing else, narrowing 5/10/20/30. And either way the passage rolls
    again - all 163 of them were followed by another roll in the same
    entry."""
    import re

    carried = branched = 0
    for seed in range(20):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for node in dungeon.all_nodes():
            if node.kind != "passage":
                continue
            resized = [e for e in node.geo.get("events", []) if e["type"] == "resize"]
            if not resized:
                continue
            width = resized[-1]["width_ft"]
            # `carries_on` marks the child that *is* this corridor going on -
            # `turn is None` is not enough, a portal, a drop down a shaft and
            # a plain terminal child all look like that too.
            children = [e for e in node.geo.get("events", []) if e["type"] == "child"]
            for child, event in zip(node.children, children):
                if event.get("carries_on"):
                    assert child.geo.get("width_ft") == width, (
                        f"seed {seed} passage #{node.id}: rolled {width} ft wide and the "
                        f"way straight on came out {child.geo.get('width_ft')}"
                    )
                    carried += 1
                elif child.kind in ("passage", "pending"):
                    # Only passages: a room keeps its own rolled size in the
                    # same `width_ft`, which is not this at all.
                    assert child.geo.get("width_ft") is None, (
                        f"seed {seed} passage #{node.id}: only the way straight on keeps "
                        f"the width, not {child.geo.get('width_ft')} on a {child.kind}"
                    )
                    branched += 1
    assert carried > 5, f"expected some widened passages to carry on, found {carried}"


def test_a_passage_that_inherited_its_width_says_so():
    """A corridor drawn twice the normal width has to be explainable, and the
    roll that made it so is in another entry."""
    found = 0
    for seed in range(20):
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        for node in dungeon.all_nodes():
            if node.kind != "passage" or not node.geo.get("width_ft"):
                continue
            width = node.geo["width_ft"]
            assert any(f"is {width} ft wide here" in line for line in node.lines), (
                f"seed {seed} passage #{node.id}: inherited {width} ft and says nothing "
                f"about it: {node.lines[:2]}"
            )
            found += 1
    assert found > 5, f"expected some passages to inherit a width, found {found}"
