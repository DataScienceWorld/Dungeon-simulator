from dungeon_simulator.dice import Dice
from dungeon_simulator.tables import (
    DOOR_TABLE,
    DUNGEON_SIZE_TABLE,
    DUNGEON_TYPE_TABLE,
    PASSAGE_CONTENTS_TABLE,
    PASSAGE_TABLE,
    ROOM_CONTENTS_TABLE,
    STAIRS_TABLE,
    roll_room_shape,
)


def test_every_die_face_resolves():
    dice = Dice(seed=7)
    for table in (DUNGEON_SIZE_TABLE, DUNGEON_TYPE_TABLE, PASSAGE_TABLE, PASSAGE_CONTENTS_TABLE,
                  DOOR_TABLE, STAIRS_TABLE, ROOM_CONTENTS_TABLE):
        for value in range(1, table.die + 1):
            entry = table.resolve(value)
            assert entry is not None


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
