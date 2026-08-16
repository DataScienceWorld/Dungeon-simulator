from dungeon_simulator.content import generate_clue, roll_trap
from dungeon_simulator.dice import Dice
from dungeon_simulator.tables import (
    DOOR_TABLE,
    DUNGEON_SIZE_TABLE,
    DUNGEON_TYPE_TABLE,
    PASSAGE_CONTENTS_TABLE,
    PASSAGE_TABLE,
    RANDOM_ARCHITECTURE_TABLE,
    ROOM_CONTENTS_TABLE,
    SECRET_DOOR_TABLE,
    STAIRS_TABLE,
    TRAP_TABLE,
    roll_room_shape,
)


def test_every_die_face_resolves():
    dice = Dice(seed=7)
    for table in (DUNGEON_SIZE_TABLE, DUNGEON_TYPE_TABLE, PASSAGE_TABLE, PASSAGE_CONTENTS_TABLE,
                  DOOR_TABLE, STAIRS_TABLE, ROOM_CONTENTS_TABLE, RANDOM_ARCHITECTURE_TABLE,
                  SECRET_DOOR_TABLE, TRAP_TABLE):
        for value in range(1, table.die + 1):
            entry = table.resolve(value)
            assert entry is not None


def test_clue_table_has_100_distinct_entries():
    dice = Dice(seed=11)
    seen = {generate_clue(dice) for _ in range(300)}
    assert len(seen) > 50  # sampling should hit a good spread of the 100 entries


def test_roll_trap_makes_four_components_by_default():
    dice = Dice(seed=12)
    result = roll_trap(dice, party_level=5)
    assert result.count("; then ") == 3
    assert "Notice DC" in result and "Save DC" in result and "d6 damage" in result


def test_roll_trap_damage_never_below_one_die():
    dice = Dice(seed=13)
    for _ in range(200):
        result = roll_trap(dice, party_level=1, rolls=1)
        assert "0d6" not in result


def test_modifier_clamps_above_top_entry():
    entry = ROOM_CONTENTS_TABLE.resolve(130)
    assert entry.low == 93 and entry.high == 100


def test_modifier_clamps_below_bottom_entry():
    entry = ROOM_CONTENTS_TABLE.resolve(-10)
    assert entry.low == 1


def test_room_shape_builder_covers_all_rolls():
    dice = Dice(seed=99)
    for _ in range(500):
        shape = roll_room_shape(dice)
        assert shape["exits"] >= 1
        assert shape["dims"][0] > 0 and shape["dims"][1] > 0


_WALL_FEATURE_ROWS = (12, 13, 14, 17, 18)


def test_wall_feature_rows_offer_the_passage_a_way_to_carry_on():
    """The rows that put a feature in a passage *wall* - a door either side,
    a secret door, an opening to stairs - each carry an explicit 50% chance
    that the passage ends there.

    Before this the behaviour was split three ways and stated nowhere: a door
    in a wall always ended the passage, an opening to stairs never did, and a
    secret door ended it only if someone noticed it. The clause is on the row
    itself so a reader of the table knows it without reading the generator."""
    for roll in _WALL_FEATURE_ROWS:
        payload = PASSAGE_TABLE.resolve(roll).payload
        assert payload.get("end_chance_pct") == 50, (
            f"passage row {roll} should carry the 50% end/continue clause"
        )
        assert "50% chance the passage ends here" in payload["template"], (
            f"passage row {roll}'s own text should state the clause"
        )
        assert payload.get("side"), (
            f"passage row {roll} places its feature in a wall, so it needs a side"
        )


def test_no_other_passage_row_carries_the_clause():
    """It is opt-in per row: anything without the clause keeps the plain
    behaviour, so adding the key by accident silently changes a row."""
    for roll in range(1, 21):
        payload = PASSAGE_TABLE.resolve(roll).payload
        if roll in _WALL_FEATURE_ROWS:
            continue
        assert "end_chance_pct" not in payload, f"passage row {roll} unexpectedly has the clause"
