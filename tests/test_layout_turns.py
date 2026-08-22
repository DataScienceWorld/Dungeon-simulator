"""Una svolta a 90 gradi e' una L da 3 celle, non una tacca sull'angolo.

"Passage turns right 90 degrees" e' un gomito da 30ft: una cella nella
direzione di prima, la cella d'angolo, e una nella direzione nuova, dopo la
quale il passaggio prosegue di la'. Sul reticolo i due bracci non sono lunghi
un'unita' ciascuno, perche' una cella si prende dal lato *oltre* la linea da
cui la si percorre: quale braccio voglia l'unita' in piu' dipende dal segno
delle due direzioni, ed e' quello che `_turn_lead` sa.
"""
import collections

import pytest

from dungeon_simulator import dungeongen_bridge as bridge
from dungeon_simulator.generator import DungeonGenerator
from dungeon_simulator.layout import _VECTORS, _rotate, _turn_lead, compute_layout

SEEDS = range(40)
HEADINGS = ("N", "E", "S", "W")
_BY_VECTOR = {(0, -1): "N", (0, 1): "S", (1, 0): "E", (-1, 0): "W"}


def _elbow_cells(old, new, l1, l2):
    """Le celle che dungeongen ricava da un gomito con bracci lunghi l1 e l2."""
    dx, dy = _VECTORS[old]
    ex, ey = _VECTORS[new]
    p0 = (10.0, 10.0)
    p1 = (p0[0] + dx * l1, p0[1] + dy * l1)
    p2 = (p1[0] + ex * l2, p1[1] + ey * l2)
    return bridge._path_cells(bridge._grid_cell_path(bridge._dedupe([p0, p1, p2])))


def _bends(cells):
    return len({c[0] for c in cells}) > 1 and len({c[1] for c in cells}) > 1


def _collapse(points):
    """I punti allineati fusi: un cambio di larghezza spezza il tratto a meta'
    di un braccio, e quello non e' una svolta."""
    out = []
    for point in bridge._dedupe([tuple(p) for p in points]):
        while len(out) >= 2:
            a, b = out[-2], out[-1]
            if (a[0] == b[0] == point[0]) or (a[1] == b[1] == point[1]):
                out.pop()
            else:
                break
        out.append(point)
    return out


def _leg(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = abs(dx) + abs(dy)
    return _BY_VECTOR[(int(dx / length), int(dy / length))], int(length)


def _turns(seeds=SEEDS):
    """Ogni svolta di ogni passaggio: (seme, nodo, bracci, celle, terminale)."""
    for seed in seeds:
        dungeon = DungeonGenerator(seed=seed, limitless_room_cap=20).generate()
        layout = compute_layout(dungeon)
        for islands in layout.values():
            for island in islands:
                merged = collections.OrderedDict()
                for corridor in island["corridors"]:
                    # I tratti di uno stesso nodo sono un passaggio solo: si
                    # spezzano a ogni cambio di larghezza, non a ogni svolta.
                    merged.setdefault(corridor["id"], []).extend(corridor["points"])
                for node_id, raw in merged.items():
                    points = _collapse(raw)
                    for i in range(1, len(points) - 1):
                        a, b, d = points[i - 1], points[i], points[i + 1]
                        cells = bridge._path_cells(
                            bridge._grid_cell_path(bridge._dedupe([a, b, d])))
                        yield {
                            "seed": seed, "node": node_id, "at": b,
                            "incoming": _leg(a, b), "outgoing": _leg(b, d),
                            "cells": cells, "terminal": i + 1 == len(points) - 1,
                        }


@pytest.mark.parametrize("old", HEADINGS)
@pytest.mark.parametrize("direction", ("left", "right"))
def test_turn_lead_is_the_shortest_elbow_the_grid_can_draw(old, direction):
    """Per tutte e otto le svolte, la coppia di bracci che `_turn_lead` chiede
    e' l'unica che da' 3 celle piegate - e sotto quella misura non si piega
    comunque, per quanto lungo sia l'altro braccio."""
    new = _rotate(old, direction)
    want = (_turn_lead(old, incoming=True), _turn_lead(new, incoming=False))

    three = [(l1, l2)
             for l1 in range(1, 7) for l2 in range(1, 5)
             if len(_elbow_cells(old, new, l1, l2)) == 3
             and _bends(_elbow_cells(old, new, l1, l2))]
    assert three == [want], f"{old}->{new}: {three}"

    # Sopra il minimo la piega tiene comunque: e' un pavimento, non una
    # misura fissa, cosi' una svolta dopo 50ft di corridoio resta una L.
    for l1 in range(want[0], 7):
        for l2 in range(want[1], 5):
            assert _bends(_elbow_cells(old, new, l1, l2)), (old, new, l1, l2)
    # Sotto il minimo non si piega mai, nemmeno allungando l'altro braccio.
    for short, other in ((want[0] - 1, want[1]), (want[1] - 1, want[0])):
        if short < 1:
            continue
        pair = (short, other) if short == want[0] - 1 else (other, short)
        for extra in range(0, 4):
            l1, l2 = pair
            l1, l2 = (l1, l2 + extra) if short == want[0] - 1 else (l1 + extra, l2)
            assert not _bends(_elbow_cells(old, new, l1, l2)), (old, new, l1, l2)


def test_right_turn_coming_from_the_south_draws_the_three_cells():
    """L'esempio: vengo da sud, svolto a destra. Cella 1 a nord di dove sono,
    cella 2 a nord di quella e aperta a sud e a est, cella 3 a est della 2 e
    aperta a ovest, e da li' il passaggio prosegue verso est."""
    cells = _elbow_cells("N", "E", _turn_lead("N", incoming=True),
                         _turn_lead("E", incoming=False))
    entry, corner, onward = (10, 9), (10, 8), (11, 8)
    assert sorted(cells) == sorted([entry, corner, onward])
    assert corner == (entry[0], entry[1] - 1)      # la 2 e' a nord della 1
    assert onward == (corner[0] + 1, corner[1])    # la 3 e' a est della 2


def test_every_turn_on_the_map_bends():
    """Sulle mappe vere: nessuna svolta e' una tacca. L'unica eccezione e' il
    gomito amputato da una stanza gia' disegnata, che puo' solo essere l'ultimo
    tratto del passaggio - il tracciato si ferma li' e lo dice nel registro."""
    seen = flat = 0
    for turn in _turns():
        seen += 1
        heading, length = turn["incoming"]
        # Il braccio in ingresso non e' mai corto: se non ci fosse stato posto
        # per allungarlo, la svolta non sarebbe nemmeno avvenuta.
        assert length >= _turn_lead(heading, incoming=True), turn
        if not _bends(turn["cells"]):
            flat += 1
            assert turn["terminal"], turn
            continue
        assert len(turn["cells"]) >= 3, turn
    assert seen > 100, seen
    # Misurato: 124 svolte su 40 semi, 4 amputate da una stanza.
    assert flat <= seen // 10, (flat, seen)
