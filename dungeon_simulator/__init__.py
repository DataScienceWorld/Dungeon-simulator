"""Procedural solo-dungeon-crawl simulator.

Implements the dungeon-generation tables (size, type, starting area,
passages, doors, stairs, rooms and their contents) as an explorable,
seedable generator.
"""

from .generator import DungeonGenerator
from .models import Dungeon, Node

__all__ = ["DungeonGenerator", "Dungeon", "Node"]
