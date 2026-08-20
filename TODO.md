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

## 4. Passage intersections - two of the three cases done

Draw order decides which case applies:

- a **room** that doesn't fit because a passage is already there → **done**:
  a candidate footprint covering a cell some corridor already runs down is
  rejected, and if no position along the entry wall is clear the room is not
  placed (and says so in its own entry). The claim that this "already
  happened" was wrong - placement only ever checked room against room.
- a **passage arriving at a room already drawn** → **done**: it stops at that
  wall and is recorded as a secret entrance to the room, with the log saying
  which room it broke into; everything past that point of the branch is not
  drawn. It is marked on the map too: the bridge hands it to dungeongen as a
  plain breach in the wall, which draws like any ordinary exit, so the overlay
  puts the same "S" on it that a secret door gets. Seed 72 has ten of them
  against two secret doors, which is why marking only the doors was not
  enough - passage 15's break-in to room 14 read as a normal doorway.
  It is also no longer handed over *at all*. dungeongen's `Exit` is not a
  neutral wall breach - its own docstring calls it "a skewed inverted U
  archway extending away from the dungeon", and it draws that: a perspective
  archway sticking out of the wall, announcing the way out. Removing it
  leaves the wall solid, which is what a hidden way in should look like and
  the same rule a secret door already follows. A side effect worth having:
  the adapter excludes exit cells from passages, so the arriving corridor
  gets back the cell the archway was eating (item 2, for this case).
- a **passage crossing another passage** → still only handled at a branch's
  own *takeoff*, not where one runs into another at its far end.

Between the first two, corridor cells sitting inside a room's floor went from
11.9% to 1.27% (40 seeds). What is left is a passage that *began* inside a
room - because whatever dispatched it was already in there - and dead-end
stubs, which move without going through the same clipping.

Cost: rooms with nowhere to go went 16.0% → 20.3%. Rooms and corridors now
compete for the same ground and the corridor, being there first, wins. The
lever is not the rule but how little freedom a room has: it only tries
positions along the wall it was entered from, so shortening its corridor or
letting it sit further along would find space for many of them.

### Arm-to-arm through a crossing

`_claim_takeoff_cell` extends a branch back onto the cell it leaves from, so
every arm shares a cell with its trunk - dungeongen's adapter only calls a
cell a crossing when two passages occupy the same one. Each arm is therefore
connected to the junction. Walking *between* two arms through the junction
still is not guaranteed: where several passages overlap that cell, the
adapter sometimes leaves their segments unconnected to each other. That is
inside its own `_convert_passage` splitting, and it is what
`test_the_four_way_is_one_connected_region_in_dungeongens_own_model` stops
short of asserting.

## 4b. A secret entrance on a hole the room already has

7 of 72 secret entrances (60 seeds, 9.7%) land on a spot where the room
*already* declares an ordinary opening - same room, same cell. Seed 1's room
313 has both a plain exit and a secret break-in at (67, 13).

Nothing is hidden there: the wall is already open, and the overlay puts an
"S" on a visible doorway. The log says "ingresso segreto" about it too.

This is a layout question, not a bridge one - what should happen is that a
passage arriving where the room already opens is *not* a secret entrance at
all, it simply met the room at its own exit, and both the log and the mark
should say that instead. Left alone because it changes what the generator
narrates, not just what is drawn.
`test_a_secret_entrance_does_not_breach_the_wall_in_dungeongen` skips exactly
this case, and says so.

## 4c. Stairs get an alcove of their own

The steps are drawn in a one-cell **room** rather than a passage, and that is
what gives them walls. dungeongen draws a wall only along the outline of a
region, so two touching floor cells inside one region have nothing to draw
between them: as a passage, a stairs cell running alongside another corridor
(32% of them - 60 of 185 over 40 seeds) had no wall on that flank at all. A
room draws its own outline whatever region it sits in, which is where the
three walls come from.

Seed 72's stairs 23, longest ink-free run per edge, steps stripped so that
only wall counts:

| | N | S | E | W |
|---|---|---|---|---|
| as a passage | 15% open | 0 | 14% | 0 |
| as an alcove | **0 - solid** | 0 | **15% - the way in** | 0 |

The way in is the same three pieces dungeongen uses for any room off a
corridor, and **all three are needed together**: the room, a `Passage` that
*ends* in it, and a **closed** `Door` between them carrying that passage's id.

That took several wrong turns worth recording, because each failed silently:

- a chip on its own opens nothing. An `Exit`, or a door with no passage
  terminating at it, leaves the alcove **sealed on all four sides** - 0%
  opening on every edge. A chip is made to sit in a wall two floors already
  reach; it does not cut one by itself.
- hiding the glyph does not help either, and for the same reason: what reads
  as an opening is the glyph, so an `Exit` with its archway suppressed is just
  a sealed box. (That version was committed and reverted - `4526914`,
  `9946cc3`.)
- the door must face **into** the alcove, away from the corridor. The other
  way round measures 0% on all four edges, exactly like no door at all.
- an **open** door would merge the regions and take the walls with it, the
  same reason a secret door goes over closed.

Two measurements misled me for a while and are worth not repeating: the
staircase's own widest step line sits **on the cell edge**, so a pixel scan
counts it as wall - strip the props before measuring; and
`_quieten_stair_alcoves` *re-adds* a missing staircase, so stripping before it
runs does nothing.

Three guards this needed, each a real failure first:

- an alcove whose cell falls inside a room is not created at all - it would be
  a room drawn inside a room, and two overlapping rooms handed to dungeongen.
- two stairs can be walked onto the same cell; the second gets no alcove (the
  stair itself is still handed over).
- `_convert_stair` looks for a passage before a room and falls back to
  `passages[0]`, so with stairs no longer being passages the staircase could
  land on an unrelated corridor or be dropped outright.
  `_quieten_stair_alcoves` puts it back, or rebuilds it. Alcoves without their
  steps: 0 of 116.

Identifying an alcove by size ("the only room one cell across") was wrong -
real rooms come out 1x1 too. It is done by position now, against the stair
cells the dungeon was built from.

The door is not drawn. It has to *exist* - that is what keeps the alcove its
own region - but no die rolled it, and dungeongen puts its leaf in the middle
of the cell, on top of the staircase: seed 72's stairs 23 show two steps with
it on and three with it off. Silencing it costs nothing, and that is the part
worth knowing: the opening is the door's chip meeting the passage that ends
there, and the region paints that itself, so the edges measure the same either
way (N/S/W solid, E open at 15%). That separation only holds in this
arrangement - a chip with no passage terminating at it opens nothing, glyph or
no glyph, which is what the sealed version shipped.

Its chip is not dungeongen's either, and for a separate reason. The chip is
not decoration - it *is* the opening, the floor that bridges the wall - but
dungeongen's is a rounded lobe a third of a cell across, drawn to sit
half-hidden inside a room of ordinary size. In one cell there is nowhere for
it to hide: it bulges into the middle of the floor and reads as a pear stuck
to the doorway. Moving the door out to the boundary cell hides the lobe but
**seals** the alcove, so the shape had to change, not the position. It is a
plain rectangle straddling the wall now. Alcoves with exactly one side open,
over 20 seeds: **13 -> 110**, none sealed; six open on more than one side,
where the cell abuts something that reaches into it.

The staircase is drawn smaller than dungeongen draws it, at
`_ALCOVE_STAIR_SCALE` of the cell. Its own six treads run the full width with
the widest sitting exactly on the cell boundary (`y = -CELL_SIZE/2`, plus an
overhang to cover the grid dots) - right for a passage, whose walls the treads
should meet, but in the alcove that boundary is the doorway, so the top tread
landed across the opening and closed it. Measured on the east edge of seed
72's stairs 23: **15% open with the steps stripped and 0% with them drawn**,
i.e. the staircase, not the wall, was sealing it. Inset, it is 14% either way.

### The doorway overshoots the wall by one thickness, and cannot do less

The chip that opens the alcove reaches one `border_width` past the wall, and
the alcove's north wall visibly runs that far into the corridor: measured on
seed 72's stairs 23, its north wall reaches 0.14 of a cell past the corner
against 0.07 for its own south wall, which has no doorway.

That is the floor, not a value left untuned. The alcove and the corridor are
separate regions, so each outlines what it owns and the part of the chip past
the wall gets outlined too - but squaring the chip off *at* the line, or at
half a thickness, makes the alcove measure **shut on all four sides**: a
region has to clear its own wall stroke before it reads as open. One thickness
is the least that opens it, and
`test_the_alcove_doorway_overshoots_the_wall_by_exactly_one_thickness` pins
both ends, failing at a deeper chip and at a flush one.

Getting rid of the overshoot for good means the corridor's region supplying
the outer half, the way dungeongen's own door splits `_left_group` /
`_right_group` between the two sides. Handing our chip out whole is what makes
the alcove own both halves. The obstacle is that those halves meet at the
door's centre, and on the alcove's cell that centre is half a cell inside the
wall; putting the door on the corridor cell instead - where dungeongen puts it
for every ordinary room - has been measured three times and comes out sealed.

**A warning about measuring any of this.** `_make_regions` inflates every
shape by `REGION_INFLATE` (CELL_SIZE * 0.025) before drawing, so probing a
region for "is this side open" says yes on all four sides of every alcove - 42
of 43 over eight seeds. A probe further out stops saying yes only where the
chip protrudes, which reads like an opening test and is really a protrusion
test: an earlier version of the test above was written that way and duly
failed the flusher chip as a regression. Measure the rectangle handed over, or
scan the rendered wall line; do not ask the region.

## 4d. Stairs walled off from their own trunk (superseded, re-measure)

The steps now have a floor - a stairs node emits a corridor for the length it
walks, so its 10ft cell exists and dungeongen's own `StairsProp` (a 1x1 cell
of drawn steps) can be hung off it. Before that they sat on nothing: 84% of
stairs were on no corridor and no room at all, and the adapter's
`_convert_stair` would have dumped the prop on `passages[0]` - silently, on an
unrelated corridor somewhere else on the level.

Measured while the stairs were still a passage: in the same connected
region as the corridor they leave from, **2% -> 76%** (4 -> 140 of 185).
That number does not carry over - an alcove is deliberately its own
region now, reached through a closed door - so the connectivity question
needs asking again in the new model before anything is claimed about it.

What is left splits into two, neither of them the same bug:

- the stairs *are* the entrance (parent node is `start`), so there is no
  corridor behind them to join. Correct as drawn.
- the stairs sit behind a **door**, which by design takes no cell of its own,
  so the cell behind them carries no route to claim. This is the real one, and
  it is the door-connection problem from item 2 seen from the other side.

27 stairs have a takeoff cell no other route occupies, which is the union of
those two cases.

## 5. Rooms that find nowhere to go are 10.2%

72 of 708 (60 seeds x 2 depths), down from 19.4%. It was 9.9% before the
stairs got a corridor of their own - two more rooms now lose their ground
to one, which is the same competition item 4 describes. Each says so in its own log
entry, which is the invariant that matters.

The budget they used to waste is recovered: after each breadth-first wave the
generator asks the layout what it cannot draw and stops exploring there - not
only past an unplaceable room, but past a passage that runs into a room
already on the map or begins inside one, and past an exit whose wall has no
cell left. Nodes sitting behind something the map never reaches: 34.6% → 0%.
A cut room is also taken back off the room budget, which is what lets the
freed rolls go to branches that can be drawn.

The remaining lever is how little freedom a room has - it only ever tries
positions along the wall it was entered from, so shortening its corridor or
letting it sit further along would find space for some of the rest.

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
- a secret entrance opened by an arriving passage sits on that room's wall,
  and is marked "S" there - it is not a door and does not come off the door
  table, so nothing else on the map would say it is secret
- and it does not breach that wall in dungeongen: an `Exit` there draws an
  archway announcing the way out, over the very wall it is meant to hide in
- two rooms joined by nothing but a door keep the wall between them (an
  *open* door in dungeongen merges their regions and erases it)
- a passage rolled with no length of its own says in the log that it still
  takes the minimum 10ft
- nothing is generated past a point the map cannot reach - an unplaceable
  room, a passage that runs into one, an exit with no room on its wall - and
  the node where it stops says so
- every stairs node stands on a corridor cell of its own, and the cell
  recorded for it is one that corridor covers (the walk's end *point* is
  one cell past its last cell whenever it ran forwards)
- a stairs marker names the room or passage it comes out in, and the level
- a secret door goes to dungeongen *closed*, never secret: its adapter turns
  a secret door into an open one, which erases the wall it hides in
- no dungeongen hangs *or segfaults* across the seed sweep

Measured at the state this list was last rewritten, 60 seeds x 2 depths:
708 rooms, 72 of them unplaceable (10.2%), 30748 coordinates, 5190 segments,
861 room pairs, 1371 exits - all clean. Corridor cells inside a
room's floor: 1.72%. Nodes behind something the map never reaches: 0%. Hang
sweep: 1784 islands, 0 hangs, 6 size refusals. Levels drawn by dungeongen:
120 of 120 (100%).

Run the hang sweep with **empty islands included**. It used to skip them
(`if not island["rooms"]: continue`) - which is exactly where the segfault in
item 1 was hiding, so the sweep that was supposed to catch it never looked.
That is also why the island count jumped from 932 to 2086.
