"""Core dungeon generation: walks the tables and builds an explorable tree.

Exploration is breadth-first, not depth-first: dispatch_beyond() never
recurses into a room/passage/door/stairs synchronously. It creates an empty
placeholder Node (so parents can already record it as a child and move on)
and enqueues a job that will fill the placeholder in later. generate() then
drains that queue in FIFO order, so every node at tree-depth N is resolved
before any node at depth N+1 - a room's four exits all get a fair, even
chance to grow before any single one of them is allowed to consume the
whole room budget. The room/node budget check (budget_exhausted) happens
inside each fill_* function, i.e. at the moment a job is actually dequeued -
by then every job discovered earlier in the same or an earlier breadth-first
wave has already been accounted for, so the budget runs out evenly across
sibling branches instead of being monopolized by whichever branch happened
to be explored first.
"""

from __future__ import annotations

from collections import deque

from .content import (
    encounter_description,
    generate_clue,
    generate_hazard,
    generate_hoard,
    generate_npc,
    generate_treasure,
    roll_trap,
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
    RANDOM_ARCHITECTURE_TABLE,
    ROOM_CONTENTS_TABLE,
    SECRET_DOOR_TABLE,
    STAIRS_TABLE,
    STARTING_AREA_TABLE,
    roll_room_shape,
)

DEFAULT_LIMITLESS_ROOMS = 40
DEFAULT_PARTY_LEVEL = 5
MAX_PASSAGE_SEGMENTS = 15
MAX_NODES = 4000


class DungeonGenerator:
    def __init__(self, seed: int | None = None, limitless_room_cap: int = DEFAULT_LIMITLESS_ROOMS,
                 verbose_empty: bool = False, party_level: int = DEFAULT_PARTY_LEVEL,
                 max_depth: int | None = None):
        self.dice = Dice(seed)
        self.seed = seed
        self.limitless_room_cap = limitless_room_cap
        self.verbose_empty = verbose_empty
        self.party_level = party_level
        # Distance from the entrance, in dispatch_beyond() hops (each
        # room/passage/door/stairs counts as one) - an *additional*, simpler
        # cap alongside the Dungeon Size Table's own room-count budget.
        # None means no depth limit (the table roll alone decides size).
        self.max_depth = max_depth
        self._next_id = 0
        self.rooms_created = 0
        self.target_rooms = 0
        self.node_count = 0
        self._queue: deque = deque()

    # -- bookkeeping ---------------------------------------------------

    def _id(self) -> int:
        value = self._next_id
        self._next_id += 1
        self.node_count += 1
        return value

    def budget_exhausted(self) -> bool:
        return self.rooms_created >= self.target_rooms or self.node_count >= MAX_NODES

    def _depth_exceeded(self, depth: int) -> bool:
        return self.max_depth is not None and depth > self.max_depth

    def _edge_node(self, level: int) -> Node:
        return Node(
            id=self._id(), kind="edge", level=level,
            lines=["You sense you've reached the edge of the dungeon. Time to leave!"],
        )

    def _make_edge(self, node: Node) -> None:
        """Turn an already-placed placeholder into an edge node in place -
        used when a job's budget check fails at dequeue time, after the
        placeholder (and its id) already exists in a parent's children."""
        node.kind = "edge"
        node.lines = ["You sense you've reached the edge of the dungeon. Time to leave!"]

    def _run_queue(self) -> None:
        while self._queue:
            job = self._queue.popleft()
            job()

    def dispatch_beyond(self, kind: str, level: int, modifier: int = 0, depth: int = 0) -> Node:
        """Resolve whatever lies beyond a passage/door/stairs, respecting the
        room budget and, if set, the max-depth cap.

        Per the Dungeon Size Table's rule: once the target room count is
        reached, rooms stop having extra exits and passages tend to dead-end.
        `depth` counts hops from the entrance (the start node is depth 0) and
        is an additional, simpler way to bound exploration - unlike the room
        budget it doesn't need dequeue-time fairness, since every node at the
        same depth is capped identically regardless of processing order.

        Returns a placeholder Node immediately - the real content is filled
        in later, breadth-first, by _run_queue(). A cheap upfront check still
        short-circuits to an edge node when a budget is *already* exhausted
        (avoiding pointless queue growth); jobs enqueued while there's still
        room budget left get their own, more up-to-date check when they're
        actually dequeued.
        """
        if kind == "d4_passage_stairs_room":
            roll = self.dice.d4()
            return self.dispatch_beyond({1: "passage", 2: "stairs", 3: "room", 4: "room"}[roll], level, modifier, depth)
        if kind == "d4_passage_room":
            roll = self.dice.d4()
            return self.dispatch_beyond("passage" if roll == 1 else "room", level, modifier, depth)
        if kind == "d4_room_passage":
            roll = self.dice.d4()
            return self.dispatch_beyond("room" if roll <= 2 else "passage", level, modifier, depth)
        if kind == "secret":
            return self.resolve_secret_door(level, modifier, depth)
        if self.budget_exhausted() or self._depth_exceeded(depth):
            return self._edge_node(level)
        if kind == "room":
            return self._enqueue(level, self._fill_room, level, modifier, depth)
        if kind == "passage":
            return self._enqueue(level, self._fill_passage, level, depth)
        if kind == "stairs":
            return self._enqueue(level, self._fill_stairs, level, depth)
        if kind == "door":
            return self._enqueue(level, self._fill_door, level, depth)
        raise ValueError(f"Unknown dispatch kind: {kind!r}")

    def _enqueue(self, level: int, fill, *args) -> Node:
        node = Node(id=self._id(), kind="pending", level=level)
        self._queue.append(lambda: fill(node, *args))
        return node

    def resolve_secret_door(self, level: int, modifier: int = 0, depth: int = 0) -> Node:
        """Roll the Secret Door Table and merge its result into the node beyond.

        The "beyond" node is itself a deferred placeholder (from
        dispatch_beyond), so the prefix lines can't be prepended yet - that
        has to wait until the placeholder's own fill job has actually run.
        Queuing the prepend step right after it keeps the order correct
        without needing the two jobs to know about each other. The secret
        door itself has no Node of its own, so it doesn't add to `depth` -
        whatever's beyond it is at the same distance from the entrance as if
        there were no secret door at all.
        """
        value, entry = SECRET_DOOR_TABLE.roll(self.dice)
        payload = entry.payload
        prefix = [f"[Secret Door d6={value}]"]
        if payload["trapped"]:
            prefix.append(f"Trapped! {roll_trap(self.dice, self.party_level)}.")
        child = self.dispatch_beyond(payload["beyond"], level, modifier=modifier or payload["modifier"], depth=depth)
        self._queue.append(lambda: setattr(child, "lines", prefix + child.lines))
        return child

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
        child = self.dispatch_beyond(start_kind, level=1, depth=1)
        root.children.append(child)

        self._run_queue()

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

    def _fill_passage(self, node: Node, level: int, depth: int) -> None:
        if self.budget_exhausted() or self._depth_exceeded(depth):
            self._make_edge(node)
            return
        node.kind = "passage"
        events = node.geo.setdefault("events", [])
        segments = 0
        while True:
            value, entry = PASSAGE_TABLE.roll(self.dice)
            payload = entry.payload
            tag = payload["next"]

            length_ft = 0
            width_ft = None
            n_value = None
            if payload.get("length_dice"):
                length_ft = self.dice.expr(payload["length_dice"]) * 10
                n_value = length_ft
            elif payload.get("length_fixed") is not None:
                length_ft = payload["length_fixed"]
                n_value = length_ft
            elif payload.get("resize_dice"):
                width_ft = max(payload["resize_min"], (self.dice.roll(6) // 2) * 10)
                n_value = width_ft

            text = payload["template"].format(n=n_value) if "{n}" in payload["template"] else payload["template"]
            node.lines.append(f"[Passage d20={value}] {text}")
            node.lines.extend(self._passage_contents_lines(level))

            # 'shaft' length is a vertical drop, not a horizontal move.
            if tag != "shaft" and length_ft:
                events.append({"type": "move", "length_ft": length_ft})
            if payload.get("turn"):
                events.append({"type": "turn", "dir": payload["turn"]})
            if width_ft is not None:
                events.append({"type": "resize", "width_ft": width_ft})

            if tag == "continue":
                segments += 1
                if segments >= MAX_PASSAGE_SEGMENTS:
                    node.lines.append("The passage keeps going, but you've mapped enough of it for now.")
                    return
                continue

            if tag == "architecture":
                arch_value, arch_entry = RANDOM_ARCHITECTURE_TABLE.roll(self.dice)
                node.lines.append(f"[Architecture d20={arch_value}] {arch_entry.payload}")
                if arch_value == 19:  # Portal - takes you to another, disconnected part of the dungeon
                    sub = self.dice.d4()
                    child = self.dispatch_beyond("passage" if sub <= 2 else "room", level, depth=depth + 1)
                    node.children.append(child)
                    events.append({"type": "child", "turn": None, "portal": True})
                    return
                segments += 1
                if segments >= MAX_PASSAGE_SEGMENTS:
                    return
                continue

            if tag in ("branch_four_way", "branch_t", "branch_side_left", "branch_side_right"):
                if tag == "branch_side_left":
                    branch_dirs = ["left"]
                elif tag == "branch_side_right":
                    branch_dirs = ["right"]
                else:
                    # A T-junction and a four-way intersection both open onto
                    # a *perpendicular* corridor, i.e. both left and right -
                    # a four-way additionally keeps going forward (handled by
                    # falling through to `continue` below), a T doesn't (it
                    # returns instead of looping back for another trunk
                    # segment - there is no "forward" at a T).
                    branch_dirs = ["left", "right"]
                for branch_dir in branch_dirs:
                    child = self.dispatch_beyond("passage", level, depth=depth + 1)
                    node.children.append(child)
                    events.append({"type": "child", "turn": branch_dir})
                if tag == "branch_t":
                    return
                segments += 1
                if segments >= MAX_PASSAGE_SEGMENTS:
                    return
                continue

            if tag == "dead_end_secret":
                if self.dice.chance(40):
                    roll, found = self.dice.check(dc=15)
                    if found:
                        node.lines.append(f"A secret door is found here (Perception {roll} vs DC 15)!")
                        node.children.append(self.dispatch_beyond("secret", level, depth=depth + 1))
                        events.append({"type": "child", "turn": None})
                    else:
                        node.lines.append(f"There's a secret door here, but it goes unnoticed (Perception {roll} vs DC 15).")
                else:
                    node.lines.append("A true dead end.")
                return

            if tag == "secret_door_check":
                roll, found = self.dice.check(dc=15)
                if found:
                    node.lines.append(f"Secret door found (Perception {roll} vs DC 15)!")
                    node.children.append(self.dispatch_beyond("secret", level, depth=depth + 1))
                    events.append({"type": "child", "turn": None})
                    return
                node.lines.append(f"Perception {roll} vs DC 15 - nothing noticed. The passage continues.")
                segments += 1
                if segments >= MAX_PASSAGE_SEGMENTS:
                    return
                continue

            if tag == "shaft":
                sub = self.dice.d4()
                child = self.dispatch_beyond("passage" if sub <= 2 else "room", level + 1, depth=depth + 1)
                node.children.append(child)
                events.append({"type": "child", "turn": None})
                return

            # terminal: door / stairs / room
            child = self.dispatch_beyond(tag, level, depth=depth + 1)
            node.children.append(child)
            events.append({"type": "child", "turn": None})
            return

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
            lines.append(f"Trap! {roll_trap(self.dice, self.party_level)}.")
        elif tag == "loot":
            if self.dice.chance(payload["loot_pct"]):
                tier = treasure_tier_for_level(level)
                lines.append(f"Loot, oddly out of place here: {generate_treasure(self.dice, tier)[0]}. How did this get here?")
            else:
                lines.append("Nothing here after all.")
        return lines

    # -- doors --------------------------------------------------------------

    def _fill_door(self, node: Node, level: int, depth: int) -> None:
        if self.budget_exhausted() or self._depth_exceeded(depth):
            self._make_edge(node)
            return
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

        node.kind = "door"
        node.lines = lines
        node.geo["length_ft"] = 5
        node.children.append(self.dispatch_beyond(payload["beyond"], level, depth=depth + 1))

    # -- stairs ---------------------------------------------------------------

    def _fill_stairs(self, node: Node, level: int, depth: int) -> None:
        if self.budget_exhausted() or self._depth_exceeded(depth):
            self._make_edge(node)
            return
        value, entry = STAIRS_TABLE.roll(self.dice)
        payload = entry.payload
        new_level = level + payload["level_delta"]
        node.kind = "stairs"
        node.lines = [f"[Stairs d20={value}] {payload['text']}"]
        node.geo.update({"length_ft": 10, "level_delta": payload["level_delta"], "to_level": new_level})
        node.children.append(self.dispatch_beyond(payload["beyond"], new_level, payload.get("modifier", 0), depth=depth + 1))

    # -- rooms ------------------------------------------------------------------

    def _fill_room(self, node: Node, level: int, modifier: int, depth: int) -> None:
        if self.budget_exhausted() or self._depth_exceeded(depth):
            self._make_edge(node)
            return
        shape = roll_room_shape(self.dice)
        node.kind = "room"
        node.lines = [f"[Room d20={shape['roll']}] {shape['text']}"]
        node.geo.update({"width_ft": shape["dims"][0], "length_ft": shape["dims"][1], "shape": shape.get("shape", "rect")})
        self.rooms_created += 1
        extra_exits = max(0, shape["exits"] - 1)
        node.lines.append(
            f"Exits: {shape['exits']} ({extra_exits} beyond the way in)."
            if extra_exits else f"Exits: {shape['exits']} (only the way in - no other exits)."
        )

        size_bonus = self._room_size_bonus(shape["dims"])
        value, entry = ROOM_CONTENTS_TABLE.roll(self.dice, modifier + size_bonus)
        node.lines.append(f"[Room Contents d100={value}]")
        node.lines.extend(self._room_contents_lines(entry.payload, level))
        node.geo["content_tag"] = entry.payload["tag"]

        exit_slots = []
        for _ in range(extra_exits):
            slot = ("forward", "right", "left")[len(exit_slots) % 3]
            exit_slots.append(slot)
            is_door = self.dice.chance(50)
            node.children.append(self.dispatch_beyond("door" if is_door else "passage", level, depth=depth + 1))
        node.geo["exit_slots"] = exit_slots

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
