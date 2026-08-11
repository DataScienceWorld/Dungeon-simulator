from dungeon_simulator.dice import Dice


def test_roll_range():
    dice = Dice(seed=1)
    for _ in range(200):
        assert 1 <= dice.roll(6) <= 6


def test_expr_parsing():
    dice = Dice(seed=1)
    for _ in range(200):
        value = dice.expr("2d6+3")
        assert 5 <= value <= 15


def test_expr_no_count():
    dice = Dice(seed=1)
    for _ in range(200):
        assert 1 <= dice.expr("d4") <= 4


def test_chance_bounds():
    dice = Dice(seed=42)
    assert all(dice.chance(100) for _ in range(50))
    assert not any(dice.chance(0) for _ in range(50))


def test_seed_reproducibility():
    a = Dice(seed=123)
    b = Dice(seed=123)
    seq_a = [a.d20() for _ in range(50)]
    seq_b = [b.d20() for _ in range(50)]
    assert seq_a == seq_b
