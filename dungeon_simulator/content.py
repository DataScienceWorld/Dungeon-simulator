"""Flavour generators for loot, clues, NPCs, traps and encounters.

The source material references several tables that weren't part of the
pages provided (the DMG individual-treasure/hoard tables, the Clues
table, the NPC table, the Trap table, the Obstacles table, the Random
Architecture table). Those are stubbed out here with small, clearly
self-contained generators so the simulator can still produce a
complete result end to end. Swap these out for the real tables if you
have them.
"""

from __future__ import annotations

from .dice import Dice

_TREASURE_TIERS = {
    "low": (10, 60, 2),      # (gp die sides, gp multiplier, magic-item chance %)
    "mid": (20, 100, 8),
    "high": (20, 500, 20),
    "epic": (20, 2000, 40),
}

_MAGIC_ITEMS = [
    "a potion of healing",
    "a scroll covered in unfamiliar runes",
    "a +1 dagger",
    "a ring that hums faintly",
    "a wand with one charge left",
    "an amulet depicting a forgotten god",
    "a cloak that repels dust and grime",
    "a set of masterwork thieves' tools",
]

_CLUES = [
    "a torn page with a hand-drawn map fragment",
    "a name scrawled in blood on the wall",
    "a sigil matching one you've seen elsewhere in this dungeon",
    "a letter, half-burnt, naming a conspirator",
    "a ledger entry recording a delivery to this place",
    "a child's toy, oddly out of place here",
    "a key with no visible lock to match",
    "fresh tracks heading deeper in",
]

_NPC_CLASSES = [
    "Fighter", "Rogue", "Wizard", "Cleric", "Ranger",
    "Barbarian", "Bard", "Druid", "Paladin", "Warlock",
]

_HAZARDS_D6 = {
    1: "a sinkhole",
    2: "a patch of luminous fungus",
    3: "a trap",
    4: "collapsing masonry (or another natural hazard)",
    5: "a wandering monster (medium difficulty)",
    6: "something of the player's choice",
}

_ARCHITECTURE_FLAVOUR = [
    "Weathered pillars, carved with scenes you don't recognise, line the way.",
    "A faded mural covers one wall, its meaning lost to time.",
    "Rubble from an old collapse narrows the space underfoot.",
    "A dry fountain, cracked and empty, sits against the wall.",
    "A statue, worn featureless, watches from an alcove.",
    "A rope bridge sways over a black chasm you can't see the bottom of.",
    "Strange, cold draughts blow from unseen vents in the stone.",
    "Old scaffolding, long abandoned, still clings to the walls.",
]


def treasure_tier_for_level(dungeon_level: int) -> str:
    """Very rough level->tier mapping, standing in for the real challenge tables."""
    if dungeon_level <= 1:
        return "low"
    if dungeon_level <= 3:
        return "mid"
    if dungeon_level <= 6:
        return "high"
    return "epic"


def generate_treasure(dice: Dice, tier: str, rolls: int = 1) -> list[str]:
    sides, multiplier, magic_chance = _TREASURE_TIERS.get(tier, _TREASURE_TIERS["low"])
    results = []
    for _ in range(rolls):
        gp = dice.roll(sides)
        gp *= multiplier // 10 or 1
        line = f"{gp} gp"
        if dice.chance(magic_chance):
            line += f", plus {dice.choice(_MAGIC_ITEMS)}"
        results.append(line)
    return results


def generate_hoard(dice: Dice, tier: str) -> str:
    sides, multiplier, magic_chance = _TREASURE_TIERS.get(tier, _TREASURE_TIERS["high"])
    gp = dice.roll(sides, count=3) * (multiplier // 5 or 1)
    line = f"a hoard worth roughly {gp} gp"
    if dice.chance(min(90, magic_chance * 2)):
        items = dice.roll(4)
        chosen = ", ".join(dice.choice(_MAGIC_ITEMS) for _ in range(items))
        line += f", including {chosen}"
    return line


def generate_clue(dice: Dice) -> str:
    return dice.choice(_CLUES)


def generate_npc(dice: Dice, level_hint: int) -> str:
    level = max(1, level_hint + dice.roll(4) - 2)
    return f"a level {level} {dice.choice(_NPC_CLASSES)}"


def generate_hazard(dice: Dice) -> str:
    return _HAZARDS_D6[dice.d6()]


def generate_architecture_flavour(dice: Dice) -> str:
    return dice.choice(_ARCHITECTURE_FLAVOUR)


def generate_trap(dice: Dice) -> str:
    dc = dice.roll(4, modifier=10)  # DC 11-14, generic stand-in
    damage = dice.roll(6, count=2)
    kinds = ["a pressure plate", "a tripwire", "a poisoned needle", "a collapsing floor panel",
             "a swinging blade", "a dart trap", "a gas vent"]
    return (f"{dice.choice(kinds)} (Perception/Investigation DC {dc} to notice, "
            f"roughly {damage} damage if triggered)")


def encounter_description(difficulty: str) -> str:
    return f"Level-appropriate {difficulty} encounter"
