"""The per-table notes in `docs/tabelle/` have to keep up with the tables.

They are read to answer "what does this roll actually become", so a row that
exists in `tables.py` and not in its `.md` is worse than no note at all: it
reads as complete and is not. These tests do not check the *prose* - nobody can
- but they do check that every row of every table has a line of its own, and
that the index lists every file.

Rows are matched by their bold range label, `**7**` or `**1-8**`, which is the
format every one of those files uses.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from dungeon_simulator.tables import (
    DOOR_TABLE,
    DUNGEON_SIZE_TABLE,
    DUNGEON_TYPE_TABLE,
    PASSAGE_CONTENTS_TABLE,
    PASSAGE_TABLE,
    RANDOM_ARCHITECTURE_TABLE,
    ROOM_CONTENTS_TABLE,
    ROOM_TABLE_BUILDERS,
    SECRET_DOOR_TABLE,
    STAIRS_TABLE,
    STARTING_AREA_TABLE,
    TRAP_TABLE,
)

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs" / "tabelle"

TABLE_DOCS = {
    "dungeon-size.md": DUNGEON_SIZE_TABLE,
    "dungeon-type.md": DUNGEON_TYPE_TABLE,
    "starting-area.md": STARTING_AREA_TABLE,
    "passage.md": PASSAGE_TABLE,
    "passage-contents.md": PASSAGE_CONTENTS_TABLE,
    "door.md": DOOR_TABLE,
    "stairs.md": STAIRS_TABLE,
    "room-contents.md": ROOM_CONTENTS_TABLE,
    "random-architecture.md": RANDOM_ARCHITECTURE_TABLE,
    "secret-door.md": SECRET_DOOR_TABLE,
    "trap.md": TRAP_TABLE,
}


def _label(low: int, high: int) -> str:
    return f"**{low}**" if low == high else f"**{low}-{high}**"


@pytest.mark.parametrize("filename", sorted(TABLE_DOCS))
def test_every_row_of_the_table_has_a_line_in_its_notes(filename):
    text = (DOCS / filename).read_text(encoding="utf-8")
    missing = [
        _label(entry.low, entry.high)
        for entry in TABLE_DOCS[filename].entries
        if _label(entry.low, entry.high) not in text
    ]
    assert not missing, (
        f"docs/tabelle/{filename} says nothing about {', '.join(missing)} - "
        f"a row was added or its range changed and the note was not updated"
    )


def test_the_room_tables_shape_rows_all_have_a_line():
    text = (DOCS / "room.md").read_text(encoding="utf-8")
    missing = [_label(lo, hi) for lo, hi in ROOM_TABLE_BUILDERS if _label(lo, hi) not in text]
    assert not missing, f"docs/tabelle/room.md says nothing about {', '.join(missing)}"


def test_the_notes_do_not_claim_ranges_the_table_does_not_have():
    """The other direction: a row that was narrowed or removed leaves a line
    behind describing a roll that can no longer come up."""
    for filename, table in TABLE_DOCS.items():
        text = (DOCS / filename).read_text(encoding="utf-8")
        known = {_label(entry.low, entry.high) for entry in table.entries}
        # only labels in the leftmost column of a table row, so a `**+15**` or
        # a bold number in the prose is not mistaken for one
        claimed = set(re.findall(r"^\|\s*(\*\*\d+(?:-\d+)?\*\*)\s*\|", text, re.M))
        stale = claimed - known
        assert not stale, (
            f"docs/tabelle/{filename} still describes {', '.join(sorted(stale))}, "
            f"which is no longer a row of this table"
        )


def test_the_index_lists_every_file_and_every_file_is_listed():
    index = (DOCS / "README.md").read_text(encoding="utf-8")
    on_disk = {path.name for path in DOCS.glob("*.md")} - {"README.md"}
    linked = set(re.findall(r"\(([a-z-]+\.md)\)", index))
    assert on_disk - linked == set(), (
        f"not linked from docs/tabelle/README.md: {sorted(on_disk - linked)}"
    )
    assert linked - on_disk == set(), (
        f"linked from docs/tabelle/README.md but missing: {sorted(linked - on_disk)}"
    )
