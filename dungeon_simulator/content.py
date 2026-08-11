"""Flavour generators for loot, clues, NPCs, traps and encounters.

The Clue Table, Trap Table and Random Architecture Table are the real
tables from the source rulebook (see tables.py for the trap/architecture
data). The DMG individual-treasure/hoard tables, the NPC table and the
Obstacles table weren't part of the pages provided, so those are
stubbed out here with small, clearly self-contained generators. Swap
them out for the real tables if you have them.
"""

from __future__ import annotations

import math

from .dice import Dice
from .tables import TRAP_TABLE

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

# Clue Table (d100) - index 0 is roll 1, index 99 is roll 100.
_CLUE_TABLE = [
    "A broken arrow of a distinctive type.",
    "The monster's / NPC's weapon has dried blood on it. But what type?",
    "The carcass or area has a strange odour.",
    "There is a strange noise coming from somewhere in this area.",
    "You see tracks leading off from this area.",
    "1d10 platinum pieces in an ornately embroidered pouch. The embroidery mentions someone's name.",
    "Magical compass; the player has to figure out the command word to activate it.",
    "The corpse is gripping an envelope, sealed with wax bearing an unknown sigil.",
    "Fresh blood stains splatter the wall. One part is still trickling down as you enter the room.",
    "The body is covered in map symbols.",
    "The body is covered in runic tattoos.",
    "The body is contorted, showing evidence of reconstructive surgery to head and chest cavity, with attachments and implants below the skin.",
    "The body is branded with a number, directly behind the neck.",
    "The body has a significant number of healed wounds, suggesting ongoing punishment and whipping.",
    "An old wooden toy horse, one you used to play with as a child and had forgotten until now.",
    "You hear loud ravens/crows, cawing nonstop nearby.",
    "You find a pendant with a missing piece.",
    "You find sacks of bloody corn and wheat.",
    "You notice a bright flash of purplish light just out of the corner of your eye.",
    "The room/corpse is covered in a thin layer of frost.",
    "A note with only the name of the nearby town written on it.",
    "Stones patterned in a directional arrow with the words 'Help me' underneath.",
    "Part of a map.",
    "A broken weapon with runes on it.",
    "A holy symbol.",
    "An adventurer's backpack containing a journal, its entries stopping abruptly.",
    "A rope hangs from above, crudely hacked at the bottom end.",
    "Graffiti on the wall: \"Beware the Great Hall!\"",
    "A hole in the floor, and beside it a spade - someone started digging and gave up. Or...",
    "A bear or man trap sitting in a pool of blood. Perhaps a severed limb nearby.",
    "Tracks, only they are made out of flour.",
    "A broken lantern.",
    "An empty coffin, the lid broken.",
    "A glass chess piece lying on the floor.",
    "The broken blade of a sword.",
    "Singing, distant and mournful.",
    "Whispering, from somewhere in the room, disembodied. It stops and starts again, unnervingly.",
    "A pile of carefully stacked stones sits in the middle of this area.",
    "Loud thumping from either above or below the current area.",
    "A loose brick in the wall hides a scroll. What is written on it? (Q/A or situations table)",
    "A hole has been bashed through the wall into an adjoining chamber, with no other way in or out.",
    "A pack and its contents strewn across the ground (suggests a live or dead NPC somewhere in the dungeon).",
    "Rubble here has been swept into neat piles by someone, obviously using a broom.",
    "You hear whispering right behind you, but when you turn, no one is there.",
    "A severed hand covered in stitches lies on the floor.",
    "A book of hand-sketched images of various humanoids, some with large red crosses through them.",
    "A body is here, savaged as if by a wild animal.",
    "A shield lies on the ground in two pieces. Whatever ripped through this possesses great strength.",
    "A platinum piece, glued to the floor.",
    "A small ray of light shines through a crack in the ceiling.",
    "A trail of blood, as if a body were being dragged, leads away, then stops suddenly.",
    "A long list of names, all crossed out except the last 5-10. Close to the end is the PC's name.",
    "A detailed colour map of the local area, marked with several previously unknown ruins.",
    "A chill wind, as if a door opened onto an arctic tundra, blows through this area briefly.",
    "You hear the sound of metal being dragged across stone. It continues for a while, then stops.",
    "Suddenly you realize your footfalls have become completely silent.",
    "Ball bearings or caltrops litter the floor in this area.",
    "Geometric shapes drawn in chalk on the floor.",
    "The floor is covered by a rug; close inspection reveals spots of a dark liquid, possibly blood.",
    "A map of a labyrinth, neatly made on a piece of parchment.",
    "A letter of recommendation from a noble no one has heard of.",
    "The remains of an adventurer lie slumped against the wall, a vial or note in hand.",
    "Hurried footsteps, coming from somewhere up ahead.",
    "A small beast (cockroach?) sits in an alcove. As you pass, it speaks to you!",
    "A bucket of entrails from an unknown creature.",
    "A target practice dummy is nearby.",
    "The sound of glass smashing comes from somewhere, echoing off the walls.",
    "A fine dagger with a retracting blade. Who did it belong to?",
    "A piece of shell that looks like it came from a large egg.",
    "The wall has been carved away, and a large standing stone placed in the new alcove, covered in strange writing.",
    "A large roast meal is laid out on a table, complete with place settings - steaming hot, but totally untouched.",
    "Goblin graffiti on the walls.",
    "A large collection of animal bones, organized into a pile.",
    "A cauldron sits in the corner.",
    "A hand... it looks severed, but the odd thing is that it's made of stone.",
    "You find a stone jar containing teeth of all descriptions.",
    "An adventurer's journal. Reading through, you see the entries stop suddenly.",
    "A table and single chair in the corner. The table is spattered with large globs of wax.",
    "An empty net on the ground, torn to shreds.",
    "A stack of clay tablets, all with indecipherable runes.",
    "A lute, its neck smashed from the body and dangling by the strings.",
    "The shrunken head of a kobold.",
    "A book containing a history of the world - not of this world, though.",
    "A well, in the middle of the dungeon. A rope hangs down from its top.",
    "You step on a stone and hear a click...",
    "A clanking sound, followed by a hissing sound, from somewhere below...",
    "A jar of pickled eyes.",
    "A campfire circle containing a prepared fire that has not been lit.",
    "Hammered to a nearby door, or affixed to the wall, is a piece of framed parchment - completely blank.",
    "An empty brandy bottle.",
    "A six-sided die that is all ones.",
    "A halfling's skull, intact except for a perfect circle removed at the top.",
    "A large assortment of clay pots in alcoves, all containing noxious-smelling liquids.",
    "A weapons rack on the wall holds several ancient, rusted weapons - a few might be restorable by an expert.",
    "A steady flow of moisture down a nearby wall suggests you might be below a body of water.",
    "The sound of rushing water, echoing from every direction.",
    "A bag of feathers. A successful Nature check (DC 12) reveals them to be from a harpy.",
    "A parchment containing what looks like a recipe for a particular kind of potion.",
    "A pouch of spell components.",
    "Magic item! Relevant to the quest.",
]

assert len(_CLUE_TABLE) == 100

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
    # Callers append their own trailing punctuation, so strip the table entry's.
    return _CLUE_TABLE[dice.d100() - 1].rstrip(".!")


def generate_npc(dice: Dice, level_hint: int) -> str:
    level = max(1, level_hint + dice.roll(4) - 2)
    return f"a level {level} {dice.choice(_NPC_CLASSES)}"


def generate_hazard(dice: Dice) -> str:
    return _HAZARDS_D6[dice.d6()]


def _trap_damage_dice(party_level: int, payload: dict) -> int:
    if "level_mult" in payload:
        return max(1, math.ceil(party_level * payload["level_mult"]))
    return max(1, party_level + payload.get("level_mod", 0))


def roll_trap(dice: Dice, party_level: int, rolls: int = 4) -> str:
    """Roll the Trap Table. The source instructs 'make 4 rolls' per trap trigger."""
    parts = []
    for _ in range(rolls):
        _, entry = TRAP_TABLE.roll(dice)
        payload = entry.payload
        dice_count = _trap_damage_dice(party_level, payload)
        detail = ""
        if payload.get("elemental"):
            detail = f" ({dice.choice(['fire', 'cold', 'force', 'lightning'])})"
        parts.append(
            f"{payload['type']}{detail} (Notice DC {payload['notice']}, Save DC {payload['save']}, "
            f"{dice_count}d6 damage)"
        )
    return "; then ".join(parts)


def encounter_description(difficulty: str) -> str:
    return f"Level-appropriate {difficulty} encounter"
