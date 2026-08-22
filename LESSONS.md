# What we know about the machinery

**Keep this file up to date whenever something new is understood about how any
of this works.** It is not a changelog and not a task list - `TODO.md` holds
open items. This holds the things that were *surprising*: the traps, the
non-obvious contracts, and the measurements that turned out to mean something
other than what they looked like. Anything here was learned the hard way,
usually after getting it wrong once or twice first.

Short entries. Where the detail matters, name the function rather than
explaining it.

---

## Measuring and verifying

This section first, because most wrong conclusions in this project came from a
measurement that was quietly answering a different question.

### Do

- **Prove a regression test fails without the fix.** Every time. Several tests
  here passed on the broken code and were only caught by trying.
- **Compare like with like.** Two walls of the *same* room is still not enough
  if one side has a corridor and the other has rock - the scan picks up the
  neighbour.
- **Clear `__pycache__` before measuring** (`find . -name __pycache__ -type d
  -exec rm -rf {} +`). Stale bytecode has served a constant that had just been
  changed, with the same file size and mtime to the second.
- **Say what a number counts.** "15% open" and "0.14 cells of ink past the
  corner" are different measurements of the same edge and disagree happily.
- **Ask the pixels what is drawn.** Region geometry cannot see paint: the
  alcove doorway is filled over the wall at `Layers.OVERLAY`, so every shape
  in the map still says that side is walled. `_alcove_edge_ink` renders and
  scans the four cell edges instead.

### Don't

- **Don't pixel-scan a cell edge for "is there a wall".** `StairsProp` draws
  its widest tread *on* the cell boundary, so a scan counts the staircase as
  wall. Strip the props first - and note `_quieten_stair_alcoves` puts a
  missing staircase back, so strip *after* it runs, not before.
- **Don't draw debug marks on the thing being measured.** A dashed rectangle
  outlining a cell lands exactly on that cell's edges; the scan then measures
  the overlay. Render twice - once clean to measure, once marked to look at.
- **Don't diff two renders to isolate one element** - and don't diff two
  renders at all. The same island rendered twice by the same code, in two
  processes, comes out different: props change shape, decoration moves. Only
  the geometry - walls, regions, chips, the rectangles a glyph draws - is
  reproducible. Measure that, or scan a wall line, never the ornament.
- **Don't probe a region's shape to ask "is this side open".** See
  `REGION_INFLATE` below - it used to answer yes on all four sides of
  everything. That probe is trustworthy now, but only because the inflation is
  off.
- **Don't patch a library constant around the conversion only.**
  `Map._make_regions` runs inside `Map.render`, so a patch that is restored
  after `convert_dungeon` changes nothing at all and reads as "the setting has
  no effect". See `_region_inflation`.

---

## Coordinates: lattice points vs cells

The single most productive source of off-by-one bugs in this codebase.

### Do

- **Keep the two straight.** A room `(x, y, w, h)` spans `[x, x+w]` in *lattice
  points*; a cell `(gx, gy)` is the square `[gx, gx+1] x [gy, gy+1]`.
- **Remember the convention** stated in `_segment_cells`: the cell is the
  square *after* the line. Travelling forwards, the last cell of a run to `b`
  is `b - 1`; travelling backwards it is `b`.
- **Expand runs before asking what occupies a cell.** `_grid_cell_path`
  returns **waypoints** - the corners - not every cell. A corridor from
  (20,14) to (23,14) comes back as `[(20,14), (22,14)]` and (21,14) is
  implied. Reading that list as "cells covered" reported the cell above seed
  72's stairs #23 as bare rock, twice, when two routes run through it.
- **Round half up** (`_grid`), never `round()`. Banker's rounding sends the
  two ends of a room in opposite directions and it comes out a cell too wide.

### Don't

- **Don't take a walk's end *point* as its last cell.** They differ by one
  whenever the walk ran in the positive direction. This left a third of the
  stairs pointing at the empty square past the end of their own corridor.

---

## Regions, walls and shading

### Do

- **Think of a wall as the outline of a region's combined shape**, not as an
  object. There is no `Wall` class. `Map._make_regions` traces connected
  elements, unions their shapes, and the outline of that union is what gets
  drawn.
- **Accept the corollary**: two contiguous floor cells inside one region have
  no boundary between them, so nothing is drawn there. For a wall to exist
  between two dug cells, they must be in different regions - or one of them
  must not be floor.

### Don't

- **Don't expect a one-cell room to look like a small version of a big one.**
  `Room.draw` brackets its corners (`CORNER_SIZE` 0.35 of a cell,
  `CORNER_INSET` 0.12): decoration at four cells across, a second stroke
  merging with the wall at one. Alcoves have `draw_corners` silenced.
- **Don't blame the drop shadow for heavy walls.** Zeroing
  `room_shadow_offset` moves the measurement not at all. It was the region
  inflation.

- **Don't expect two regions that touch to share one outline.** `Map.render`
  collects every region's path into one `unified_border` and strokes it, with
  no union: two outlines running along the same grid line are stroked twice,
  and anything one region owns past the line is stroked over the other's
  floor. That is where the box beside the stairs alcove came from.

### Worth knowing

Drawing order in `Map.render`, which is what makes a painted opening possible:
crosshatch, then per-region fills, shadows, grid and props (each clipped to
its region), then the unified border stroke, and only then `Layers.OVERLAY`
and `Layers.TEXT` over every element. Anything filled at OVERLAY covers the
wall.

`REGION_INFLATE` (dungeongen's `CELL_SIZE * 0.025` = 1.6px) inflates *every*
region before drawing. Two regions side by side are each inflated towards the
other, so their outlines land 3.2px apart and two 6px strokes merge into 9.2px
- which is why adjacent rooms shared a visibly fatter wall. It is overridden to
0 in `_REGION_INFLATE_OVERRIDE`; at 0 a shared wall and a free-standing one are
both 6.0px, both centred exactly on the grid line.

### To investigate

- What the inflation was *for*. Most likely welding a room to its corridor
  inside one region so no hairline shows. No seam has appeared without it over
  the sweep, but that is an absence of evidence. If seams ever show along a
  room-to-corridor join, put it back first.

---

## Doors, exits and openings

### Do

- **Remember there are exactly two chip providers**: `Door.get_side_shape` and
  `Exit.get_side_shape`. Nothing else opens a wall.
- **Draw a secret door as nothing at all.** Closed keeps its wall, which is
  the point - but closed also means dungeongen draws a leaf on that wall, so a
  secret door was rendering with a door plainly drawn in it. Its `draw` is
  silenced and the overlay's "S" is the only mark.
- **Hand a secret door over as `CLOSED`.** The webview adapter folds
  `DoorType.SECRET` into `OPEN`, and an open door is not a glyph, it is a hole
  - it merges the regions and erases the wall the secret is hidden in. The
  overlay draws the "S" itself.
- **Use all three pieces together** for a room off a corridor: the room, a
  `Passage` that *ends* in it, and a **closed** `Door` between them carrying
  that passage's id. Any one alone does nothing.
- **Point the door into the room.** Facing the other way measures sealed on
  all four sides, exactly like no door.

### Don't

- **Don't expect a chip alone to open anything.** It is made to sit in a wall
  that two floors already reach. An `Exit`, or a door with no passage
  terminating at it, leaves the room sealed on all four sides.
- **Don't hide a glyph and expect the opening to survive** *unless* the
  arrangement above is in place. With it, silencing the glyph is free (the
  region paints the chip). Without it, the glyph was the only thing that read
  as an opening.
- **Don't use `Exit` for anything that is not a way out of the dungeon.** Its
  own docstring: "a skewed inverted U archway extending away from the
  dungeon", and it draws exactly that, in perspective, sticking out of the
  wall. It was announcing the way out on top of secret entrances.
- **Don't put a door or exit on a cell you need as corridor floor.** Passages
  exclude cells occupied by doors or exits - the corridor there disappears.
- **Don't return a whole chip from `get_side_shape`** *on a wall*. dungeongen
  returns only the half on the connected element's side, which is how two
  regions meet exactly on the line with neither protruding. The exception is a
  door with a cell of its own: there the doorway *is* the cell, and handing
  both sides the same rectangle makes their outlines coincide instead of
  leaving a seam down the middle of it (`_square_off_doors`).
- **Don't assume a door's chip is where the door is.** dungeongen builds both
  halves inside the door's *own cell*, reaching from its middle out to each of
  its two walls, and draws the leaf in the middle of that cell. Right when a
  door has a cell to itself; ours sit on the wall and take none, so the half
  handed across reached half a cell into the wrong region and was outlined
  there - a rounded box on the wall with the leaf floating in it, 0.50 of a
  cell off. 117 of 117 wall-doors over 12 seeds.
- **Don't work out which wall a door is in from the door.** `direction` comes
  from `_door_direction`, which measures from one room's centre and does not
  survive a link whose two ends belong to different rooms; `orientation` is
  reliable but gives only the axis. And `shape.contains` is not enough to ask
  who owns the cell: dungeongen's passages *exclude* the cells their doors sit
  on, so a third of them are covered by neither neighbour. `_door_sides` reads
  the two neighbours' boxes on the orientation's axis instead.

### Worth knowing

- **There is no such thing as a gap between two regions.** Whatever either one
  owns past the shared line is outlined too, so a chip cannot cut a hole - it
  can only add a bump. Measured over 30 seeds: all 138 stairs alcoves were
  walled on all four sides, doorway included. An opening therefore comes from
  one of exactly two things: the two floors being in the *same* region, or
  paint laid over the wall afterwards.
- **A closed door's own glyph is paint of the second kind.** `Door.draw` fills
  its leaf in `room_color` at `Layers.OVERLAY`, after the border is stroked,
  and then strokes the leaf. Fill without that stroke and the result is a
  clean hole in the wall - which is how the alcove doorway is drawn.
- An **open** door is traversed by `Map._trace_connected_region`, so the two
  rooms become one region and the wall between them is erased. A **closed**
  door and an **`Exit`** are terminal: they contribute their chip and stop.
- **An open door draws nothing, and must not be made to.** It is a hole, not a
  glyph: there is no wall on that join to put a door in. `Door.draw` opens
  with `if not self._open`, and a replacement `draw` that drops that guard
  puts a door across every open join - which is what put one between seed
  72's passages 3 and 8, where the map had never drawn anything. Over 12 seeds
  42 of 145 doors are open.
- dungeongen's own generator only places a door with probability
  `DOOR_CHANCE`. Most of its room-corridor joins have no door at all - the
  opening is simply the two floors overlapping.

---

## Passages

### Do

- **Claim the takeoff cell** so a branch shares a cell with its trunk
  (`_claim_takeoff_cell`). The adapter only treats a cell as a crossing when
  two passages occupy the same one; a branch that merely touches another
  corridor's flank is a separate region with a wall between.
- **Let the layout record the takeoff.** Deriving it in the bridge was wrong
  in both directions - behind the branch joins the opposite arm, perpendicular
  joins whatever runs alongside. And translate it with the island.

### Don't

- **Don't decide "already drawn" by comparing a first point to a link's
  points.** Compare *cells*. Comparing points threw away exactly the arms a
  crossing is made of.

### To investigate

- Walking *between* two arms through a junction is still not guaranteed, even
  though each arm reaches it. Inside the adapter's own `_convert_passage`
  splitting.

---

## Stairs and their alcove

### Do

- **Give the steps a floor.** A stairs node emits a corridor for the length it
  walks; without it 84% of staircases stood on nothing.
- **Draw the alcove staircase smaller** (`_ALCOVE_STAIR_SCALE`). dungeongen's
  own runs the full width with the widest tread *on* the boundary plus an
  overhang - right in a passage, but in the alcove that boundary is the
  doorway, and the tread closed it.
- **Paint the doorway, don't build it.** A rectangle in `room_color` across
  the wall at `Layers.OVERLAY`, one `border_width` deep either side of the
  line and stopping one short of each corner (the border's round join reaches
  a half-thickness along the neighbouring wall, and painting over that eats
  the corner). 112 of 112 alcoves over 20 seeds then render as a square with
  one clear side, and it is the side the door faces.

### Don't

- **Don't trust `_convert_stair` to place the prop.** It looks for a passage,
  then a room, then falls back to `passages[0]` - silently putting the
  staircase on an unrelated corridor, or dropping it where an island has no
  passages left. `_quieten_stair_alcoves` takes it back and rebuilds it.
- **Don't identify an alcove by size.** Ordinary rooms come out 1x1 too, and
  they were having their decoration stripped. By position, against the stair
  cells the dungeon was built from (`_alcove_cell_of`).
- **Don't hand the alcove door a chip.** dungeongen's own goes in as two
  halves, one per region, and both sit inside the alcove cell because the door
  is on the cell rather than on one of its own - so the corridor's outline
  pokes into the alcove. Ours went in whole to *both* sides, and each region
  outlined all of it: that small box sticking into the corridor, which read as
  a closed door for weeks. `get_side_shape` now returns an empty group.
- **Don't open the door to get rid of the walls.** It works, and it takes too
  many: 77 of 138 alcoves kept their three walls, 21 kept four, 29 dropped to
  two, and one lost all of them - the alcove merges with everything its
  approach passage touches.

---

## Generation and layout

### Do

- **Write every roll into the log**, including the ones that produce nothing
  on the map: a room that fits nowhere says so in its own entry, a passage
  with no length of its own says it still takes the minimum 10ft.
- **Give every choice on the map two nodes in the log** - four-way, T
  junction, side passage, and a wall feature the passage carries on past.
- **Cut branches the map cannot reach** before spending rolls on them
  (`_cut_branches_the_map_will_not_reach`, run after each breadth-first wave).
  A cut room goes back on the room budget.

### Don't

- **Don't move anything to make it fit.** Draw the room, then the passage,
  then the next room at its rolled size. A room that does not fit is not
  placed.

---

## Environment

- **dungeongen and skia are only in `.venv`**; **playwright is only in the
  system `python`**. Tests run under `.venv`, so a test cannot render through
  a browser.
- **dungeongen's ±3200 map-unit limit is a native segfault**, not an
  exception. `island_extent_map_units` guards it, and must measure everything
  handed over - a room-less island is all corridors and used to report an
  extent of zero.
- **Run the hang sweep with empty islands included.** It used to skip them,
  which is exactly where the segfault was hiding.
