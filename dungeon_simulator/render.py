"""Turn a generated Dungeon into human-readable text or a JSON-able dict."""

from __future__ import annotations

from .models import Dungeon, Node

_KIND_LABELS = {
    "start": "ENTRANCE",
    "room": "ROOM",
    "passage": "PASSAGE",
    "door": "DOOR",
    "stairs": "STAIRS",
    "edge": "EDGE OF DUNGEON",
    "dead_end": "DEAD END",
}


def render_text(dungeon: Dungeon) -> str:
    out = []
    out.append("=" * 60)
    out.append("DUNGEON SIMULATOR")
    out.append("=" * 60)
    out.append(f"Type: {dungeon.dungeon_type}")
    out.append(f"Size: {dungeon.size_label}")
    out.append(f"Seed: {dungeon.seed}")
    out.append(f"Rooms generated: {dungeon.room_count} / target {dungeon.target_rooms}")
    out.append(f"Total nodes: {dungeon.node_count}")
    out.append("")
    _render_node(dungeon.root, depth=0, out=out)
    return "\n".join(out)


def _render_node(node: Node, depth: int, out: list[str]) -> None:
    indent = "  " * depth
    label = _KIND_LABELS.get(node.kind, node.kind.upper())
    out.append(f"{indent}- [{label}] (level {node.level}, #{node.id})")
    for line in node.lines:
        out.append(f"{indent}    {line}")
    for child in node.children:
        _render_node(child, depth + 1, out)


def to_dict(dungeon: Dungeon) -> dict:
    return {
        "dungeon_type": dungeon.dungeon_type,
        "size_label": dungeon.size_label,
        "target_rooms": dungeon.target_rooms,
        "seed": dungeon.seed,
        "room_count": dungeon.room_count,
        "node_count": dungeon.node_count,
        "root": _node_to_dict(dungeon.root),
    }


def _node_to_dict(node: Node) -> dict:
    return {
        "id": node.id,
        "kind": node.kind,
        "level": node.level,
        "lines": node.lines,
        "children": [_node_to_dict(child) for child in node.children],
    }
