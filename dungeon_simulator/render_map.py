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
  .dg-map-panel { display: none; padding: .5rem; overflow: auto; max-height: 70vh; }
  .dg-map-svg { display: block; }
  .dg-map-legend {
    display: flex; flex-wrap: wrap; gap: .5rem 1rem; padding: .6rem .9rem .8rem;
    font-size: .74rem; color: var(--text-dim); border-top: 1px solid var(--line);
  }
  .dg-map-legend .dg-swatch { display: inline-flex; align-items: center; gap: .35rem; }
  .dg-map-legend .dg-dot { width: .6rem; height: .6rem; border-radius: 2px; display: inline-block; }

  .dg-map-corridor { fill: none; stroke: var(--brass); stroke-width: 6; stroke-linecap: round; stroke-linejoin: round; opacity: .55; }
  .dg-map-room-box { fill: var(--bg); stroke: var(--line); stroke-width: 1.5; }
  .dg-map-room-stripe { stroke: none; }
  .dg-map-room-stripe.k-rust   { fill: var(--rust); }
  .dg-map-room-stripe.k-teal   { fill: var(--teal); }
  .dg-map-room-stripe.k-plum   { fill: var(--plum); }
  .dg-map-room-stripe.k-violet { fill: var(--violet); }
  .dg-map-room-stripe.k-moss   { fill: var(--moss); }
  .dg-map-room-stripe.k-slate  { fill: var(--slate); opacity: .5; }
  .dg-map-door { stroke: var(--rust); stroke-width: 4; stroke-linecap: round; }
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
            parts.append(
                f'<g class="dg-map-room">'
                f'<rect x="{px(rx)}" y="{px(ry)}" width="{px(rw)}" height="{px(rh)}" rx="4" '
                f'class="dg-map-room-box">{_title(room["lines"])}</rect>'
                f'<rect x="{px(rx)}" y="{px(ry)}" width="{px(rw)}" height="5" rx="2" '
                f'class="dg-map-room-stripe k-{hue}"><title>Stanza {shape_name} · #{room["id"]}</title></rect>'
                f"</g>"
            )

        for door in island["doors"]:
            mx, my = (door["x1"] + door["x2"]) / 2 - minx, (door["y1"] + door["y2"]) / 2 - miny
            ddx, ddy = door["x2"] - door["x1"], door["y2"] - door["y1"]
            perp_x, perp_y = -ddy, ddx
            norm = (perp_x ** 2 + perp_y ** 2) ** 0.5 or 1.0
            perp_x, perp_y = perp_x / norm * 0.4, perp_y / norm * 0.4
            parts.append(
                f'<line x1="{px(door["x1"] - minx)}" y1="{px(door["y1"] - miny)}" '
                f'x2="{px(door["x2"] - minx)}" y2="{px(door["y2"] - miny)}" class="dg-map-corridor" />'
                f'<line x1="{px(mx - perp_x)}" y1="{px(my - perp_y)}" x2="{px(mx + perp_x)}" y2="{px(my + perp_y)}" '
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

    body = "".join(parts)
    width_px, height_px = px(w), px(h)
    return (
        f'<svg class="dg-map-svg" width="{width_px}" height="{height_px}" '
        f'viewBox="0 0 {width_px} {height_px}" xmlns="http://www.w3.org/2000/svg">{body}</svg>'
    )


def render_map_section(dungeon) -> str:
    """A self-contained map section: level tabs (if needed) + one SVG per level + legend."""
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
                f'<div class="dg-map-panel" data-for="{_tab_id(level)}">{_svg_for_level(layout[level])}</div>'
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
        panels_html = f'<div class="dg-map-panel" data-for="only">{_svg_for_level(layout[levels[0]])}</div>'
        panel_css = ""
        show_first = '.dg-map-panel[data-for="only"] { display: block; }\n'

    legend = (
        '<div class="dg-map-legend">'
        '<span class="dg-swatch"><span class="dg-dot" style="background:var(--brass)"></span>Corridoio</span>'
        '<span class="dg-swatch"><span class="dg-dot" style="background:var(--rust)"></span>Porta / pericolo</span>'
        '<span class="dg-swatch"><span class="dg-dot" style="background:var(--teal)"></span>Incontro</span>'
        '<span class="dg-swatch"><span class="dg-dot" style="background:var(--plum)"></span>Scale / rischio</span>'
        '<span class="dg-swatch"><span class="dg-dot" style="background:var(--violet)"></span>Indizio / enigma</span>'
        '<span class="dg-swatch"><span class="dg-dot" style="background:var(--slate)"></span>Vuoto / limite</span>'
        "</div>"
    )

    tabs_wrap = f'<div class="dg-map-tabs">{labels_html}</div>' if labels_html else ""
    return (
        f"{_MAP_STYLE}<style>{panel_css}{show_first}</style>\n"
        f'<div class="dg-map-wrap">{radios_html}{tabs_wrap}'
        f'<div class="dg-map-panels">{panels_html}</div>'
        f"{legend}</div>"
    )
