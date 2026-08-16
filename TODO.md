# Open items

Written down at the end of a long session of map-fidelity work, so the
context doesn't have to be rediscovered. Ordered roughly by how much each one
changes what you actually see on the map.

Everything here is *known and deliberate*, not a discovered-but-unreported
bug. Measurements are from the state at commit `2642091` unless said
otherwise; re-measure before trusting them, the numbers move.

---

## 1. ~~One empty island drops the whole level to the fallback renderer~~ (done)

Fixed. Across 40 seeds, levels drawn by dungeongen went **35% → 100%**; 54% of
islands (162 of 299) have no rooms, which is why one bail cost so much.

What made a room-less island a special case: dungeongen's adapter normalizes
what it is given by `-Dungeon.bounds[0]`, and `Dungeon.bounds` is computed from
**rooms alone** - with none it is a placeholder box at the origin, so the island
was rendered at its raw grid position. Islands sit side by side, so a late one
lands thousands of map units out and trips dungeongen's internal ±3200 limit,
which on the native side is a **segfault**, not an exception.
`render_island_svg` now does that normalization itself in exactly that case.

Two things found on the way, both real:

- `island_extent_map_units` measured rooms and links only, so a room-less
  island - all corridors - reported an extent of zero and walked straight past
  the crash guard. It measures everything handed over now.
- It was also seeded with the origin, so it measured *distance from the
  origin* rather than the island's own size, and refused perfectly renderable
  islands late in a level. Everything is normalized before dungeongen sees it,
  so only the size can trip the limit. Size-guard refusals over the sweep:
  189 → 4.

Cost: the pages got heavy. Seed 72 goes 289 KB → 5.3 MB, because dungeongen's
art is vector hatching and there is now a lot more of it. Over 20 seeds: median
1.48 MB, max 6.3 MB (seed 14), none near the 16 MB artifact ceiling, and a page
still loads in ~0.24s locally. Worth revisiting if it grows - see item 7.

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

Requested behaviour, only partly implemented. When a passage runs into
something already on the map, it should connect there rather than stop, and
the log should say so. Draw order decides which of the three cases applies:

- a **room** that doesn't fit because a passage is already there → the room is
  not placed (this part already happens);
- a **passage arriving at a room that is already drawn** → the passage becomes
  an additional entrance to it, a secret one;
- a **passage crossing another passage** → that branch finishes generating,
  and the two form a crossing.

The machinery for the third case now exists but is only used at a branch's
*takeoff*. `_claim_takeoff_cell` extends a branch back one cell so it shares
the cell it leaves from, because dungeongen's adapter only calls a cell a
crossing when two passages occupy the same cell - short of that it walls them
apart. A branch that runs into another corridor at its *far* end still gets
no such treatment, so a crossing the generator never declared is still drawn
as two separate corridors. The same helper should extend to that end once the
layout decides what an arriving passage means (an intersection to record in
the log, not just cells to merge).

## 5. Rooms that find nowhere to go are up to 16%

Was 13.2% (60 seeds x 2 depths). The wall-feature rows now give the passage a
50% chance of carrying on past a door or an opening rather than stopping
there, so passages run longer and the map gets more crowded: 114 rooms of 713
have no clear spot along their own entry wall, against 90 of 684 before.

Each one says so in its own log entry, which is the invariant that matters,
but they are still rooms the dice rolled and the map does not show. The lever
is not the margin (already 0) - it is that a room only ever tries positions
along the wall it was entered from. Letting it try the far side of its own
corridor, or shortening the corridor, would find room for some of them.

## 6. One link in 211 still meets its rooms only at a corner

Left unresolved in `2642091`. Counted over links that leave a declared room
exit: 210 meet both rooms squarely, 1 doesn't. Not diagnosed.

## 7. Cell-conversion machinery in `dungeongen_bridge.py` is now mostly pass-through

Already written up in that module's own docstring - see the `TODO (pending
cleanup...)` block there for which functions are affected and why this must
not be ripped out reflexively.

## 8. ~~Cost of a passage continuing past a side opening~~ (absorbed by item 1)

Making a wall feature a side branch (rather than a turn of the trunk) means
the passage carries on past it, which explores more of the dungeon. The cost
measured at the time was almost entirely the extra empty islands it created:
levels drawn by dungeongen 38% → 32%. Item 1 removed that penalty
entirely - empty islands no longer cost a level its art - so this is closed.

What remains of it is page weight, not coverage: more islands drawn means more
SVG, which is the 5.3 MB in item 1. If that becomes the problem, the lever is
dungeongen's own hatching density, not how the passage branches.

---

## Invariants currently held

Re-check these after any change to layout or the bridge; they are what the
recent work bought, and they are cheap to verify (60 seeds x 2 depths):

- every coordinate the layout produces is an integer
- no two rooms overlap
- no room exit sits off its own wall
- every room is drawn, or says in the log why it isn't, or sits behind a node
  that does
- no corridor or link segment runs diagonally
- every corridor the layout drew reaches dungeongen (or is already covered,
  cell for cell, by something that did)
- every link starts on its from-room's wall and ends on its to-room's
- no dungeongen hangs *or segfaults* across the seed sweep

Measured at the state this list was last rewritten, 60 seeds x 2 depths:
713 rooms, 114 of them unplaceable (16.0%), 28442 coordinates, 4869 segments,
937 room pairs, 1169 exits, 157 links - all clean. Hang sweep: 1987 islands,
0 hangs, 2 refusals which are all the deliberate size guard. Levels drawn by
dungeongen: 127 of 128 (99%) - the one that falls back has an island past the
size limit, which is the guard doing its job.

Run the hang sweep with **empty islands included**. It used to skip them
(`if not island["rooms"]: continue`) - which is exactly where the segfault in
item 1 was hiding, so the sweep that was supposed to catch it never looked.
That is also why the island count jumped from 932 to 2086.
