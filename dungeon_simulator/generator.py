"""Core dungeon generation: walks the tables and builds an explorable tree."""

from __future__ import annotations

from .content import (
    encounter_description,
    generate_architecture_flavour,
    generate_clue,
    generate_hazard,
    generate_hoard,
    generate_npc,
    generate_trap,
    generate_treasure,
    treasure_tier_for_level,
)
from .dice import Dice
from .models import Dungeon, Node
from .tables import (
    DOOR_TABLE,
    DUNGEON_SIZE_TABLE,
    DUNGEON_TYPE_TABLE,
    PASSAGE_CONTENTS_TABLE,
    PASSAGE_TABLE,
    ROOM_CONTENTS_TABLE,
    STAIRS_TABLE,
    STARTING_AREA_TABLE,
    roll_room_shape,
)

DEFAULT_LIMITLESS_ROOMS = 40
MAX_PASSAGE_SEGMENTS = 15
MAX_NODES = 4000


class DungeonGenerator:
    def __init__(self, seed: int | None = None, limitless_room_cap: int = DEFAULT_LIMITLESS_ROOMS,
                 verbose_empty: bool = False):
        self.dice = Dice(seed)
        self.seed = seed
        self.limitless_room_cap = limitless_room_cap
        self.verbose_empty = verbose_empty
        self._next_id = 0
        self.rooms_created = 0
        self.target_rooms = 0
        self.node_count = 0

    # -- bookkeeping ---------------------------------------------------

    def _id(self) -> int:
        value = self._next_id
        self._next_id += 1
        self.node_count += 1
        return value

    def budget_exhausted(self) -> bool:
        return self.rooms_created >= self.target_rooms or self.node_count >= MAX_NODES

    def _edge_node(self, level: int) -> Node:
        return Node(
            id=self._id(), kind="edge", level=level,
            lines=["You sense you've reached the edge of the dungeon. Time to leave!"],
        )

    def dispatch_beyond(self, kind: str, level: int, modifier: int = 0) -> Node:
        """Resolve whatever lies beyond a passage/door/stairs, respecting the room budget.

        Per the Dungeon Size Table's rule: once the target room count is
        reached, rooms stop having extra exits and passages tend to dead-end.
        """
        if self.budget_exhausted():
            return self._edge_node(level)
        if kind == "room":
            return self.resolve_room(level, modifier=modifier)
        if kind == "passage":
            return self.resolve_passage(level)
        if kind == "stairs":
            return self.resolve_stairs(level)
        if kind == "door":
            return self.resolve_door(level)
        if kind == "d4_passage_stairs_room":
            roll = self.dice.d4()
            return self.dispatch_beyond({1: "passage", 2: "stairs", 3: "room", 4: "room"}[roll], level, modifier)
        if kind == "d4_passage_room":
            roll = self.dice.d4()
            return self.dispatch_beyond("passage" if roll == 1 else "room", level, modifier)
        if kind == "d4_room_passage":
            roll = self.dice.d4()
            return self.dispatch_beyond("room" if roll <= 2 else "passage", level, modifier)
        if kind == "secret":
            roll = self.dice.d4()
            child = self.dispatch_beyond("passage" if roll == 1 else "room", level, modifier)
            child.lines.insert(0, "(hidden behind a secret door)")
            return child
        raise ValueError(f"Unknown dispatch kind: {kind!r}")

    # -- top level -------------------------------------------------------

    def generate(self) -> Dungeon:
        _, type_entry = DUNGEON_TYPE_TABLE.roll(self.dice)
        dungeon_type = type_entry.payload

        size_val, size_entry = DUNGEON_SIZE_TABLE.roll(self.dice)
        size_label = size_entry.payload["label"]
        if size_entry.payload["rooms"] is None:
            self.target_rooms = self.limitless_room_cap
            size_note = f"{size_label} (capped at {self.target_rooms} rooms for this simulation)"
        else:
            self.target_rooms = max(1, self.dice.expr(size_entry.payload["rooms"]))
            size_note = f"{size_label} ({self.target_rooms} rooms)"

        root = Node(
            id=self._id(), kind="start", level=1,
            lines=[f"Dungeon type: {dungeon_type}", f"Size: {size_note}"],
        )

        start_val, start_entry = STARTING_AREA_TABLE.roll(self.dice)
        start_kind = start_entry.payload
        if start_kind == "open_entrance":
            roll = self.dice.d4()
            start_kind = "passage" if roll <= 2 else "room"
            root.lines.append("Open entrance.")
        child = self.dispatch_beyond(start_kind, level=1)
        root.children.append(child)

        return Dungeon(
            dungeon_type=dungeon_type,
            size_label=size_note,
            target_rooms=self.target_rooms,
            seed=self.seed,
            root=root,
            room_count=self.rooms_created,
            node_count=self.node_count,
        )

    # -- passages ---------------------------------------------------------

    def resolve_passage(self, level: int) -> Node:
        node = Node(id=self._id(), kind="passage", level=level, lines=[])
        segments = 0
        while True:
            value, entry = PASSAGE_TABLE.roll(self.dice)
            payload = entry.payload
            node.lines.append(f"[Passage d20={value}] {payload['text']}")
            node.lines.extend(self._passage_contents_lines(level))

            tag = payload["next"]

            if tag == "continue":
                segments += 1
                if segments >= MAX_PASSAGE_SEGMENTS:
                    node.lines.append("The passage keeps going, but you've mapped enough of it for now.")
                    return node
                continue

            if tag == "architecture":
                node.lines.append(generate_architecture_flavour(self.dice))
                segments += 1
                if segments >= MAX_PASSAGE_SEGMENTS:
                    return node
                continue

            if tag in ("branch_four_way", "branch_t", "branch_side"):
                if not self.budget_exhausted():
                    node.children.append(self.resolve_passage(level))
                else:
                    node.children.append(self._edge_node(level))
                segments += 1
                if segments >= MAX_PASSAGE_SEGMENTS:
                    return node
                continue

            if tag == "dead_end_secret":
                if self.dice.chance(40):
                    roll, found = self.dice.check(dc=15)
                    if found:
                        node.lines.append(f"A secret door is found here (Perception {roll} vs DC 15)!")
                        sub = self.dice.d4()
                        child = self.dispatch_beyond("passage" if sub == 1 else "room", level)
                        node.children.append(child)
                    else:
                        node.lines.append(f"There's a secret door here, but it goes unnoticed (Perception {roll} vs DC 15).")
                else:
                    node.lines.append("A true dead end.")
                return node

            if tag == "secret_door_check":
                roll, found = self.dice.check(dc=15)
                if found:
                    node.lines.append(f"Secret door found (Perception {roll} vs DC 15)!")
                    sub = self.dice.d4()
                    child = self.dispatch_beyond("passage" if sub == 1 else "room", level)
                    node.children.append(child)
                    return node
                node.lines.append(f"Perception {roll} vs DC 15 - nothing noticed. The passage continues.")
                segments += 1
                if segments >= MAX_PASSAGE_SEGMENTS:
                    return node
                continue

            if tag == "shaft":
                depth = self.dice.d10() * 10
                node.lines.append(f"It's a {depth} ft drop.")
                sub = self.dice.d4()
                child = self.dispatch_beyond("passage" if sub <= 2 else "room", level + 1)
                node.children.append(child)
                return node

            # terminal: door / stairs / room
            child = self.dispatch_beyond(tag, level)
            node.children.append(child)
            return node

    def _passage_contents_lines(self, level: int) -> list[str]:
        value, entry = PASSAGE_CONTENTS_TABLE.roll(self.dice)
        payload = entry.payload
        tag = payload["tag"]

        if tag == "empty":
            return [f"[Contents d100={value}] Empty."] if self.verbose_empty else []

        lines = [f"[Contents d100={value}]"]
        if tag == "rubble":
            if self.dice.chance(payload["clue_pct"]):
                lines.append(f"Rubble here, hiding a clue: {generate_clue(self.dice)}.")
            else:
                lines.append("Just rubble.")
        elif tag == "corpse":
            if self.dice.chance(payload["clue_pct"]):
                lines.append(f"A corpse lies here, with a clue on the body: {generate_clue(self.dice)}.")
            else:
                lines.append("A corpse lies here, picked clean.")
        elif tag == "old_body":
            if self.dice.chance(payload["clue_pct"]):
                lines.append(f"A long-dead body, with a clue: {generate_clue(self.dice)}.")
            else:
                lines.append("A long-dead body, with nothing of note.")
        elif tag == "encounter":
            lines.append(f"{encounter_description(payload['difficulty'])} in this stretch of passage.")
            if self.dice.chance(payload["loot_pct"]):
                tier = treasure_tier_for_level(level)
                lines.append(f"Loot: {generate_treasure(self.dice, tier)[0]}.")
            if self.dice.chance(payload["clue_pct"]):
                lines.append(f"Clue: {generate_clue(self.dice)}.")
        elif tag == "trap":
            lines.append(f"Trap! {generate_trap(self.dice)}.")
        elif tag == "loot":
            if self.dice.chance(payload["loot_pct"]):
                tier = treasure_tier_for_level(level)
                lines.append(f"Loot, oddly out of place here: {generate_treasure(self.dice, tier)[0]}. How did this get here?")
            else:
                lines.append("Nothing here after all.")
        return lines

    # -- doors --------------------------------------------------------------

    def resolve_door(self, level: int) -> Node:
        value, entry = DOOR_TABLE.roll(self.dice)
        payload = entry.payload
        lines = [f"[Door d100={value}] {payload['text']}"]

        if payload.get("lock_check_dc"):
            roll, success = self.dice.check(payload["lock_check_dc"])
            lines.append(f"Lock check: {roll} vs DC {payload['lock_check_dc']} -> {'opened' if success else 'must be forced/smashed'}.")
        if payload.get("trap_chance_pct") is not None and self.dice.chance(payload["trap_chance_pct"]):
            find_dc = payload.get("trap_find_dc", 15)
            roll, success = self.dice.check(find_dc)
            lines.append(f"Trapped! Perception {roll} vs DC {find_dc} -> {'trap found and avoided' if success else 'trap triggered'}.")
        if payload.get("force_check_dc"):
            roll, success = self.dice.check(payload["force_check_dc"])
            lines.append(f"Forcing it open: {roll} vs DC {payload['force_check_dc']} -> {'success' if success else 'still stuck'}.")
        if payload.get("damage_expr"):
            dmg = self.dice.expr(payload["damage_expr"])
            lines.append(f"Passing through costs {dmg} damage.")
        if payload.get("needs_key"):
            lines.append("This door needs a key, carried by a humanoid monster somewhere in the dungeon.")
        if payload.get("random_material"):
            material = {1: "Wooden", 2: "Wooden", 3: "Stone", 4: "Stone", 5: "Iron", 6: "Iron"}[self.dice.d6()]
            locked = self.dice.d6() <= 3
            trapped = self.dice.d6() == 1
            lines.append(f"{material} door, {'locked' if locked else 'unlocked'}, {'trapped' if trapped else 'untrapped'}.")

        node = Node(id=self._id(), kind="door", level=level, lines=lines)
        node.children.append(self.dispatch_beyond(payload["beyond"], level))
        return node

    # -- stairs ---------------------------------------------------------------

    def resolve_stairs(self, level: int) -> Node:
        value, entry = STAIRS_TABLE.roll(self.dice)
        payload = entry.payload
        new_level = level + payload["level_delta"]
        node = Node(id=self._id(), kind="stairs", level=level,
                    lines=[f"[Stairs d20={value}] {payload['text']}"])
        node.children.append(self.dispatch_beyond(payload["beyond"], new_level, payload.get("modifier", 0)))
        return node

    # -- rooms ------------------------------------------------------------------

    def resolve_room(self, level: int, modifier: int = 0) -> Node:
        shape = roll_room_shape(self.dice)
        node = Node(id=self._id(), kind="room", level=level,
                    lines=[f"[Room d20={shape['roll']}] {shape['text']}"])
        self.rooms_created += 1

        size_bonus = self._room_size_bonus(shape["dims"])
        value, entry = ROOM_CONTENTS_TABLE.roll(self.dice, modifier + size_bonus)
        node.lines.append(f"[Room Contents d100={value}]")
        node.lines.extend(self._room_contents_lines(entry.payload, level))

        extra_exits = max(0, shape["exits"] - 1)
        for _ in range(extra_exits):
            if self.budget_exhausted():
                node.children.append(self._edge_node(level))
                continue
            is_door = self.dice.chance(50)
            node.children.append(self.dispatch_beyond("door" if is_door else "passage", level))
        return node

    @staticmethod
    def _room_size_bonus(dims: tuple[int, int]) -> int:
        longest = max(dims)
        if longest >= 130:
            return 30
        if longest >= 90:
            return 15
        return 0

    def _room_contents_lines(self, payload: dict, level: int) -> list[str]:
        tag = payload["tag"]
        lines: list[str] = []
        tier = treasure_tier_for_level(level)

        def roll_extras(loot_key="loot_pct", clue_key="clue_pct", secret_key="secret_door_pct",
                         npc_key="npc_pct", boon_key="boon_pct"):
            if payload.get(loot_key) and self.dice.chance(payload[loot_key]):
                lines.append(f"Loot: {generate_treasure(self.dice, tier)[0]}.")
            if payload.get(clue_key) and self.dice.chance(payload[clue_key]):
                lines.append(f"Clue: {generate_clue(self.dice)}.")
            if payload.get(secret_key) and self.dice.chance(payload[secret_key]):
                lines.append("There's a secret door hidden in this room.")
            if payload.get(npc_key) and self.dice.chance(payload[npc_key]):
                lines.append(f"An NPC is present: {generate_npc(self.dice, level)}.")
            if payload.get(boon_key) and self.dice.chance(payload[boon_key]):
                lines.append("A minor boon can be found here.")

        if tag == "deadly_encounter":
            lines.append(f"{encounter_description('Deadly')}. Roll the loot table appropriate to the encounter.")
            roll_extras()
        elif tag == "bbeg_remnants":
            lines.append("Remnants / proof of the boss or BBEG - it looks as though they've been up to mischief here.")
        elif tag == "encounter":
            note = f" ({payload['note']})" if payload.get("note") else ""
            lines.append(f"{encounter_description(payload['difficulty'])}{note}.")
            roll_extras()
        elif tag == "hazard":
            lines.append(f"Dungeon hazard: {generate_hazard(self.dice)}.")
        elif tag == "npc_investigating":
            lines.append(f"An NPC is here, investigating something: {generate_npc(self.dice, level)}. "
                         f"They seem to be looking into {generate_clue(self.dice)}.")
        elif tag == "trapped_victim":
            alive = self.dice.chance(payload["alive_pct"])
            lines.append("A previously triggered trap caught a Hard-encounter victim here"
                         f" - {'still alive' if alive else 'now dead'}.")
            roll_extras()
        elif tag == "obstacle":
            lines.append("An obstacle blocks the way (rubble, crevasse, sinkhole, underground stream, "
                         "wild magic field...) - an Athletics/Acrobatics check may be needed, or it may be impassable.")
        elif tag == "dying_npc":
            lines.append(f"A near-death NPC lies here (1d4 levels below you, minimum 1): {generate_npc(self.dice, max(1, level - 1))}. "
                         "A battle clearly happened - they fought something powerful, lost, but damaged it.")
            roll_extras()
        elif tag == "creatures_fighting":
            difficulty = "Easy" if self.dice.d4() <= 2 else "Medium"
            lines.append(f"Two creatures ({difficulty} each) are fighting each other as you arrive. "
                         "You have advantage on stealth checks while they're distracted.")
        elif tag == "runes":
            lines.append("Deserted, but for strange runes and symbols on the floor. Magical? Perhaps.")
        elif tag == "strong_npc":
            attitude_roll = self.dice.d4()
            npc = generate_npc(self.dice, level + self.dice.roll(4, modifier=1))
            if attitude_roll <= 2:
                lines.append(f"A strong NPC ({npc}) has just defeated a Deadly encounter and tells you to begone, "
                             "though they'll agree to go separate ways if pressed.")
            else:
                lines.append(f"A strong NPC ({npc}) has just defeated a Deadly encounter and offers to team up "
                             "for the rest of this dungeon, splitting the loot (CR of later encounters +1d4).")
            roll_extras()
        elif tag == "empty_mission_loot":
            lines.append("Empty.")
            roll_extras()
        elif tag == "relic":
            lines.append("An accursed or blessed relic sits here, guarded by a Deadly encounter. "
                         "Its true nature is unclear.")
        elif tag == "boss":
            lines.append("BOSS / BBEG / significant NPC encounter!")
            if self.dice.chance(payload["loot_pct"]):
                if self.dice.d20() <= 14:
                    rolls = self.dice.d4()
                    items = generate_treasure(self.dice, tier, rolls=rolls)
                    lines.append(f"Loot: {'; '.join(items)}.")
                else:
                    lines.append(f"Loot: {generate_hoard(self.dice, tier)}.")
        return lines
