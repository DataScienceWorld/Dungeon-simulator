"""The dungeon-generation range tables, transcribed from the source rulebook.

Each table is addressed by rolling the stated die and looking up the
inclusive range the result falls into. A couple of entries in the source
were cut off by page-scan overlays; where that happens a short comment
marks the assumption made to fill the gap.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .dice import Dice


@dataclass(frozen=True)
class _Entry:
    low: int
    high: int
    payload: Any


class RangeTable:
    """A table addressed by inclusive numeric ranges on a single die type.

    Bonus modifiers (the +15/+30 seen on the Room/Passage Contents and
    Stairs tables) can push a roll above the highest listed range; such
    rolls clamp to the top entry instead of erroring, which is exactly
    what those bonuses are meant to do (bias towards the rare, better
    results at the end of the table).
    """

    def __init__(self, die: int, rows: list[tuple[int, int, Any]]):
        self.die = die
        self.entries = [_Entry(lo, hi, payload) for lo, hi, payload in rows]

    def resolve(self, value: int) -> _Entry:
        if value < self.entries[0].low:
            return self.entries[0]
        if value > self.entries[-1].high:
            return self.entries[-1]
        for entry in self.entries:
            if entry.low <= value <= entry.high:
                return entry
        raise ValueError(f"No entry covers roll {value} on d{self.die} table")

    def roll(self, dice: Dice, modifier: int = 0) -> tuple[int, _Entry]:
        value = dice.roll(self.die) + modifier
        return value, self.resolve(value)


# ---------------------------------------------------------------------------
# Dungeon Size Table (d20)
# ---------------------------------------------------------------------------

def _rooms(dice: Dice, expr: str) -> int:
    return dice.expr(expr)


DUNGEON_SIZE_TABLE = RangeTable(20, [
    (1, 3, {"label": "Tiny", "rooms": "1d4+2"}),
    (4, 8, {"label": "Small", "rooms": "1d6+4"}),
    (9, 16, {"label": "Medium", "rooms": "4d4+6"}),
    (17, 18, {"label": "Large", "rooms": "5d6+12"}),
    (19, 19, {"label": "Huge", "rooms": "10d6+24"}),
    (20, 20, {"label": "Limitless", "rooms": None}),
])

# ---------------------------------------------------------------------------
# Dungeon Type Table (d10)
# ---------------------------------------------------------------------------

DUNGEON_TYPE_TABLE = RangeTable(10, [
    (1, 1, "Lair"),
    (2, 2, "Tomb / Crypt"),
    (3, 3, "Abandoned stronghold"),
    (4, 4, "Temple or shrine"),
    (5, 5, "Natural caves"),
    (6, 6, "Maze"),
    (7, 7, "Mine"),
    (8, 8, "Planar Gate"),
    (9, 9, "Guild / cult headquarters"),
    (10, 10, "Death Trap"),
])

# ---------------------------------------------------------------------------
# Starting Area (d10)
# ---------------------------------------------------------------------------

STARTING_AREA_TABLE = RangeTable(10, [
    (1, 2, "passage"),
    (3, 4, "room"),
    (5, 6, "door"),
    (7, 8, "stairs"),
    (9, 10, "open_entrance"),
])

# ---------------------------------------------------------------------------
# Passage Table (d20)
# ---------------------------------------------------------------------------

PASSAGE_TABLE = RangeTable(20, [
    (1, 1, {"template": "Passage continues {n} ft.", "length_dice": "1d4", "next": "continue"}),
    (2, 2, {"template": "Passage goes 15 ft and ends at a door.", "length_fixed": 15, "next": "door"}),
    (3, 3, {"template": "Passage goes 30 ft and ends in stairs.", "length_fixed": 30, "next": "stairs"}),
    (4, 4, {"template": "Passage turns left 90 degrees.", "turn": "left", "next": "continue"}),
    (5, 5, {"template": "Passage turns right 90 degrees.", "turn": "right", "next": "continue"}),
    (6, 6, {"template": "Passage dead ends. 40% chance of a secret door.", "next": "dead_end_secret"}),
    (7, 7, {"template": "Passage continues {n} ft and comes to a four-way intersection.", "length_dice": "1d4", "next": "branch_four_way"}),
    (8, 8, {"template": "Passage continues {n} ft and comes to a T-junction.", "length_dice": "1d4", "next": "branch_t"}),
    (9, 9, {"template": "Passage continues {n} ft, then a side passage leads off to the left.", "length_dice": "1d6", "next": "branch_side_left"}),
    (10, 10, {"template": "Passage continues {n} ft, then a side passage leads off to the right.", "length_dice": "1d6", "next": "branch_side_right"}),
    (11, 11, {"template": "Passage ends in an open entrance to a room.", "next": "room"}),
    (12, 12, {"template": "Door in the right wall.", "turn": "right", "next": "door"}),
    (13, 13, {"template": "Door in the left wall.", "turn": "left", "next": "door"}),
    (14, 14, {"template": "Secret door on a passage wall (Perception DC 15).", "next": "secret_door_check"}),
    (15, 15, {"template": "Passage narrows to {n} ft wide.", "resize_dice": "1d6", "resize_min": 5, "next": "continue"}),
    (16, 16, {"template": "Passage widens to {n} ft wide.", "resize_dice": "1d6", "resize_min": 10, "next": "continue"}),
    (17, 17, {"template": "Opening to the left, leading to stairs.", "turn": "left", "next": "stairs"}),
    (18, 18, {"template": "Opening to the right, leading to stairs.", "turn": "right", "next": "stairs"}),
    (19, 19, {"template": "Opening in the floor, a straight drop down {n} ft.", "length_dice": "1d10", "next": "shaft"}),
    (20, 20, {"template": "Roll on the Random Architecture table.", "next": "architecture"}),
])

# ---------------------------------------------------------------------------
# Passage Contents Table (d100) - rolled after every Passage Table roll
# ---------------------------------------------------------------------------

PASSAGE_CONTENTS_TABLE = RangeTable(100, [
    (1, 69, {"tag": "empty"}),
    (70, 80, {"tag": "rubble", "clue_pct": 10}),
    (81, 84, {"tag": "corpse", "clue_pct": 20}),
    (85, 88, {"tag": "old_body", "clue_pct": 40}),
    (89, 90, {"tag": "encounter", "difficulty": "Easy", "loot_pct": 15, "clue_pct": 15}),
    (91, 92, {"tag": "encounter", "difficulty": "Medium", "loot_pct": 25, "clue_pct": 25}),
    (93, 94, {"tag": "encounter", "difficulty": "Hard", "loot_pct": 50, "clue_pct": 50}),
    (95, 98, {"tag": "trap"}),
    (99, 100, {"tag": "loot", "loot_pct": 60, "treasure_rolls": 1, "modifier": 30}),
])

# ---------------------------------------------------------------------------
# Door Table (d100)
# ---------------------------------------------------------------------------

DOOR_TABLE = RangeTable(100, [
    (1, 20, {
        "text": "Standard wooden door, braced with metal, unlocked.",
        "beyond": "d4_passage_stairs_room",
    }),
    (21, 25, {
        "text": ("Iron bars (portcullis) with a lever to the side; you can see through. "
                 "Pulling the lever raises it if unlocked (d4: 1-2 locked, 3-4 unlocked). "
                 "DC 14 thieves' tools to unlock, DC 19 Strength to wrench open. "
                 "The lever might be trapped."),
        "beyond": "room",
        "lock_check_dc": 14,
        "force_check_dc": 19,
    }),
    (26, 30, {
        "text": ("Empty doorway. Perhaps a magic glyph trap, triggering an attack spell. "
                 "(Unlikely, -2 modifier on whether it's trapped.)"),
        "beyond": "d4_passage_stairs_room",
        "trap_chance_pct": 35,  # "Unlikely" stand-in probability
    }),
    (31, 35, {
        "text": "Wooden door, locked. DC 15 thieves' tools, or it must be smashed (AC 12, 20 hp).",
        "beyond": "room",
        "lock_check_dc": 15,
    }),
    (36, 40, {
        "text": "Iron door, locked. DC 14 thieves' tools (or Knock, or smashing it down).",
        "beyond": "d4_passage_room",
        "lock_check_dc": 14,
    }),
    (41, 45, {
        "text": "Locked and trapped stone door. DC 15 Perception to find the trap.",
        "beyond": "d4_passage_stairs_room",
        "lock_check_dc": 15,
        "trap_chance_pct": 100,
        "trap_find_dc": 15,
    }),
    (46, 50, {
        "text": "Secret door. Through to (d4) 1: hidden passage, 2-4: hidden chamber.",
        "beyond": "secret",
    }),
    (51, 55, {
        "text": "Entrance, then 10 ft through to an adjacent passageway. Empty archway, no door.",
        "beyond": "passage",
    }),
    (56, 60, {
        "text": "Locked stone door, secured with a puzzle. DC 14 Intelligence check to solve it.",
        "beyond": "d4_passage_room",
        "lock_check_dc": 14,
    }),
    (61, 75, {
        "text": "Material and state rolled randomly (wood/stone/iron; locked or not; trapped or not).",
        "beyond": "room",
        "random_material": True,
    }),
    (76, 80, {
        "text": "Trapped door. DC 15 Perception to find the trap.",
        "beyond": "d4_passage_room",
        "trap_chance_pct": 100,
        "trap_find_dc": 15,
    }),
    (81, 85, {
        "text": ("Locked door, can only be opened with a key carried by a humanoid monster "
                  "somewhere in this dungeon."),
        "beyond": "room",
        "needs_key": True,
    }),
    (86, 90, {
        "text": ("Door composed of elemental energy (fire or lightning). You can move through it, "
                  "taking 3d8 damage of that type."),
        "beyond": "room",
        "damage_expr": "3d8",
    }),
    (91, 95, {
        "text": "Heavy stone door, requires an Athletics check to open (DC 16, -1 hp per 2 failures).",
        "beyond": "room",
        "force_check_dc": 16,
    }),
    (96, 100, {
        "text": "Door is smashed and hanging off its hinges (why?).",
        "beyond": "room",
    }),
])

# ---------------------------------------------------------------------------
# Stairs Table (d20)
# ---------------------------------------------------------------------------

STAIRS_TABLE = RangeTable(20, [
    (1, 8, {"text": "Down one level to a (d4) room/passage.", "level_delta": 1, "beyond": "d4_room_passage"}),
    (9, 9, {"text": "Down one level to a room, +15 to the Room Contents roll.", "level_delta": 1, "beyond": "room", "modifier": 15}),
    (10, 10, {"text": "Down one level to a room, +30 to the Room Contents roll.", "level_delta": 1, "beyond": "room", "modifier": 30}),
    (11, 11, {"text": "Down one level to a passage.", "level_delta": 1, "beyond": "passage"}),
    (12, 12, {"text": "Down one level to a passage, +15 to the Passage Contents roll.", "level_delta": 1, "beyond": "passage", "modifier": 15}),
    (13, 13, {"text": "Down one level to a passage, +30 to the Passage Contents roll.", "level_delta": 1, "beyond": "passage", "modifier": 30}),
    (14, 14, {"text": "Down two levels to a (d4) passage/room.", "level_delta": 2, "beyond": "d4_passage_room"}),
    (15, 15, {"text": "Up one level to a room, +15 to the Room Contents roll.", "level_delta": -1, "beyond": "room", "modifier": 15}),
    (16, 16, {"text": "Up one level to a room, +30 to the Room Contents roll.", "level_delta": -1, "beyond": "room", "modifier": 30}),
    (17, 17, {"text": "Up one level to a passage.", "level_delta": -1, "beyond": "passage"}),
    (18, 18, {"text": "Up one level to a passage, +15 to the Passage Contents roll.", "level_delta": -1, "beyond": "passage", "modifier": 15}),
    # Source lists +15 (not +30) for entry 19 as well - transcribed as printed.
    (19, 19, {"text": "Up one level to a passage, +15 to the Passage Contents roll.", "level_delta": -1, "beyond": "passage", "modifier": 15}),
    (20, 20, {"text": "Up two levels to a (d4) passage/room.", "level_delta": -2, "beyond": "d4_passage_room"}),
])

# ---------------------------------------------------------------------------
# Room Table (d20) - shape/size builders that roll their own dice
# ---------------------------------------------------------------------------

def _room_rect(dice: Dice) -> dict:
    w, l = dice.d4() * 10, dice.d4() * 10
    return {"text": f"Rectangular room, {w}ft x {l}ft.", "dims": (w, l), "exits": dice.d6(), "shape": "rect"}


def _room_square(dice: Dice, die: int) -> dict:
    side = (dice.roll(die) + 1) * 10
    exits_die = {4: 4, 6: 6, 8: 8}[die]
    return {"text": f"Square room, {side}ft on each side.", "dims": (side, side), "exits": dice.roll(exits_die), "shape": "square"}


def _room_rect_ab(dice: Dice, die_a: int, off_a: int, die_b: int, off_b: int) -> dict:
    w = (dice.roll(die_a) + off_a) * 10
    l = (dice.roll(die_b) + off_b) * 10
    return {"text": f"Rectangular room, {w}ft x {l}ft.", "dims": (w, l), "exits": dice.d6(), "shape": "rect"}


def _room_circular(dice: Dice) -> dict:
    d = dice.d4() * 10
    return {"text": f"Circular room, {d}ft diameter.", "dims": (d, d), "exits": dice.d4(), "shape": "circle"}


def _room_triangular(dice: Dice) -> dict:
    side = dice.d6() * 10
    return {"text": f"Triangular room, {side}ft along one side (others fit the space).", "dims": (side, side), "exits": dice.d4(), "shape": "triangle"}


def _room_polygon(dice: Dice, side_die: int, exit_die: int, exit_offset: int) -> dict:
    across = dice.roll(side_die) * 10
    exits = max(1, dice.roll(exit_die) + exit_offset)
    return {"text": f"Polygonal room, {across}ft across.", "dims": (across, across), "exits": exits, "shape": "polygon"}


def _room_trapezoidal(dice: Dice) -> dict:
    side = dice.d6() * 10
    # Exit count wasn't legible on the source page for this entry; d4 is used
    # by analogy with the other irregular-polygon rooms above.
    return {"text": f"Trapezoidal room, roughly {side}ft on each side.", "dims": (side, side), "exits": dice.d4(), "shape": "trapezoid"}


def _room_cave(dice: Dice) -> dict:
    width = dice.d12() * 10
    # Exit count for the rough-cave entry was cropped out of the source scan;
    # d6 is used as a reasonable default in line with similarly sized rooms.
    return {"text": f"Rough cave, roughly {width}ft across.", "dims": (width, width), "exits": dice.d6(), "shape": "cave"}


ROOM_TABLE_BUILDERS: dict[tuple[int, int], Callable[[Dice], dict]] = {
    (1, 2): lambda dice: _room_rect(dice),
    (3, 4): lambda dice: _room_square(dice, 4),
    (5, 6): lambda dice: _room_square(dice, 6),
    (7, 8): lambda dice: _room_square(dice, 8),
    (9, 10): lambda dice: _room_rect_ab(dice, 4, 1, 8, 1),
    (11, 12): lambda dice: _room_rect_ab(dice, 6, 1, 6, 2),
    (13, 14): lambda dice: _room_circular(dice),
    (15, 15): lambda dice: _room_triangular(dice),
    (16, 16): lambda dice: _room_polygon(dice, 4, 4, -2),
    (17, 17): lambda dice: _room_polygon(dice, 6, 4, -1),
    (18, 18): lambda dice: _room_polygon(dice, 6, 4, -1),
    (19, 19): lambda dice: _room_trapezoidal(dice),
    (20, 20): lambda dice: _room_cave(dice),
}


def roll_room_shape(dice: Dice) -> dict:
    value = dice.d20()
    for (lo, hi), builder in ROOM_TABLE_BUILDERS.items():
        if lo <= value <= hi:
            result = builder(dice)
            result["roll"] = value
            return result
    raise AssertionError("unreachable")  # every 1-20 value is covered above


# ---------------------------------------------------------------------------
# Room Contents Table (d100)
# ---------------------------------------------------------------------------

RANDOM_ARCHITECTURE_TABLE = RangeTable(20, [
    (1, 1, "Statue"),
    (2, 2, "Series of alcoves"),
    (3, 3, "Fountain"),
    (4, 4, "1d4 pools"),
    (5, 5, "Hole in the floor"),
    (6, 6, "Underground terrarium"),
    (7, 7, "Pillars along each side - is anything hiding there?"),
    (8, 8, "Catacombs"),
    (9, 9, "A puzzle of some sort (Intelligence check required)"),
    (10, 10, "Sacrificial plinth"),
    (11, 11, "Temple / shrine"),
    (12, 12, "Guard post"),
    (13, 13, "Trapdoor with a ladder"),
    (14, 14, "Underground stream"),
    (15, 15, "Natural cavern"),
    (16, 16, "Ventilation shaft"),
    (17, 17, "Crystal growth"),
    (18, 18, "Abandoned campsite"),
    (19, 19, "Portal - takes you to another, random part of the dungeon"),
    (20, 20, "Edible fungi / moss farm"),
])

# ---------------------------------------------------------------------------
# Secret Door Table (d6)
# ---------------------------------------------------------------------------

SECRET_DOOR_TABLE = RangeTable(6, [
    (1, 2, {"beyond": "room", "modifier": 40, "trapped": False}),
    (3, 4, {"beyond": "passage", "modifier": 40, "trapped": False}),
    (5, 6, {"beyond": "d4_passage_room", "modifier": 50, "trapped": True}),
])

# ---------------------------------------------------------------------------
# Trap Table (d100) - "Make 4 rolls" per the source
# ---------------------------------------------------------------------------

TRAP_TABLE = RangeTable(100, [
    (1, 6, {"type": "Poison darts", "notice": 11, "save": 10, "level_mod": -3}),
    (7, 12, {"type": "Collapsing roof", "notice": 11, "save": 10, "level_mod": -2}),
    (13, 19, {"type": "Simple pit", "notice": 11, "save": 11, "level_mod": -1}),
    (20, 26, {"type": "Hidden pit", "notice": 11, "save": 12, "level_mod": -1}),
    (27, 32, {"type": "Locking pit", "notice": 11, "save": 12, "level_mod": 0}),
    (33, 38, {"type": "Spiked pit", "notice": 12, "save": 13, "level_mod": 0}),
    (39, 44, {"type": "Rolling sphere", "notice": 12, "save": 14, "level_mod": 0}),
    (45, 50, {"type": "Scything blade", "notice": 13, "save": 14, "level_mod": 1}),
    (51, 56, {"type": "Glyph trap", "notice": 14, "save": 15, "level_mod": 1, "elemental": True}),
    (57, 63, {"type": "Magic missile spell", "notice": 14, "save": 15, "level_mod": 1}),
    (64, 69, {"type": "Poison gas / acid spray", "notice": 15, "save": 16, "level_mod": 1}),
    (70, 76, {"type": "Room fills with water", "notice": 15, "save": 16, "level_mod": 2}),
    (77, 82, {"type": "Walls begin closing", "notice": 16, "save": 17, "level_mod": 2}),
    (83, 88, {"type": "Spears come out of the floor", "notice": 17, "save": 18, "level_mod": 2}),
    (89, 93, {"type": "Spiked grate drops", "notice": 17, "save": 19, "level_mult": 1.5}),
    (94, 100, {"type": "Trapdoor (snakes / acid below?)", "notice": 18, "save": 20, "level_mult": 2}),
])

ROOM_CONTENTS_TABLE = RangeTable(100, [
    (1, 4, {"tag": "deadly_encounter", "loot_pct": 45, "clue_pct": 75}),
    (5, 8, {"tag": "bbeg_remnants"}),
    (9, 12, {"tag": "encounter", "difficulty": "Easy", "note": "low-level minions of the BBEG"}),
    (13, 20, {"tag": "hazard"}),
    (21, 32, {"tag": "encounter", "difficulty": "Hard", "clue_pct": 30, "loot_pct": 30, "secret_door_pct": 30}),
    (33, 36, {"tag": "npc_investigating"}),
    (37, 40, {"tag": "trapped_victim", "alive_pct": 30, "loot_pct": 10}),
    (41, 52, {"tag": "encounter", "difficulty": "Easy", "loot_pct": 20, "secret_door_pct": 10, "clue_pct": 30}),
    (53, 56, {"tag": "obstacle"}),
    (57, 67, {"tag": "encounter", "difficulty": "Medium", "loot_pct": 30, "secret_door_pct": 20, "clue_pct": 30}),
    (68, 71, {"tag": "dying_npc", "loot_pct": 50}),
    (72, 74, {"tag": "creatures_fighting"}),
    (75, 76, {"tag": "runes"}),
    (77, 80, {"tag": "strong_npc", "secret_door_pct": 30, "loot_pct": 30}),
    (81, 84, {"tag": "empty_mission_loot", "loot_pct": 30}),
    (85, 88, {"tag": "encounter", "difficulty": "Easy", "clue_pct": 30, "npc_pct": 30, "boon_pct": 30}),
    (89, 92, {"tag": "relic", "guarded": True}),
    (93, 100, {"tag": "boss", "loot_pct": 90}),
])
