# Open items

Written down at the end of a long session of map-fidelity work, so the
context doesn't have to be rediscovered. Ordered roughly by how much each one
changes what you actually see on the map.

Everything here is *known and deliberate*, not a discovered-but-unreported
bug. Measurements are from the state at commit `2642091` unless said
otherwise; re-measure before trusting them, the numbers move.

---

## 1. One empty island drops the whole level to the fallback renderer

`_dungeongen_level_svg` returns `None` if **any** island on the level has no
rooms, so the level falls back to the RoughJS renderer. Islands with no rooms
are common: a stairs or portal branch that never reaches a room becomes one.

Seed 72, explored fully (no `--max-depth`), 40 rooms across 5 levels:

| level | rooms | islands | empty | dungeongen art |
|-------|-------|---------|-------|----------------|
| -1    | 1     | 2       | 1     | no             |
| 0     | 1     | 4       | 3     | no             |
| 1     | 21    | 3       | 1     | no             |
| 2     | 6     | 16      | 10    | no             |
| 3     | 1     | 1       | 0     | **yes**        |

One level out of five, and not because of size - purely because of empty
islands. Across 40 seeds only ~32% of levels get dungeongen's art.

This is the single biggest lever on how much of the map gets the good
rendering. Options: skip empty islands when handing the level over, or let
the overlay draw them on its own.

Watch out: `test_dungeongen_level_svg_returns_none_when_any_island_has_no_rooms`
encodes today's behaviour on purpose and has to be rewritten, not deleted -
whatever replaces it still has to guarantee the stairs/dead-end markers on
those islands don't silently vanish.

## 2. The doorway glyph eats the first cell of a corridor

Where a passage leaves a room, dungeongen draws its `Door` occupying the
passage's **first cell**. A 30ft corridor therefore reads as 10ft of threshold
plus 20ft of corridor - the "strettoia" reported on seed 72's passage 13, west
of room 6.

It is not spurious length: the roll really is 30ft and the cells really are 3.
And the `Door` is not decoration either - in dungeongen's model a door is the
only thing that connects a passage to a room (`Map._trace_connected_region`
walks *through* doors), so simply not emitting it walls the corridor off from
the room it belongs to.

Open question: can the archway sit on the room's wall line instead of claiming
a cell of the corridor? Depends on how `_create_passage_with_doors` trims door
cells out of the path; expect a few rounds to get it without breaking the
connection.

## 3. `_door_direction` resolves an exact diagonal the wrong way

```python
if abs(dx) > abs(dy):        # a tie falls through to north/south
```

A door sitting exactly diagonal from its room's centre always comes out
north or south. Seed 72: room 6's centre is (13.5, 13.5) and its **west** door
at (11, 11) gives dx = dy = -2.5, so it is handed over as `north`.

Invisible today - dungeongen's adapter orients the glyph from the path
direction and ignores this field - but it is wrong, and it will bite whenever
something starts reading it. The direction should come from where the passage
actually goes, not from a comparison against the room's centre.

## 4. Passage intersections (feature, not a bug)

Requested behaviour, not implemented at all yet. When a passage runs into
something already on the map, it should connect there rather than stop, and
the log should say so. Draw order decides which of the three cases applies:

- a **room** that doesn't fit because a passage is already there → the room is
  not placed (this part already happens);
- a **passage arriving at a room that is already drawn** → the passage becomes
  an additional entrance to it, a secret one;
- a **passage crossing another passage** → that branch finishes generating,
  and the two form a crossing.

## 5. One link in 211 still meets its rooms only at a corner

Left unresolved in `2642091`. Counted over links that leave a declared room
exit: 210 meet both rooms squarely, 1 doesn't. Not diagnosed.

## 6. Cell-conversion machinery in `dungeongen_bridge.py` is now mostly pass-through

Already written up in that module's own docstring - see the `TODO (pending
cleanup...)` block there for which functions are affected and why this must
not be ripped out reflexively.

## 7. Cost of a passage continuing past a side opening

Making a wall feature a side branch (rather than a turn of the trunk) means
the passage carries on past it, which explores more of the dungeon. Measured
over 40 seeds: rooms 343 → 350, islands 242 → 315 (empty ones 129 → 180),
levels drawn by dungeongen 38% → 32%.

Mostly a restatement of item 1 - the cost is almost entirely the extra empty
islands - so fixing that should absorb this too. Worth re-measuring afterwards
rather than assuming.

---

## Invariants currently held

Re-check these after any change to layout or the bridge; they are what the
recent work bought, and they are cheap to verify (60 seeds x 2 depths):

- every coordinate the layout produces is an integer
- no two rooms overlap
- no room exit sits off its own wall
- every room is drawn, or says in the log why it isn't, or sits behind a node
  that does
- no dungeongen hangs across the seed sweep
