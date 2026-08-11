"""Data structures for the generated dungeon tree."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Node:
    """One explored feature: a room, a passage run, a door, a staircase, ..."""

    id: int
    kind: str  # "start" | "room" | "passage" | "door" | "stairs" | "edge" | "dead_end"
    level: int
    lines: list[str] = field(default_factory=list)
    children: list["Node"] = field(default_factory=list)

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass
class Dungeon:
    """A complete generated dungeon: metadata plus the explored node tree."""

    dungeon_type: str
    size_label: str
    target_rooms: int
    seed: int | None
    root: Node
    room_count: int = 0
    node_count: int = 0

    def all_nodes(self):
        yield from self.root.walk()
