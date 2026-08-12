"""Render the 2D dungeon layout (see layout.py) as a hand-drawn SVG map.

Room/corridor/door/stairs geometry is computed in Python (deterministic,
from the same dice rolls as everything else). The actual line art is drawn
client-side by RoughJS (vendored in `vendor/rough.min.js`, MIT license) so
walls and corridors get a sketchy, hand-drawn quality instead of looking
like a technical CAD diagram. Every shape gets a numeric seed derived from
its node id, so the sketch is stable across reloads of the same page.
Room numbers, the room key, legend and tooltips stay as plain crisp SVG/
HTML text, since RoughJS only wobbles line art, not type.
"""

from __future__ import annotations

import html as _html
import json as _json
import re as _re
from pathlib import Path

from . import dungeongen_bridge as _bridge
from .layout import compute_layout

PX = 20  # pixels per grid unit (1 unit = 10 ft)
PAD = 1.0  # padding around the map, in grid units

_VENDOR_JS = (Path(__file__).parent / "vendor" / "rough.min.js").read_text(encoding="utf-8")

_CONTENT_HUE = {
    "boss": "rust",
    "deadly_encounter": "rust",
    "bbeg_remnants": "rust",
    "trapped_victim": "rust",
    "strong_npc": "plum",
    "hazard": "plum",
    "relic": "violet",
    "npc_investigating": "violet",
    "runes": "violet",
    "encounter": "teal",
    "dying_npc": "teal",
    "creatures_fighting": "teal",
}

_CONTENT_HUE_LABELS = [
    ("rust", "Pericolo grave / boss"),
    ("teal", "Incontro"),
    ("plum", "Rischio / trappola"),
    ("violet", "Indizio / enigma"),
    ("slate", "Vuota o poco rilevante"),
]

_SHAPE_NAMES = {
    "rect": "rettangolare", "square": "quadrata", "circle": "circolare",
    "triangle": "triangolare", "polygon": "poligonale", "trapezoid": "trapezoidale",
    "cave": "caverna",
}

_MAP_STYLE = """
<style>
  .dg-map-wrap { border: 1px solid var(--line); border-radius: 10px; background: var(--bg-panel); overflow: hidden; }
  .dg-map-radio { position: absolute; opacity: 0; pointer-events: none; }
  .dg-map-tabs { display: flex; flex-wrap: wrap; gap: .3rem; padding: .6rem .6rem 0; }
  .dg-map-tabs label {
    font-size: .78rem; font-weight: 600; padding: .3rem .7rem; border-radius: 6px 6px 0 0;
    background: var(--bg); color: var(--text-dim); cursor: pointer; border: 1px solid var(--line); border-bottom: none;
  }
  .dg-map-panels { position: relative; }
  .dg-map-panel { display: none; }
  .dg-map-scroll { padding: .5rem; overflow: auto; max-height: 70vh; }
  .dg-map-svg { display: block; }
  .dg-map-legend {
    display: flex; flex-wrap: wrap; gap: .5rem 1rem; padding: .6rem .9rem .8rem;
    font-size: .74rem; color: var(--text-dim); border-top: 1px solid var(--line);
  }
  .dg-map-legend .dg-swatch { display: inline-flex; align-items: center; gap: .35rem; }
  .dg-map-legend .dg-dot { width: .6rem; height: .6rem; border-radius: 2px; display: inline-block; }
  .dg-map-legend-title {
    flex: 0 0 100%; font-weight: 700; text-transform: uppercase; letter-spacing: .04em;
    font-size: .68rem; color: var(--text-dim); margin-top: .3rem;
  }
  .dg-map-legend-title:first-child { margin-top: 0; }
  .dg-map-legend svg { flex: none; overflow: visible; }

  .dg-map-key {
    border-top: 1px solid var(--line); padding: .7rem .9rem .9rem;
    display: grid; grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
    gap: .3rem .9rem; font-size: .78rem; color: var(--text);
  }
  .dg-map-key .dg-key-row { display: flex; gap: .5rem; align-items: baseline; }
  .dg-map-key .dg-key-num {
    flex: none; min-width: 1.6em; text-align: right; font-weight: 700;
    color: var(--brass); font-variant-numeric: tabular-nums;
  }

  .dg-map-grid-line { stroke: var(--line); stroke-width: 1; opacity: .3; }
  .dg-map-compass { font: 700 11px system-ui, sans-serif; fill: var(--text-dim); }
  .dg-map-compass-arrow { stroke: var(--text-dim); stroke-width: 1.5; }
  .dg-map-room-number {
    font: 700 12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    fill: var(--text); text-anchor: middle; dominant-baseline: central;
  }
  .dg-map-label {
    font: 600 10px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    fill: var(--text-dim);
    font-variant-numeric: tabular-nums;
  }
  .dg-map-entrance-label {
    font: 700 11px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    fill: var(--brass);
  }

  /* dungeongen-backed maps: fixed paper background regardless of page theme,
     so the overlay below also uses fixed (non-token) colors on purpose. */
  .dg-map-svg-dungeongen { background: #ffffff; border-radius: 6px; }
  .dg-map-hit { fill: #000; opacity: 0; cursor: help; pointer-events: all; }
  .dg-map-room-number-dg {
    font: 700 26px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    fill: #1a1a1a; text-anchor: middle; paint-order: stroke; stroke: #fff; stroke-width: 4px;
  }
  .dg-map-label-dg {
    font: 600 20px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    fill: #333; font-variant-numeric: tabular-nums;
  }
  .dg-map-entrance-label-dg {
    font: 700 20px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    fill: #a9701f; paint-order: stroke; stroke: #fff; stroke-width: 3px;
  }
</style>
"""

# Small, crisp (non-sketchy) icons for the legend - drawn plainly so they
# stay legible at 16px regardless of RoughJS's random wobble.
_LEGEND_ICONS = {
    "corridor": '<svg width="26" height="16" viewBox="0 0 26 16"><line x1="2" y1="8" x2="24" y2="8" stroke="var(--brass)" stroke-width="5" stroke-linecap="round" /></svg>',
    "door": (
        '<svg width="26" height="16" viewBox="0 0 26 16">'
        '<line x1="2" y1="8" x2="10" y2="8" stroke="var(--brass)" stroke-width="5" stroke-linecap="round" />'
        '<line x1="16" y1="8" x2="24" y2="8" stroke="var(--brass)" stroke-width="5" stroke-linecap="round" />'
        '<line x1="13" y1="3" x2="13" y2="13" stroke="var(--rust)" stroke-width="4" /></svg>'
    ),
    "stairs": '<svg width="16" height="16" viewBox="0 0 16 16"><polygon points="8,3 2,13 14,13" fill="var(--plum)" /></svg>',
    "portal": '<svg width="16" height="16" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6" fill="none" stroke="var(--violet)" stroke-width="2" stroke-dasharray="3 3" /></svg>',
    "cap": '<svg width="16" height="16" viewBox="0 0 16 16"><circle cx="8" cy="8" r="4" fill="var(--slate)" /></svg>',
    "entrance": '<svg width="16" height="16" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6" fill="var(--brass)" /></svg>',
}

# Renders every level's shapes with RoughJS, once per page (shared across all
# level tabs). Reads its input from the JSON blob in #dg-map-data.
_RENDER_SCRIPT_JS = """
(function () {
  function seedFor(id, salt) { return (((id * 2654435761) ^ salt) & 0x7fffffff) || 1; }
  function addTitle(node, text) {
    if (!text || !node) return;
    var t = document.createElementNS('http://www.w3.org/2000/svg', 'title');
    t.textContent = text;
    node.insertBefore(t, node.firstChild);
  }
  function renderLevel(rc, svg, data) {
    // Corridors and doors first, rooms on top with an opaque floor: a
    // corridor that happens to route close to an unrelated room must
    // disappear behind its wall, not read as cutting through it.
    data.corridors.forEach(function (c) {
      if (c.points.length < 2) return;
      var node = rc.linearPath(c.points, {
        stroke: 'var(--brass)', strokeWidth: 6, roughness: 1.7, bowing: 1.8, seed: seedFor(c.id, 3),
      });
      addTitle(node, c.title);
      svg.appendChild(node);
    });
    data.doors.forEach(function (d) {
      var stub1 = rc.line(d.x1, d.y1, d.gx1, d.gy1, { stroke: 'var(--brass)', strokeWidth: 6, roughness: 1.7, seed: seedFor(d.id, 4) });
      var stub2 = rc.line(d.gx2, d.gy2, d.x2, d.y2, { stroke: 'var(--brass)', strokeWidth: 6, roughness: 1.7, seed: seedFor(d.id, 5) });
      svg.appendChild(stub1); svg.appendChild(stub2);
    });
    data.rooms.forEach(function (r) {
      // --bg is meant for a room floor to stand out against the surrounding
      // --bg-panel, but the two are nearly identical in the dark palette -
      // a room reads as an unrendered void, just its outline and number
      // floating in empty space. --line sits a clear step lighter than
      // --bg-panel in *both* palettes, so it always reads as a floor.
      var floor = rc.rectangle(r.x, r.y, r.w, r.h, {
        fill: 'var(--line)', fillStyle: 'solid', stroke: 'none', roughness: 0,
      });
      floor.setAttribute('class', 'dg-map-room-floor');
      svg.appendChild(floor);
      var stripe = rc.rectangle(r.x, r.y, r.w, 6, {
        fill: 'var(--' + r.hue + ')', fillStyle: 'hachure', hachureGap: 3, fillWeight: 1.6,
        stroke: 'none', roughness: 1.4, seed: seedFor(r.id, 1),
      });
      svg.appendChild(stripe);
      var box = rc.rectangle(r.x, r.y, r.w, r.h, {
        fill: 'none', stroke: 'var(--text-dim)', strokeWidth: 2, roughness: 1.9, bowing: 1.2,
        seed: seedFor(r.id, 2),
      });
      addTitle(box, r.title);
      svg.appendChild(box);
      var text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', r.x + r.w / 2);
      text.setAttribute('y', r.y + r.h / 2);
      text.setAttribute('class', 'dg-map-room-number');
      text.textContent = r.id;
      svg.appendChild(text);
    });
    // The door bar itself is drawn last of the "structural" layer, on top
    // of the room floors, so it stays visible right at the threshold.
    data.doors.forEach(function (d) {
      var bar = rc.line(d.px1, d.py1, d.px2, d.py2, { stroke: 'var(--rust)', strokeWidth: 5, roughness: 2.1, seed: seedFor(d.id, 6) });
      addTitle(bar, d.title);
      svg.appendChild(bar);
    });
    data.stairs.forEach(function (s) {
      var tri = rc.polygon(s.points, { fill: 'var(--plum)', fillStyle: 'solid', stroke: 'var(--plum)', roughness: 1.7, seed: seedFor(s.id, 7) });
      addTitle(tri, s.title);
      svg.appendChild(tri);
      var text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', s.lx); text.setAttribute('y', s.ly);
      text.setAttribute('class', 'dg-map-label');
      text.textContent = 'L' + s.toLevel;
      svg.appendChild(text);
    });
    data.portals.forEach(function (p) {
      var c = rc.circle(p.x, p.y, 14, { stroke: 'var(--violet)', strokeWidth: 2, roughness: 2, fill: 'none', seed: seedFor(p.id, 8) });
      addTitle(c, 'Portale - prosegue altrove sulla mappa');
      c.setAttribute('stroke-dasharray', '3 3');
      svg.appendChild(c);
    });
    data.caps.forEach(function (cap) {
      var c = rc.circle(cap.x, cap.y, 8, { fill: 'var(--slate)', fillStyle: 'solid', stroke: 'none', roughness: 1.4, seed: seedFor(cap.id, 9) });
      addTitle(c, cap.kind === 'edge' ? 'Limite del dungeon' : 'Vicolo cieco');
      svg.appendChild(c);
      // <title> tooltips don't show on touch devices; label lets the id be matched to the log entry.
      var capLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      capLabel.setAttribute('x', cap.x + 11); capLabel.setAttribute('y', cap.y + 4);
      capLabel.setAttribute('class', 'dg-map-label');
      capLabel.textContent = '#' + cap.id;
      svg.appendChild(capLabel);
    });
    data.origins.forEach(function (o) {
      var oc = rc.circle(o.x, o.y, 12, {
        fill: o.isEntrance ? 'var(--brass)' : 'none', fillStyle: 'solid',
        stroke: 'var(--brass)', strokeWidth: 2, roughness: 1.5,
        seed: seedFor(o.seed, 10),
      });
      if (!o.isEntrance) oc.setAttribute('stroke-dasharray', '2 2');
      addTitle(oc, o.isEntrance ? 'Ingresso del dungeon' : 'Punto di arrivo su questa mappa');
      svg.appendChild(oc);
      // A hover-only <title> is invisible on touch devices, so the marker's
      // meaning also gets a permanent text label right next to it (same
      // treatment as the stairs' "L{level}" label below).
      var oLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      oLabel.setAttribute('x', o.x + 16); oLabel.setAttribute('y', o.y + 4);
      oLabel.setAttribute('class', 'dg-map-entrance-label');
      oLabel.textContent = o.isEntrance ? 'Ingresso' : 'Arrivo';
      svg.appendChild(oLabel);
    });
  }
  function boot() {
    var script = document.getElementById('dg-map-data');
    if (!script || !window.rough) return;
    var levels = JSON.parse(script.textContent);
    levels.forEach(function (data) {
      var svg = document.getElementById(data.svgId);
      if (!svg) return;
      var rc = window.rough.svg(svg);
      renderLevel(rc, svg, data);
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
"""


def _tab_id(level: int) -> str:
    return f"dg-map-lvl-{level}".replace("-", "n") if level < 0 else f"dg-map-lvl-{level}"


def _room_hue(room: dict) -> str:
    return _CONTENT_HUE.get(room.get("content_tag"), "slate")


def _room_summary(lines: list[str], limit: int = 130) -> str:
    # lines[0] is the shape roll, lines[1] is the exits count, lines[2] is
    # just the "[Room Contents d100=NN]" header - the actual description
    # starts at lines[3].
    body = " ".join(line for line in lines[3:] if line).strip()
    if not body:
        body = "Stanza vuota."
    if len(body) > limit:
        body = body[: limit - 1].rstrip() + "…"
    return body


def _full_text(lines: list[str]) -> str:
    return "\n".join(lines) if lines else ""


# ---------------------------------------------------------------------------
# dungeongen backend: photoreal-ish room/corridor/door art (see
# dungeongen_bridge.py) with our own interactive overlay on top. Its paper is
# always light, so the overlay uses fixed hex colors (matching this file's
# light theme values) instead of the --token custom properties, which would
# turn invisible-on-white in dark mode.
# ---------------------------------------------------------------------------

_DG_FIXED_HUES = {
    "rust": "#a44f24", "teal": "#2f6b73", "plum": "#6b4fa0",
    "violet": "#5a55a8", "slate": "#6b7280", "moss": "#3f7a4a",
}
_DG_INK = "#1a1a1a"
_DG_BRASS = "#a9701f"

_SVG_OUTER_RE = _re.compile(r"<svg\b[^>]*>", _re.IGNORECASE)
_ID_ATTR_RE = _re.compile(r'\bid="([^"]+)"')
_ID_REF_RE = _re.compile(r"url\(#([^)\"]+)\)")


def _strip_svg_wrapper(svg_text: str) -> str:
    """Return just the inner content of an <svg>...</svg> document."""
    match = _SVG_OUTER_RE.search(svg_text)
    start = match.end() if match else 0
    end = svg_text.rfind("</svg>")
    return svg_text[start:end] if end != -1 else svg_text[start:]


def _namespace_svg_ids(svg_inner: str, suffix: str) -> str:
    """dungeongen reuses short clip-path ids (e.g. "cl_10") across renders -
    when more than one lands on the same page those ids collide and a later
    clip-path silently wins over an earlier one. Suffix them uniquely."""
    svg_inner = _ID_ATTR_RE.sub(lambda m: f'id="{m.group(1)}{suffix}"', svg_inner)
    svg_inner = _ID_REF_RE.sub(lambda m: f"url(#{m.group(1)}{suffix})", svg_inner)
    return svg_inner


def _dungeongen_overlay_for_island(island: dict, offset_x: float, offset_y: float, scale: float) -> str:
    """Interactive layer dungeongen has no concept of: room tooltips/numbers
    (its own numbering is disabled so ours - matching the room key - is the
    only one), a content-severity dot per room, and stairs/portals/dead-ends."""
    parts = []

    def px(x: float, y: float) -> tuple[float, float]:
        return offset_x + x * scale, offset_y + y * scale

    for room in island["rooms"]:
        cxs = [c[0] for c in room["corners"]]
        cys = [c[1] for c in room["corners"]]
        rx, ry = px(min(cxs), min(cys))
        rx2, ry2 = px(max(cxs), max(cys))
        shape_name = _SHAPE_NAMES.get(room["shape"], room["shape"])
        title = _html.escape(f"Stanza {shape_name} #{room['id']}\n{_full_text(room['lines'])}")
        cx_ = (rx + rx2) / 2
        hue = _DG_FIXED_HUES.get(_room_hue(room))
        parts.append(
            f'<rect x="{rx}" y="{ry}" width="{rx2 - rx}" height="{ry2 - ry}" '
            f'class="dg-map-hit"><title>{title}</title></rect>'
            f'<text x="{cx_}" y="{ry + 32}" class="dg-map-room-number-dg">{room["id"]}</text>'
        )
        if hue:
            parts.append(f'<circle cx="{rx + 16}" cy="{ry + 16}" r="9" fill="{hue}" stroke="#fff" stroke-width="2" />')

    for stair in island["stairs"]:
        sx, sy = px(stair["x"], stair["y"])
        up = stair["delta"] < 0
        pts = (f"{sx},{sy - 16} {sx - 13},{sy + 12} {sx + 13},{sy + 12}" if up
               else f"{sx},{sy + 16} {sx - 13},{sy - 12} {sx + 13},{sy - 12}")
        title = _html.escape(_full_text(stair["lines"]))
        parts.append(
            f'<polygon points="{pts}" fill="{_DG_FIXED_HUES["plum"]}" stroke="#fff" stroke-width="2">'
            f"<title>{title}</title></polygon>"
            f'<text x="{sx + 19}" y="{sy + 6}" class="dg-map-label-dg">L{stair.get("to_level")}</text>'
        )

    for portal in island["portals"]:
        px_, py_ = px(portal["x"], portal["y"])
        parts.append(
            f'<circle cx="{px_}" cy="{py_}" r="16" fill="none" stroke="{_DG_FIXED_HUES["violet"]}" '
            f'stroke-width="3" stroke-dasharray="6 6"><title>Portale - prosegue altrove sulla mappa</title></circle>'
        )

    # dungeongen only knows about rooms/passages (translated from our own
    # room-to-room links) - it has no idea a dead-end/edge stub even exists,
    # so unlike the RoughJS renderer (which draws every island["corridors"]
    # entry generically) this overlay has to draw the little stub line
    # itself, or a branch off a T-junction/four-way intersection would show
    # only a cap dot floating with nothing connecting it to the corridor.
    for corridor in island["corridors"]:
        if not (isinstance(corridor["id"], str) and corridor["id"].startswith("cap")):
            continue
        (sx, sy), (ex, ey) = corridor["points"][0], corridor["points"][-1]
        sx_, sy_ = px(sx, sy)
        ex_, ey_ = px(ex, ey)
        parts.append(f'<line x1="{sx_}" y1="{sy_}" x2="{ex_}" y2="{ey_}" stroke="{_DG_INK}" stroke-width="3" />')

    for cap in island["caps"]:
        cx_, cy_ = px(cap["x"], cap["y"])
        label = "Limite del dungeon" if cap["kind"] == "edge" else "Vicolo cieco"
        parts.append(f'<circle cx="{cx_}" cy="{cy_}" r="8" fill="{_DG_FIXED_HUES["slate"]}"><title>{label}</title></circle>')
        # <title> tooltips don't show on touch devices; label lets the id be matched to the log entry.
        parts.append(f'<text x="{cx_ + 11}" y="{cy_ + 7}" class="dg-map-label-dg">#{cap["id"]}</text>')

    ox, oy = island["origin"]
    ox_, oy_ = px(ox, oy)
    label = "Ingresso del dungeon" if island.get("is_entrance") else "Punto di arrivo su questa mappa"
    if island.get("is_entrance"):
        parts.append(f'<circle cx="{ox_}" cy="{oy_}" r="13" fill="{_DG_BRASS}" stroke="#fff" stroke-width="3"><title>{label}</title></circle>')
    else:
        parts.append(
            f'<circle cx="{ox_}" cy="{oy_}" r="13" fill="none" stroke="{_DG_BRASS}" stroke-width="3" '
            f'stroke-dasharray="4 4"><title>{label}</title></circle>'
        )
    # A hover-only <title> never shows on touch devices, so the marker also
    # gets a permanent text label (same treatment as the stairs' "L{level}").
    entrance_text = "Ingresso" if island.get("is_entrance") else "Arrivo"
    parts.append(f'<text x="{ox_ + 19}" y="{oy_ + 7}" class="dg-map-entrance-label-dg">{entrance_text}</text>')
    return "".join(parts)


def _dungeongen_level_svg(islands: list[dict]) -> dict | None:
    """Try to render an entire level's islands via dungeongen, composed side
    by side at dungeongen's own native scale, with our overlay (tooltips,
    room numbers, stairs/portals/dead-ends dungeongen has no concept of) on
    top. Returns None if dungeongen is unavailable, any island is too big
    for it, or anything about the render fails - the caller falls back to
    the RoughJS renderer in that case."""
    if not _bridge.available() or not islands:
        return None
    if any(not island["rooms"] for island in islands):
        # An island with no rooms at all (just a dead end, or a stub reached
        # via a stairs/portal jump that went nowhere) has nothing for
        # dungeongen to draw - its Dungeon.bounds falls back to a meaningless
        # placeholder box, unrelated to where our own overlay markers really
        # are. Simpler and safer to render the whole level with RoughJS.
        return None
    if not all(_bridge.fits_size_limit(island) for island in islands):
        return None

    placed = []
    try:
        for idx, island in enumerate(islands):
            svg, off_x, off_y, scale, width, height = _bridge.render_island_svg(island)
            inner = _namespace_svg_ids(_strip_svg_wrapper(svg), f"__i{idx}")
            placed.append((inner, -off_x, -off_y, width, height, off_x, off_y, scale))
    except Exception:
        return None

    min_x = min(p[1] for p in placed)
    min_y = min(p[2] for p in placed)
    max_x = max(p[1] + p[3] for p in placed)
    max_y = max(p[2] + p[4] for p in placed)
    shift_x, shift_y = -min_x, -min_y
    canvas_w, canvas_h = max_x - min_x, max_y - min_y

    backgrounds, overlays = [], []
    for (inner, place_x, place_y, _w, _h, off_x, off_y, scale), island in zip(placed, islands):
        gx, gy = place_x + shift_x, place_y + shift_y
        backgrounds.append(f'<g transform="translate({gx},{gy})">{inner}</g>')
        # The background for this island sits at (gx, gy) and its own content
        # at local coordinate (off_x + our_x*scale) - composing those two
        # gives shared_px = gx + off_x + our_x*scale = shift_x + our_x*scale
        # (place_x is -off_x by construction), so the overlay - which wants
        # shared_px directly - only ever needs the shared shift, not off_x.
        overlays.append(_dungeongen_overlay_for_island(island, shift_x, shift_y, scale))

    body = "".join(backgrounds) + "".join(overlays)
    svg = (
        f'<svg class="dg-map-svg dg-map-svg-dungeongen" width="{canvas_w}" height="{canvas_h}" '
        f'viewBox="0 0 {canvas_w} {canvas_h}" xmlns="http://www.w3.org/2000/svg">{body}</svg>'
    )
    return {"svg": svg}


def _bbox_of_islands(islands: list[dict]):
    xs, ys = [], []
    for island in islands:
        for room in island["rooms"]:
            for cx, cy in room["corners"]:
                xs.append(cx); ys.append(cy)
        for corridor in island["corridors"]:
            for cx, cy in corridor["points"]:
                xs.append(cx); ys.append(cy)
        for door in island["doors"]:
            xs += [door["x1"], door["x2"]]
            ys += [door["y1"], door["y2"]]
        for group in ("stairs", "portals", "caps"):
            for item in island[group]:
                xs.append(item["x"]); ys.append(item["y"])
        ox, oy = island["origin"]
        xs.append(ox); ys.append(oy)
    if not xs:
        return (0.0, 0.0, 1.0, 1.0)
    return min(xs) - PAD, min(ys) - PAD, max(xs) + PAD, max(ys) + PAD


def _level_payload(level: int, islands: list[dict]) -> dict:
    """Build the JSON-serializable shape data (in pixel space) for one level."""
    minx, miny, maxx, maxy = _bbox_of_islands(islands)

    def px(v: float) -> float:
        return round(v * PX, 1)

    rooms, corridors, doors, stairs, portals, caps, origins = [], [], [], [], [], [], []

    for island_index, island in enumerate(islands):
        for room in island["rooms"]:
            cxs = [c[0] for c in room["corners"]]
            cys = [c[1] for c in room["corners"]]
            rx, ry = px(min(cxs) - minx), px(min(cys) - miny)
            rw, rh = px(max(cxs) - min(cxs)), px(max(cys) - min(cys))
            shape_name = _SHAPE_NAMES.get(room["shape"], room["shape"])
            rooms.append({
                "id": room["id"], "x": rx, "y": ry, "w": rw, "h": rh,
                "hue": _room_hue(room),
                "title": f"Stanza {shape_name} #{room['id']}\n{_full_text(room['lines'])}",
            })

        for corridor in island["corridors"]:
            points = [[px(cx - minx), px(cy - miny)] for cx, cy in corridor["points"]]
            corridors.append({"id": corridor["id"], "points": points, "title": _full_text(corridor["lines"])})

        for door in island["doors"]:
            x1, y1 = px(door["x1"] - minx), px(door["y1"] - miny)
            x2, y2 = px(door["x2"] - minx), px(door["y2"] - miny)
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            ddx, ddy = x2 - x1, y2 - y1
            length = (ddx ** 2 + ddy ** 2) ** 0.5 or 1.0
            ux, uy = ddx / length, ddy / length
            perp_x, perp_y = -uy, ux
            gap_half = min(length * 0.35, 6.0)
            gap_x, gap_y = ux * gap_half, uy * gap_half
            doors.append({
                "id": door["id"], "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "gx1": mx - gap_x, "gy1": my - gap_y, "gx2": mx + gap_x, "gy2": my + gap_y,
                "px1": mx - perp_x * 9, "py1": my - perp_y * 9,
                "px2": mx + perp_x * 9, "py2": my + perp_y * 9,
                "title": _full_text(door["lines"]),
            })

        for stair in island["stairs"]:
            sx, sy = px(stair["x"] - minx), px(stair["y"] - miny)
            up = stair["delta"] < 0
            points = [[sx, sy - 7], [sx - 6, sy + 5], [sx + 6, sy + 5]] if up else \
                     [[sx, sy + 7], [sx - 6, sy - 5], [sx + 6, sy - 5]]
            stairs.append({
                "id": stair["id"], "points": points, "lx": sx + 9, "ly": sy + 4,
                "toLevel": stair.get("to_level"), "title": _full_text(stair["lines"]),
            })

        for portal in island["portals"]:
            portals.append({"id": portal["id"], "x": px(portal["x"] - minx), "y": px(portal["y"] - miny)})

        for cap in island["caps"]:
            caps.append({"id": cap["id"], "x": px(cap["x"] - minx), "y": px(cap["y"] - miny), "kind": cap["kind"]})

        ox, oy = island["origin"]
        origins.append({
            "id": f"origin-{island_index}",
            "seed": (island["rooms"][0]["id"] if island["rooms"]
                     else island["corridors"][0]["id"] if island["corridors"]
                     else island_index + 1),
            "x": px(ox - minx), "y": px(oy - miny),
            "isEntrance": bool(island.get("is_entrance")),
        })

    width, height = px(maxx - minx), px(maxy - miny)
    svg_id = f"{_tab_id(level)}-canvas"
    return {
        "svgId": svg_id, "width": width, "height": height,
        "rooms": rooms, "corridors": corridors, "doors": doors, "stairs": stairs,
        "portals": portals, "caps": caps, "origins": origins,
    }


def _svg_shell(payload: dict) -> str:
    w, h = payload["width"], payload["height"]
    grid = []
    x = 0.0
    while x <= w + 0.01:
        grid.append(f'<line x1="{x}" y1="0" x2="{x}" y2="{h}" class="dg-map-grid-line" />')
        x += PX
    y = 0.0
    while y <= h + 0.01:
        grid.append(f'<line x1="0" y1="{y}" x2="{w}" y2="{y}" class="dg-map-grid-line" />')
        y += PX
    cx, cy = w - 22, 26
    compass = (
        f'<g class="dg-map-compass">'
        f'<line x1="{cx}" y1="{cy + 12}" x2="{cx}" y2="{cy - 6}" class="dg-map-compass-arrow" />'
        f'<line x1="{cx}" y1="{cy - 6}" x2="{cx - 4}" y2="{cy + 1}" class="dg-map-compass-arrow" />'
        f'<line x1="{cx}" y1="{cy - 6}" x2="{cx + 4}" y2="{cy + 1}" class="dg-map-compass-arrow" />'
        f'<text x="{cx}" y="{cy + 24}" text-anchor="middle">N</text>'
        f"</g>"
    )
    return (
        f'<svg id="{payload["svgId"]}" class="dg-map-svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">'
        f'<g>{"".join(grid)}</g>{compass}</svg>'
    )


def _room_key_html(islands: list[dict]) -> str:
    rooms = sorted((room for island in islands for room in island["rooms"]), key=lambda r: r["id"])
    if not rooms:
        return ""
    rows = "".join(
        f'<div class="dg-key-row"><span class="dg-key-num">{room["id"]}</span>'
        f"<span>{_html.escape(_room_summary(room['lines']))}</span></div>"
        for room in rooms
    )
    return f'<div class="dg-map-key">{rows}</div>'


def _safe_json(data) -> str:
    return _json.dumps(data).replace("</", "<\\/")


def render_map_section(dungeon) -> str:
    """A self-contained map section: level tabs (if needed), one map + numbered
    key per level, and a legend. Each level tries the dungeongen backend first
    (proper wall/door art - see dungeongen_bridge.py) and falls back to the
    hand-drawn RoughJS renderer (client-side, against a JSON payload) when
    dungeongen is unavailable, the level is too large for it, or its render
    fails for any reason."""
    layout = compute_layout(dungeon)
    levels = sorted(layout.keys())
    if not levels:
        return ""

    svg_by_level: dict[int, str] = {}
    fallback_payloads = []
    for level in levels:
        islands = layout[level]
        dg_result = _dungeongen_level_svg(islands)
        if dg_result is not None:
            svg_by_level[level] = dg_result["svg"]
        else:
            payload = _level_payload(level, islands)
            svg_by_level[level] = _svg_shell(payload)
            fallback_payloads.append(payload)

    radios_html = ""
    labels_html = ""
    panels_html = ""
    if len(levels) > 1:
        for i, level in enumerate(levels):
            tab_id = _tab_id(level)
            checked = " checked" if i == 0 else ""
            radios_html += f'<input type="radio" name="dg-map-level" id="{tab_id}" class="dg-map-radio"{checked}>'
            labels_html += f'<label for="{tab_id}">Livello {level}</label>'
        for level in levels:
            panels_html += (
                f'<div class="dg-map-panel" data-for="{_tab_id(level)}">'
                f'<div class="dg-map-scroll">{svg_by_level[level]}</div>'
                f"{_room_key_html(layout[level])}</div>"
            )
        panel_css = "".join(
            f'#{_tab_id(level)}:checked ~ .dg-map-panels [data-for="{_tab_id(level)}"] {{ display: block; }}\n'
            f'#{_tab_id(level)}:checked ~ .dg-map-tabs label[for="{_tab_id(level)}"] '
            f"{{ background: var(--brass); color: var(--brass-ink); border-color: var(--brass); }}\n"
            for level in levels
        )
        # No extra "show the first panel" rule needed: the first radio already
        # carries the `checked` attribute, so its :checked rule above covers it.
        show_first = ""
    else:
        panels_html = (
            f'<div class="dg-map-panel" data-for="only">'
            f'<div class="dg-map-scroll">{svg_by_level[levels[0]]}</div>'
            f"{_room_key_html(layout[levels[0]])}</div>"
        )
        panel_css = ""
        show_first = '.dg-map-panel[data-for="only"] { display: block; }\n'

    legend = (
        '<div class="dg-map-legend">'
        '<span class="dg-map-legend-title">Simboli</span>'
        f'<span class="dg-swatch">{_LEGEND_ICONS["corridor"]}Corridoio</span>'
        f'<span class="dg-swatch">{_LEGEND_ICONS["door"]}Porta</span>'
        f'<span class="dg-swatch">{_LEGEND_ICONS["stairs"]}Scale (▲ su / ▼ giù, con livello di arrivo)</span>'
        f'<span class="dg-swatch">{_LEGEND_ICONS["portal"]}Portale magico</span>'
        f'<span class="dg-swatch">{_LEGEND_ICONS["cap"]}Vicolo cieco / limite mappa (il numero è l\'id nel registro, per capire perché)</span>'
        f'<span class="dg-swatch">{_LEGEND_ICONS["entrance"]}Ingresso del dungeon</span>'
        '<span class="dg-map-legend-title">Colore stanza = contenuto</span>'
        + "".join(
            f'<span class="dg-swatch"><span class="dg-dot" style="background:var(--{hue})"></span>{label}</span>'
            for hue, label in _CONTENT_HUE_LABELS
        )
        + "</div>"
    )

    tabs_wrap = f'<div class="dg-map-tabs">{labels_html}</div>' if labels_html else ""
    # RoughJS only ships when at least one level actually needs the fallback
    # renderer - a dungeongen-only page has no use for it.
    scripts = ""
    if fallback_payloads:
        data_script = f'<script id="dg-map-data" type="application/json">{_safe_json(fallback_payloads)}</script>'
        scripts = f"{data_script}<script>{_VENDOR_JS}</script><script>{_RENDER_SCRIPT_JS}</script>"
    return (
        f"{_MAP_STYLE}<style>{panel_css}{show_first}</style>\n"
        f'<div class="dg-map-wrap">{radios_html}{tabs_wrap}'
        f'<div class="dg-map-panels">{panels_html}</div>'
        f"{legend}</div>"
        f"{scripts}"
    )
