"""Seedable dice-rolling utilities shared by every table in the generator."""

from __future__ import annotations

import random
import re

_DICE_RE = re.compile(r"^(\d*)d(\d+)([+-]\d+)?$")


class Dice:
    """Wraps a private ``random.Random`` so a whole dungeon can be reproduced from one seed."""

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def roll(self, sides: int, count: int = 1, modifier: int = 0) -> int:
        return sum(self.rng.randint(1, sides) for _ in range(count)) + modifier

    def d4(self) -> int:
        return self.roll(4)

    def d6(self) -> int:
        return self.roll(6)

    def d8(self) -> int:
        return self.roll(8)

    def d10(self) -> int:
        return self.roll(10)

    def d12(self) -> int:
        return self.roll(12)

    def d20(self) -> int:
        return self.roll(20)

    def d100(self) -> int:
        return self.roll(100)

    def expr(self, expression: str) -> int:
        """Roll a standard dice expression such as ``"2d6+3"`` or ``"1d4"``."""
        match = _DICE_RE.match(expression.strip().replace(" ", ""))
        if not match:
            raise ValueError(f"Invalid dice expression: {expression!r}")
        count_s, sides_s, modifier_s = match.groups()
        count = int(count_s) if count_s else 1
        modifier = int(modifier_s) if modifier_s else 0
        return self.roll(int(sides_s), count, modifier)

    def chance(self, percent: float) -> bool:
        """``True`` with the given percent chance (0-100), via a d100 roll."""
        return self.d100() <= percent

    def check(self, dc: int, modifier: int = 0) -> tuple[int, bool]:
        """A generic d20 check against a DC. Returns (roll, success)."""
        roll = self.d20()
        return roll, (roll + modifier) >= dc

    def choice(self, seq):
        return self.rng.choice(seq)
