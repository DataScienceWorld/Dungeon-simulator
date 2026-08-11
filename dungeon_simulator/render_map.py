"""Render the 2D dungeon layout (see layout.py) as an SVG map."""

from __future__ import annotations

import html as _html

from .layout import compute_layout

PX = 20  # pixels per grid unit (1 unit = 10 ft)
PAD = 1.0  # padding around the map, in grid units

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

_SHAPE_NAMES = {
    "rect": "rettangolare", "square": "quadrata", "circle": "circolare",
    "triangle": "triangolare", "polygon": "poligonale", "trapezoid": "trapezoidale",
    "cave": "caverna",
}

_CONTENT_HUE_LABELS = [
    ("rust", "Pericolo grave / boss"),
    ("teal", "Incontro"),
    ("plum", "Rischio / trappola"),
    ("violet", "Indizio / enigma"),
    ("slate", "Vuota o poco rilevante"),
]


def _room_summary(lines: list[str], limit: int = 130) -> str:
    # lines[0] is the shape roll, lines[1] is just the "[Room Contents d100=NN]"
    # header - the actual description starts at lines[2].
    body = " ".join(line for line in lines[2:] if line).strip()
    if not body:
        body = "Stanza vuota."
    if len(body) > limit:
        body = body[: limit - 1].rstrip() + "…"
    return body

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

  .dg-map-grid-line { stroke: var(--line); stroke-width: 1; opacity: .35; }
  .dg-map-compass { font: 700 11px system-ui, sans-serif; fill: var(--text-dim); }
  .dg-map-compass-arrow { stroke: var(--text-dim); stroke-width: 1.5; }

  .dg-map-corridor { fill: none; stroke: var(--brass); stroke-width: 7; stroke-linecap: round; stroke-linejoin: round; }
  .dg-map-room-box { fill: var(--bg); stroke: var(--text-dim); stroke-width: 2; }
  .dg-map-room-stripe { stroke: none; opacity: .85; }
  .dg-map-room-stripe.k-rust   { fill: var(--rust); }
  .dg-map-room-stripe.k-teal   { fill: var(--teal); }
  .dg-map-room-stripe.k-plum   { fill: var(--plum); }
  .dg-map-room-stripe.k-violet { fill: var(--violet); }
  .dg-map-room-stripe.k-moss   { fill: var(--moss); }
  .dg-map-room-stripe.k-slate  { fill: var(--slate); opacity: .45; }
  .dg-map-room-number {
    font: 700 12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    fill: var(--text); text-anchor: middle; dominant-baseline: central;
  }
  .dg-map-door-gap { fill: var(--bg-panel); stroke: none; }
  .dg-map-door { stroke: var(--rust); stroke-width: 5; stroke-linecap: butt; }
  .dg-map-stairs { fill: var(--plum); stroke: var(--bg-panel); stroke-width: 1; }
  .dg-map-portal { fill: none; stroke: var(--violet); stroke-width: 2; stroke-dasharray: 3 3; }
  .dg-map-cap { fill: var(--slate); }
  .dg-map-entrance { fill: var(--brass); stroke: var(--bg-panel); stroke-width: 2; }
  .dg-map-arrival { fill: none; stroke: var(--brass); stroke-width: 2; stroke-dasharray: 2 2; }
  .dg-map-label {
    font: 600 10px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    fill: var(--text-dim);
    font-variant-numeric: tabular-nums;
  }
</style>
"""


def _tab_id(level: int) -> str:
    return f"dg-map-lvl-{level}".replace("-", "n") if level < 0 else f"dg-map-lvl-{level}"


def _room_hue(room: dict) -> str:
    return _CONTENT_HUE.get(room.get("content_tag"), "slate")


def _title(lines: list[str]) -> str:
    text = "\n".join(lines) if lines else ""
    return f"<title>{_html.escape(text)}</title>" if text else ""


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


def _svg_for_level(islands: list[dict]) -> str:
    minx, miny, maxx, maxy = _bbox_of_islands(islands)
    w, h = maxx - minx, maxy - miny

    def px(v: float) -> float:
        return round(v * PX, 1)

    parts = []

    # Faint graph-paper grid, one line per grid unit, for scale and orientation.
    grid = []
    x = 0.0
    while x <= w + 0.01:
        grid.append(f'<line x1="{px(x)}" y1="0" x2="{px(x)}" y2="{px(h)}" class="dg-map-grid-line" />')
        x += 1.0
    y = 0.0
    while y <= h + 0.01:
        grid.append(f'<line x1="0" y1="{px(y)}" x2="{px(w)}" y2="{px(y)}" class="dg-map-grid-line" />')
        y += 1.0
    parts.append(f'<g>{"".join(grid)}</g>')

    for island in islands:
        for corridor in island["corridors"]:
            pts = " ".join(f"{px(cx - minx)},{px(cy - miny)}" for cx, cy in corridor["points"])
            if len(corridor["points"]) < 2:
                continue
            parts.append(f'<polyline points="{pts}" class="dg-map-corridor">{_title(corridor["lines"])}</polyline>')

        for room in island["rooms"]:
            cxs = [c[0] for c in room["corners"]]
            cys = [c[1] for c in room["corners"]]
            rx, ry = min(cxs) - minx, min(cys) - miny
            rw, rh = max(cxs) - min(cxs), max(cys) - min(cys)
            hue = _room_hue(room)
            shape_name = _SHAPE_NAMES.get(room["shape"], room["shape"])
            cx_, cy_ = px(rx) + px(rw) / 2, px(ry) + px(rh) / 2
            parts.append(
                f'<g class="dg-map-room">'
                f'<rect x="{px(rx)}" y="{px(ry)}" width="{px(rw)}" height="{px(rh)}" rx="4" '
                f'class="dg-map-room-box">{_title(room["lines"])}</rect>'
                f'<rect x="{px(rx)}" y="{px(ry)}" width="{px(rw)}" height="6" rx="2" '
                f'class="dg-map-room-stripe k-{hue}"><title>Stanza {shape_name} · #{room["id"]}</title></rect>'
                f'<text x="{cx_}" y="{cy_}" class="dg-map-room-number">{room["id"]}</text>'
                f"</g>"
            )

        for door in island["doors"]:
            mx, my = (door["x1"] + door["x2"]) / 2 - minx, (door["y1"] + door["y2"]) / 2 - miny
            ddx, ddy = door["x2"] - door["x1"], door["y2"] - door["y1"]
            length = (ddx ** 2 + ddy ** 2) ** 0.5 or 1.0
            ux, uy = ddx / length, ddy / length  # along the passage
            perp_x, perp_y = -uy, ux
            gap_x, gap_y = ux * 0.5, uy * 0.5  # gap in the wall, wide enough for the door bar
            parts.append(
                f'<line x1="{px(door["x1"] - minx)}" y1="{px(door["y1"] - miny)}" '
                f'x2="{px(mx - gap_x)}" y2="{px(my - gap_y)}" class="dg-map-corridor" />'
                f'<line x1="{px(mx + gap_x)}" y1="{px(my + gap_y)}" '
                f'x2="{px(door["x2"] - minx)}" y2="{px(door["y2"] - miny)}" class="dg-map-corridor" />'
                f'<line x1="{px(mx - perp_x * 0.45)}" y1="{px(my - perp_y * 0.45)}" '
                f'x2="{px(mx + perp_x * 0.45)}" y2="{px(my + perp_y * 0.45)}" '
                f'class="dg-map-door">{_title(door["lines"])}</line>'
            )

        for stair in island["stairs"]:
            sx, sy = px(stair["x"] - minx), px(stair["y"] - miny)
            up = stair["delta"] < 0
            tri = f"{sx},{sy-7} {sx-6},{sy+5} {sx+6},{sy+5}" if up else f"{sx},{sy+7} {sx-6},{sy-5} {sx+6},{sy-5}"
            to_level = stair.get("to_level")
            parts.append(
                f'<polygon points="{tri}" class="dg-map-stairs">{_title(stair["lines"])}</polygon>'
                f'<text x="{sx + 9}" y="{sy + 4}" class="dg-map-label">L{to_level}</text>'
            )

        for portal in island["portals"]:
            px_, py_ = px(portal["x"] - minx), px(portal["y"] - miny)
            parts.append(
                f'<circle cx="{px_}" cy="{py_}" r="7" class="dg-map-portal">'
                f"<title>Portale - prosegue altrove sulla mappa</title></circle>"
            )

        for cap in island["caps"]:
            cx_, cy_ = px(cap["x"] - minx), px(cap["y"] - miny)
            label = "Limite del dungeon" if cap["kind"] == "edge" else "Vicolo cieco"
            parts.append(f'<circle cx="{cx_}" cy="{cy_}" r="4" class="dg-map-cap"><title>{label}</title></circle>')

        ox, oy = island["origin"]
        ox_, oy_ = px(ox - minx), px(oy - miny)
        label = "Ingresso del dungeon" if island.get("is_entrance") else "Punto di arrivo su questa mappa"
        marker_class = "dg-map-entrance" if island.get("is_entrance") else "dg-map-arrival"
        parts.append(f'<circle cx="{ox_}" cy="{oy_}" r="6" class="{marker_class}"><title>{label}</title></circle>')

    compass_x, compass_y = px(w) - 22, 26
    parts.append(
        f'<g class="dg-map-compass">'
        f'<line x1="{compass_x}" y1="{compass_y + 12}" x2="{compass_x}" y2="{compass_y - 6}" class="dg-map-compass-arrow" />'
        f'<line x1="{compass_x}" y1="{compass_y - 6}" x2="{compass_x - 4}" y2="{compass_y + 1}" class="dg-map-compass-arrow" />'
        f'<line x1="{compass_x}" y1="{compass_y - 6}" x2="{compass_x + 4}" y2="{compass_y + 1}" class="dg-map-compass-arrow" />'
        f'<text x="{compass_x}" y="{compass_y + 24}" text-anchor="middle">N</text>'
        f"</g>"
    )

    body = "".join(parts)
    width_px, height_px = px(w), px(h)
    return (
        f'<svg class="dg-map-svg" width="{width_px}" height="{height_px}" '
        f'viewBox="0 0 {width_px} {height_px}" xmlns="http://www.w3.org/2000/svg">{body}</svg>'
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


def render_map_section(dungeon) -> str:
    """A self-contained map section: level tabs (if needed) + one SVG + numbered key per level + legend."""
    layout = compute_layout(dungeon)
    levels = sorted(layout.keys())
    if not levels:
        return ""

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
                f'<div class="dg-map-scroll">{_svg_for_level(layout[level])}</div>'
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
            f'<div class="dg-map-scroll">{_svg_for_level(layout[levels[0]])}</div>'
            f"{_room_key_html(layout[levels[0]])}</div>"
        )
        panel_css = ""
        show_first = '.dg-map-panel[data-for="only"] { display: block; }\n'

    def _icon_corridor():
        return '<svg width="26" height="16" viewBox="0 0 26 16"><line x1="2" y1="8" x2="24" y2="8" class="dg-map-corridor" /></svg>'

    def _icon_door():
        return (
            '<svg width="26" height="16" viewBox="0 0 26 16">'
            '<line x1="2" y1="8" x2="10" y2="8" class="dg-map-corridor" />'
            '<line x1="16" y1="8" x2="24" y2="8" class="dg-map-corridor" />'
            '<line x1="13" y1="3" x2="13" y2="13" class="dg-map-door" /></svg>'
        )

    def _icon_stairs():
        return '<svg width="16" height="16" viewBox="0 0 16 16"><polygon points="8,3 2,13 14,13" class="dg-map-stairs" /></svg>'

    def _icon_portal():
        return '<svg width="16" height="16" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6" class="dg-map-portal" /></svg>'

    def _icon_cap():
        return '<svg width="16" height="16" viewBox="0 0 16 16"><circle cx="8" cy="8" r="4" class="dg-map-cap" /></svg>'

    def _icon_entrance():
        return '<svg width="16" height="16" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6" class="dg-map-entrance" /></svg>'

    legend = (
        '<div class="dg-map-legend">'
        '<span class="dg-map-legend-title">Simboli</span>'
        f'<span class="dg-swatch">{_icon_corridor()}Corridoio</span>'
        f'<span class="dg-swatch">{_icon_door()}Porta</span>'
        f'<span class="dg-swatch">{_icon_stairs()}Scale (▲ su / ▼ giù, con livello di arrivo)</span>'
        f'<span class="dg-swatch">{_icon_portal()}Portale magico</span>'
        f'<span class="dg-swatch">{_icon_cap()}Vicolo cieco / limite mappa</span>'
        f'<span class="dg-swatch">{_icon_entrance()}Ingresso del dungeon</span>'
        '<span class="dg-map-legend-title">Colore stanza = contenuto</span>'
        + "".join(
            f'<span class="dg-swatch"><span class="dg-dot" style="background:var(--{hue})"></span>{label}</span>'
            for hue, label in _CONTENT_HUE_LABELS
        )
        + "</div>"
    )

    tabs_wrap = f'<div class="dg-map-tabs">{labels_html}</div>' if labels_html else ""
    return (
        f"{_MAP_STYLE}<style>{panel_css}{show_first}</style>\n"
        f'<div class="dg-map-wrap">{radios_html}{tabs_wrap}'
        f'<div class="dg-map-panels">{panels_html}</div>'
        f"{legend}</div>"
    )
