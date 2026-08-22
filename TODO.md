# Open items

Written down at the end of a long session of map-fidelity work, so the
context doesn't have to be rediscovered. Ordered roughly by how much each one
changes what you actually see on the map.

Everything here is *known and deliberate*, not a discovered-but-unreported
bug. For how the machinery behaves - the traps, the non-obvious contracts, the
measurements that mean something other than they look like - see `LESSONS.md`,
which is the file to keep current as understanding changes. Measurements are from the state at commit `2642091` unless said
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

## 4bis. ~~Adjacent rooms share a wall that draws half again as thick~~ (done)

dungeongen inflates every region by `REGION_INFLATE` (its own
`CELL_SIZE * 0.025` = 1.6px) before drawing it. Two regions side by side are
each inflated *towards* the other, so their outlines end up 3.2px apart and
the two 6px strokes merge into one band half again as wide.

    6.0 (stroke) + 2 x 1.6 (inflation) = 9.2px

Measured on two rooms built by hand straight in dungeongen's own model, no
layout of ours involved, and then again on seed 72:

    shared wall, inflation 1.6:   9.2px
    shared wall, inflation 0.8:   7.5px
    shared wall, inflation 0:     6.0px, centred exactly on the grid line
    free-standing wall, 0:        6.0px, centred exactly on the grid line

It is off now (`_REGION_INFLATE_OVERRIDE`), which is what made the map read
heavy - the stairs alcove worst of all, the band being the same width whatever
the room's size. Seed 72's level-1 island drops from 2.4 MB of SVG to 1.76 MB
as a side effect.

Two things this cost before it worked. The shadow offset was blamed first and
is innocent: zeroing `room_shadow_offset` moves the measurement not at all.
And the constant has to stay swapped for the **whole** render - `_make_regions`
runs inside `Map.render`, so patching around `convert_dungeon` alone changes
nothing, which read as "the setting has no effect".

Whether the inflation had a purpose is a guess: most likely welding a room to
its corridor inside one region so no hairline shows between them. No seam has
turned up without it across the sweep, but that is an absence of evidence, not
a proof. If seams ever appear along a room-to-corridor join, put it back
first.

One good thing fell out: with the inflation off, asking whether a region
reaches past a given wall means something again. At 1.6 the answer was yes on
all four sides of every alcove (42 of 43 over eight seeds), which is how an
earlier test came to measure the doorway's protrusion while believing it
measured the doorway. The answer is now a clean no on all four -
`test_without_region_inflation_an_alcove_measures_like_a_closed_square` - with
the way in painted over the wall afterwards.

## 4e. Two rare geometry residues, both older than the tests that found them

Both turned up when a change to the dice moved the sample, and both were
measured against the commit before that change: they are not new, they were
simply never sampled. Their tests now assert a ceiling instead of zero, so the
day either becomes common the suite says so.

**A door-only link whose two rooms do not share a wall.** Room, door, room,
with no passage between them: the two should end up wall to wall, and a couple
come out a cell apart. Over 80 seeds: 2 of 250 now, 2 of 253 before. Seed 28's
rooms 16 and 76, `(19,11,26,18)` against `(21,8,23,10)` - a clear cell between
them on the y axis. The room is placed at the entry point it was handed, so
the entry itself is a cell short of the wall; where that comes from is not
established. `test_a_door_takes_no_cell_of_its_own`.

**A stairs alcove with a gap in a second wall.** Three walls and one opening is
the rule and holds for the rest; a couple have a second side mostly clear,
because the alcove's cell is welded to a corridor running alongside and no
wall is drawn between them. Over 40 seeds: 2 of 168 now, 1 of 174 before. Seed
1's alcove at (6,12) reads `N 1.0, S 1.0, W 0.13, E 0.0` - W is the welded
side, E the doorway. `test_the_alcove_is_a_square_with_one_opening_and_nothing_in_it`.

## 4f. A secret door in a passage wall is explored but not drawn

The branch behind one is now generated whether or not the party notices it
(the Perception roll says what they saw, not what is there). What is still
missing is the door itself on the map: unlike a secret door from the Door
Table, one the *Passage* Table puts in a wall has no node of its own -
`resolve_secret_door` folds itself into whatever lies beyond - so
`island["doors"]` never hears about it and the overlay has nothing to mark.

Recording one was tried and reverted, because two other things have to be true
first and neither is:

- **the wall has to exist.** The branch and its trunk are welded by the
  takeoff cell, or the branch is a room reached by a link and the door goes
  over OPEN, and either way dungeongen erases the wall. Seed 72's passage 13
  came out with a real gap in the wall at the right cell - which is the one
  thing a secret door must not have.
- **the marker has to land on that wall.** `_door_marker_geometry` puts a
  single-cell door segment on "that cell's leading edge", which for a segment
  that starts *on* the wall and runs into the cell beyond is the far side of
  it - a cell out. The "S" came out in the middle of open floor.

The second looks like a genuine off-by-one in the marker geometry for
single-cell segments in either direction, and is worth settling on its own
before anything is built on top of it.

## 4c. Stairs get an alcove of their own

The steps are drawn in a one-cell **room** rather than a passage, and that is
what gives them walls. dungeongen draws a wall only along the outline of a
region, so two touching floor cells inside one region have nothing to draw
between them: as a passage, a stairs cell running alongside another corridor
(32% of them - 60 of 185 over 40 seeds) had no wall on that flank at all. A
room is not merged into its neighbours' region, so its own outline is drawn
all the way round, and that is where the walls come from - `Room.draw` itself
only marks the corners.

Seed 72's stairs 23, longest ink-free run per edge, steps stripped so that
only wall counts:

| | N | S | E | W |
|---|---|---|---|---|
| as a passage | 15% open | 0 | 14% | 0 |
| as an alcove | **0 - solid** | 0 | 0 | 0 |

Solid on all four, which is what a room off a corridor should be before its
doorway is cut. The three pieces dungeongen uses for any such room are all
still needed together - the room, a `Passage` that *ends* in it, and a
**closed** `Door` between them carrying that passage's id - but they are what
keeps the alcove separate, not what opens it. The way in is painted over the
wall afterwards; see below.

That took several wrong turns worth recording, because each failed silently:

- no chip opens anything, ours or dungeongen's. It took far too long to see
  why: two regions that meet on a grid line are *both* outlined along it, so a
  chip can only add a bump on one side, never cut a hole. An `Exit`, or a door
  with no passage terminating at it, leaves the alcove sealed - and so does a
  door that has one.
- hiding the glyph does not help either, and for the same reason: what reads
  as an opening is the glyph, so an `Exit` with its archway suppressed is just
  a sealed box. (That version was committed and reverted - `4526914`,
  `9946cc3`.)
- the door must still face **into** the alcove, away from the corridor: that
  is the side `_quieten_stair_alcoves` reads to know which wall to paint
  through.
- an **open** door would merge the regions and take the walls with it, the
  same reason a secret door goes over closed. Measured: 77 of 138 alcoves keep
  three walls, 21 keep four, 29 drop to two, one loses all of them.

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

The door is not drawn as a door. It has to *exist*, and closed, because that
is what keeps the alcove its own region - but no die rolled it, and dungeongen
puts its leaf in the middle of the cell, on top of the staircase: seed 72's
stairs 23 show two steps with it on and three with it off.

**The opening is painted, not built, and everything written here before about
a floor chip opening it was wrong.** Two regions that meet on a grid line
always get a wall there: `Map.render` throws every region's outline into one
`unified_border` path and strokes it without unioning, so whatever either side
owns past the line is simply stroked over the other's floor. A chip cannot cut
a hole, only add a bump. Measured on 30 seeds, all 138 alcoves were walled on
all four sides - the "opening" was the outline of our own rectangle sticking
into the corridor, which is exactly what read as a small closed door.

What does work is what dungeongen's own glyph does. `Door.draw` runs at
`Layers.OVERLAY`, after the border has been stroked, and fills its leaf in
`room_color` straight over the wall before stroking it. Fill without that
stroke and what is left is a hole and nothing else. The alcove's doorway is a
rectangle across the wall, one `border_width` deep either side of the line
(the stroke is centred on it, and the drop shadow goes the same way) and
stopping one thickness short of each corner, because the border's round join
reaches a half-thickness along the neighbouring wall and painting over it eats
the corner.

Over 20 seeds, **112 of 112** alcoves now render as a square with exactly one
clear side, and that side the one its door faces. With the chip it was 0 of
112: the doorway side came out between a third and two thirds inked, once
fully. `test_the_alcove_is_a_square_with_one_opening_and_nothing_in_it` scans
the rendered pixels along the four cell edges, because no region shape can see
paint.

The chip is gone entirely - `get_side_shape` returns an empty group.
dungeongen's own would go in as two halves, one per region, and both sit
*inside* the alcove cell, because our door is on the cell rather than on one
of its own; the corridor's outline would then poke into the alcove.

Opening the door instead was measured and rejected: it merges the alcove with
everything its approach passage touches, leaving 77 of 138 alcoves with the
three walls they should have, 21 with four, 29 with two and one with none.

The staircase is drawn smaller than dungeongen draws it, at
`_ALCOVE_STAIR_SCALE` of the cell. Its own six treads run the full width with
the widest sitting exactly on the cell boundary (`y = -CELL_SIZE/2`, plus an
overhang to cover the grid dots) - right for a passage, whose walls the treads
should meet, but in the alcove that boundary is the doorway, so the top tread
landed across the opening and closed it. Measured on the east edge of seed
72's stairs 23: **15% open with the steps stripped and 0% with them drawn**,
i.e. the staircase, not the wall, was sealing it. Inset, it is 14% either way.

### Why the alcove looked swollen where it met the corridor - the corner marks

`Room.draw` brackets a room's four corners: `CORNER_SIZE` long (0.35 of a
cell), set `CORNER_INSET` in from the edges (0.12). Over four or five cells
that is decoration well clear of the walls. In one cell the bracket lands
7.7px from a wall whose stroke already takes 4.6 of them, and the 3px of white
left between them closes under antialiasing - towards the corner the two run
together into a single 20px band, which is what read as the alcove's wall
bulging into the corridor.

The wall itself was never wrong. Measured along the alcove's north wall it is
9.2px centred **exactly** on the grid line, the same as the south wall of
room 14 next to it (13.928..14.073 against 14.927..15.072). Two separate
strokes, each the right thickness, merging - not one thick one.

Alcoves do not draw their corner marks now. Only `draw_corners` goes; the
walls and the staircase still draw.

    x=21.30 before:  14.927..15.072, 15.121..15.154   wall + bracket
    x=21.30 after:   14.927..15.072                   wall alone

### Settled: the doorway no longer reaches past anything

This section used to argue for a chip that overshot the wall by exactly one
`border_width`, and pinned it with a test. Both are gone: there is no chip.
See above - the opening is paint, and paint has no outline.

Two things from it are still worth keeping.

**The alcove's north wall was never lengthened by the doorway**, though an
earlier note said so. Zeroing the chip left seed 72's alcove for stairs #23
measuring exactly the same along its north wall - ink to x=22.14 either way,
against x=21.14 with no alcove at all. What sticks out at that corner is the
corner join of the alcove's own outline.

**Whether a one-cell room's corner join is heavier than an ordinary room's is
still not established.** Two attempts to measure it were contaminated and
should not be repeated in the same form: scanning the alcove's south wall for
comparison picks up the corridor in (22,16) and the surrounding rock rather
than the alcove, and diffing a render against one with the stairs removed
changes dungeongen's decorative RNG, so the difference covers the whole
window. An isolated comparison - the same corner on a 1x1 and on a larger
room, both clear of other geometry - is the way to settle it.

**`_grid_cell_path` returns waypoints, not cells.** A corridor from (20,14)
to (23,14) comes back as `[(20,14), (22,14)]` - the corners - and the cells
between them are implied. Reading that list as "the cells this covers" misses
(21,14) entirely, which is how the cell directly above seed 72's stairs #23
got reported as bare rock twice when corridor 8 and the link from room 1 to
room 28 both run through it. Expand the runs before asking what occupies a
cell.

**A warning about measuring any of this.** Region geometry answers a different
question from the picture. `_make_regions` used to inflate every shape by
`REGION_INFLATE`, so probing "is this side open" said yes on all four sides of
every alcove (42 of 43 over eight seeds); with the inflation off it now says
*no* on all four, correctly, because the doorway is paint the shapes know
nothing about. Scan the rendered wall line for anything about what is drawn -
and strip the props first, since `StairsProp` puts its widest tread on the
cell boundary, and strip them *after* `_quieten_stair_alcoves`, which puts a
missing staircase back.

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

## 8b. Un passaggio largo che ne incrocia un altro: fermarsi e fondersi

Chiesto e **non fatto**. Le altre tre regole sull'allargamento ci sono: dove si
innesta la larghezza in piu' (in mezzo se le celle aggiunte sono pari, dal lato
tirato se sono dispari), l'impronta rivendicata perche' nessuno ci costruisca
sopra, e la fermata quando non c'e' spazio - vedi
[`docs/tabelle/passage.md`](docs/tabelle/passage.md).

Manca il caso in cui l'impronta ne incrocia **un'altra**: la regola voluta e'
*interrompere il passaggio e fondere i due*. Oggi `_clip_wide_run` guarda solo
`_occupied`, cioe' le stanze; due corridoi che si sovrappongono restano due
regioni distinte con un muro in mezzo - lo stesso problema degli incroci, per
cui esiste gia' `_claim_takeoff_cell`.

Da stabilire prima di scriverlo:

- **cosa vuol dire fondere.** Nel modello: le due tratte devono finire nella
  stessa regione di dungeongen, che non guarda la geometria ma le
  `connections`. Il precedente e' `_claim_takeoff_cell`, che fa esattamente
  questo per un ramo e il suo tronco.
- **chi si ferma.** Quello che arriva dopo, presumibilmente, come per le
  stanze: chi disegna prima ha la precedenza.
- **cosa ne e' del resto del ramo.** Se il passaggio si interrompe, i suoi
  figli vanno tagliati come in ogni altra fermata - a meno che "fondersi" non
  voglia dire che si prosegue *dentro* l'altro corridoio.

## 9. Cose che le tabelle dicono e la mappa non sa dire

Un inventario, tabella per tabella, di ogni risultato che produce qualcosa di
reale e che il disegno **non rappresenta, o rappresenta come un'altra cosa**.
Sta qui e non nelle note per tabella (`docs/tabelle/`) perché è lavoro da
fare, non conoscenza acquisita - le note rimandano qui.

Tre categorie, marcate per riga:

- **(A)** sappiamo come si fa, non è fatto;
- **(B)** non sappiamo come si fa con dungeongen;
- **(C)** prima va deciso *se* va disegnato: a una cella da 10ft può non
  leggersi, e una mappa piena di simboli è peggio di una muta.

Ogni voce va chiusa allo stesso modo di tutto il resto: una misura prima, una
misura dopo, e un test che fallisca senza la modifica.

### Door Table

- **(A) Soglie senza battente.** 26-30 *"empty doorway"*, 51-55 *"empty
  archway, no door"*, 96-100 *"smashed and hanging off its hinges"*: il testo
  dice esplicitamente che una porta non c'è, e vengono disegnate col
  rettangolo di porta come tutte le altre. Il come è già in mano:
  `_square_off_doors` riempie di bianco sopra il muro e poi contorna - per una
  soglia vuota basta **non contornare**, esattamente come per l'apertura
  dell'alcova. Da misurare: quante sono (sulle porte disegnate, non su tutte
  le righe) e se un varco senza contorno si distingue da un muro rotto.
- **(C) Grata / saracinesca.** 21-25: sulla mappa è una porta come le altre.
  La convenzione cartografica esiste (una fila di trattini nel varco) e
  dungeongen non ha niente del genere; andrebbe disegnata da noi
  nell'overlay.
- **(C) Materiale e stato.** 61-75 tira legno/pietra/ferro, chiusa/aperta,
  trappolata o no, e lo scrive in chiaro; il disegno è identico. Anche 31-35
  (legno), 36-40 (ferro), 41-45 e 91-95 (pietra) dicono il materiale. Da
  decidere se il materiale merita un tratto diverso o se resta registro.
- **(C) Porta chiusa a chiave, trappolata, che chiede una chiave, di energia
  elementale.** Nessuna di queste ha un segno. Una porta chiusa a chiave e una
  aperta si disegnano uguali, e il giocatore lo scopre solo dal tooltip.

### Room Table

- **(B) Stanza triangolare (15) e trapezoidale (19).** Disegnate
  **rettangolari**. `RoomShape` di dungeongen ha RECT, SQUARE, CIRCLE,
  OCTAGON, T_JUNCTION, CROSS, L_CORNER: un triangolo non c'è. Le opzioni sono
  tenersi il rettangolo (onesto ma falso), passare a OCTAGON (falso in un
  altro modo), o disegnare la forma nell'overlay sopra il pavimento di
  dungeongen. Da misurare quante sono prima di decidere.
- **(B) Caverna grezza (20).** Stessa cosa: `cave` va su RECT. Qui però
  dungeongen ha del crosshatch e delle forme organiche altrove - da verificare
  se una stanza può essere consegnata con un contorno irregolare.
- **(C) L'ingrossamento minimo.** Una stanza più piccola di 2 celle per lato
  viene disegnata a 2 celle dove c'è spazio: la mappa mente sulla misura, e la
  voce del registro dice quella vera. È deliberato e documentato, ma non è mai
  stato verificato quanto spesso accade né quanto si nota.

### Passage Table

- **(A) Un corridoio allargato viene disegnato stretto, e sappiamo come
  rimediare.** La riga 16 tira `(1d6÷2)×10`, minimo 10ft, quindi 20 o 30 ft in
  poco meno della metà dei casi, e la larghezza resta valida da lì in poi. Ma
  l'adattatore di dungeongen **non legge il campo `width`**: misurato
  consegnando lo stesso corridoio con `width` 1, 2 e 3, viene fuori sempre di
  8x1 celle, senza alcun errore. Su 20 seed sono **71 tratti larghi** (47 da 2
  celle, 24 da 3) disegnati stretti.

  *(Nota, perché è stato scritto male una volta: un `ValueError` "Passage must
  be exactly one cell wide" esiste in `map/passage.py`, ma guarda i punti che
  gli si danno, e l'adattatore ne costruisce sempre da una cella - non scatta
  mai. dungeongen non rifiuta niente: ignora.)*

  **La strada è consegnare il tratto largo come una stanza, ed è verificata.**
  Provato con stanza → passaggio → galleria 4x3 → passaggio → stanza:
  `_make_regions` ne fa **una regione sola** (5 elementi), quindi nessun muro
  fra la galleria e i corridoi ai due capi - il timore che venisse una scatola
  sigillata, come era nata l'alcova, era infondato: basta che i due passaggi
  la nominino come `start_room`/`end_room`.

  Resta da fare: spegnere la decorazione d'angolo e il numero di stanza (come
  per l'alcova, `_quieten_stair_alcoves`), decidere cosa succede quando la
  galleria gira, e vedere cosa ne fanno `_claim_takeoff_cell` e la logica
  degli incroci. Le celle vere del tratto sono già registrate in
  `corridors[...]["cells"]`.

  **Due corsie parallele da una cella non funzionano**: misurate, restano due
  regioni distinte, quindi con un muro in mezzo. Quella strada è chiusa.
- **(C) "Narrows to 5 ft" (15).** Invisibile in ogni caso: un corridoio è già
  largo una cella e sotto non si può andare. È la conseguenza diretta della
  regola dei 10ft, quindi o si accetta o si segna la strettoia con un
  simbolo.
- **(A) L'apertura nel pavimento (19).** Sul livello di partenza **non c'è
  alcun segno**: né il buco, né la trappola, né la botola. La caduta porta a
  un'isola su un'altra tavola e questa non dice che di lì si scende. Le scale
  hanno la loro nota `(id Llivello)`: serve la stessa cosa, e un simbolo per
  il buco.
- **(A) Dove porta un portale.** Il cerchio viola tratteggiato c'è, ma non
  dice **dove** si esce - le scale sì. Stessa nota, stesso posto.

### Random Architecture Table

- **(A/C) Diciannove risultati su venti sono solo testo, e per cinque il prop
  esiste già.** In `dungeongen/map/_props/` ci sono `Fountain`, `Column`
  (tonda o quadrata), `Altar`, `Dias`, `Coffin`, `Rock` (tre misure) e
  `Stairs` - e sappiamo appenderne uno a una cella, perché è quello che
  `_quieten_stair_alcoves` fa con la scala. Corrispondenze dirette:
  **fontana** (3) → `Fountain`, **pilastri lungo i lati** (7) → `Column`,
  **catacombe** (8) → `Coffin`, **plinto sacrificale** (10) → `Dias` o
  `Altar`, **statua** (1) → `Altar`/`Dias`, il meno esatto dei cinque.
  Attenzione: solo alcuni sono in `PropType`; `Fountain` e `Stairs` si
  costruiscono direttamente.
  Restano senza corrispondenza **1d4 pozze** (4), **corso d'acqua** (14),
  **botola con scala** (13), **serie di alcove** (2), **caverna naturale**
  (15) - lì o si disegna nell'overlay o si lascia al registro.
- **(C) Le macerie dei contenuti del passaggio** (70-80) avrebbero `Rock`, se
  si decide che vanno viste.
- **(A) Il "1d4 pozze" non tira nemmeno il d4**: la riga arriva letterale. Da
  sistemare comunque, disegno o no.

### Room Contents / Passage Contents

- **(A) "There's a secret door hidden in this room."** Il tiro dice che in
  quella stanza c'è una porta segreta e non produce niente: nessun nodo,
  nessun muro aperto, nessuna "S". O diventa una porta segreta vera (con un
  ramo dietro, come ora fanno quelle del passaggio) o va detto nella voce che
  è solo un aggancio narrativo. Esce dal 10-30% di sei righe diverse, quindi
  non è raro.
- **(C) Trappole nei corridoi.** 95-98 dei contenuti del passaggio tira
  quattro trappole vere, con DC e danni, e sulla mappa non c'è niente: le
  stanze hanno il pallino di gravità, i passaggi no.
- **(C) Il pallino di gravità è per stanza.** Un corridoio con un incontro
  Difficile e uno vuoto si disegnano uguali.

### Stairs Table

- **(C) Salita e discesa.** La nota dice il livello d'arrivo, quindi su/giù si
  deduce; i gradini sono orientati dalla direzione di salita. Non è mai stato
  verificato che un lettore lo colga - una freccia o un "▲/▼" nella nota
  sarebbe esplicito.

### Trap Table e Secret Door Table

- **(C) Nessuna trappola è mai disegnata**, da nessuna delle tre strade che le
  producono (contenuti del passaggio, porta trappolata, porta segreta
  trappolata 5-6). Solo registro.
- **(A) Il pericolo "a trap" del d6 dei pericoli non tira sulla Trap Table**,
  quindi resta senza DC e senza danno mentre le altre trappole li hanno.

### Dungeon Type Table

- **(C) Non influenza niente**, né il disegno né gli altri tiri: stesso seme,
  stesso dungeon, cambia solo la riga d'intestazione. Prima di dargli un
  effetto va deciso se la fonte lo prevede o se sarebbe una nostra invenzione.

### Starting Area Table

- **(C) I cinque risultati non si distinguono** sulla mappa: `open_entrance`
  diventa un d4 fra passaggio e stanza e resta solo la riga *"Open
  entrance."*. Il punto d'ingresso però è marcato, quindi manca la
  distinzione, non il segno.

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
