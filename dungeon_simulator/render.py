"""Turn a generated Dungeon into human-readable text, a JSON-able dict, or a browsable HTML page."""

from __future__ import annotations

import html as _html

from .models import Dungeon, Node

_KIND_LABELS = {
    "start": "ENTRANCE",
    "room": "ROOM",
    "passage": "PASSAGE",
    "door": "DOOR",
    "stairs": "STAIRS",
    "edge": "EDGE OF DUNGEON",
    "dead_end": "DEAD END",
}

# Italian labels + a categorical hue per node kind, for the HTML tree view.
_KIND_META = {
    "start": ("Ingresso", "violet"),
    "room": ("Stanza", "moss"),
    "passage": ("Passaggio", "teal"),
    "door": ("Porta", "rust"),
    "stairs": ("Scale", "plum"),
    "edge": ("Limite del dungeon", "slate"),
    "dead_end": ("Vicolo cieco", "slate"),
}


def render_text(dungeon: Dungeon) -> str:
    out = []
    out.append("=" * 60)
    out.append("DUNGEON SIMULATOR")
    out.append("=" * 60)
    out.append(f"Type: {dungeon.dungeon_type}")
    out.append(f"Size: {dungeon.size_label}")
    out.append(f"Seed: {dungeon.seed}")
    out.append(f"Rooms generated: {dungeon.room_count} / target {dungeon.target_rooms}")
    out.append(f"Total nodes: {dungeon.node_count}")
    out.append("")
    _render_node(dungeon.root, depth=0, out=out)
    return "\n".join(out)


def _render_node(node: Node, depth: int, out: list[str]) -> None:
    indent = "  " * depth
    label = _KIND_LABELS.get(node.kind, node.kind.upper())
    out.append(f"{indent}- [{label}] (level {node.level}, #{node.id})")
    for line in node.lines:
        out.append(f"{indent}    {line}")
    for child in node.children:
        _render_node(child, depth + 1, out)


def to_dict(dungeon: Dungeon) -> dict:
    return {
        "dungeon_type": dungeon.dungeon_type,
        "size_label": dungeon.size_label,
        "target_rooms": dungeon.target_rooms,
        "seed": dungeon.seed,
        "room_count": dungeon.room_count,
        "node_count": dungeon.node_count,
        "root": _node_to_dict(dungeon.root),
    }


def _node_to_dict(node: Node) -> dict:
    return {
        "id": node.id,
        "kind": node.kind,
        "level": node.level,
        "lines": node.lines,
        "children": [_node_to_dict(child) for child in node.children],
    }


# ---------------------------------------------------------------------------
# HTML tree view - a self-contained, theme-aware "expedition ledger" page.
# ---------------------------------------------------------------------------

_HTML_STYLE = """
<style>
  :root {
    --bg: #f2f3f7;
    --bg-panel: #ffffff;
    --text: #1c1e27;
    --text-dim: #5b5f6e;
    --line: #d7dae2;
    --brass: #a9701f;
    --brass-ink: #ffffff;
    --moss: #3f7a4a; --moss-ink: #ffffff;
    --teal: #2f6b73; --teal-ink: #ffffff;
    --rust: #a44f24; --rust-ink: #ffffff;
    --plum: #6b4fa0; --plum-ink: #ffffff;
    --violet: #5a55a8; --violet-ink: #ffffff;
    --slate: #6b7280; --slate-ink: #ffffff;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg: #12141b;
      --bg-panel: #1a1d26;
      --text: #e7e6e2;
      --text-dim: #9a9eab;
      --line: #2b2f3a;
      --brass: #c8933b; --brass-ink: #1a1204;
      --moss: #6fae78; --moss-ink: #0c1a0e;
      --teal: #57a3ac; --teal-ink: #06181a;
      --rust: #d5814c; --rust-ink: #1c0d03;
      --plum: #a891d6; --plum-ink: #180f26;
      --violet: #9891df; --violet-ink: #130f28;
      --slate: #8c93a3; --slate-ink: #12141b;
    }
  }
  :root[data-theme="dark"] {
    --bg: #12141b;
    --bg-panel: #1a1d26;
    --text: #e7e6e2;
    --text-dim: #9a9eab;
    --line: #2b2f3a;
    --brass: #c8933b; --brass-ink: #1a1204;
    --moss: #6fae78; --moss-ink: #0c1a0e;
    --teal: #57a3ac; --teal-ink: #06181a;
    --rust: #d5814c; --rust-ink: #1c0d03;
    --plum: #a891d6; --plum-ink: #180f26;
    --violet: #9891df; --violet-ink: #130f28;
    --slate: #8c93a3; --slate-ink: #12141b;
  }

  .dg-app, .dg-app * { box-sizing: border-box; }
  .dg-app {
    background: var(--bg);
    color: var(--text);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    max-width: 46rem;
    margin: 0 auto;
    padding: 1.75rem 1.25rem 3rem;
    line-height: 1.45;
  }
  .dg-header {
    background: var(--bg-panel);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 1.1rem 1.4rem 1.3rem;
    margin-bottom: 1.1rem;
  }
  .dg-header h1 {
    font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
    font-size: 1.5rem;
    font-weight: 700;
    margin: 0 0 .6rem;
    text-wrap: balance;
    border-bottom: 2px double var(--line);
    padding-bottom: .5rem;
  }
  .dg-meta-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: .35rem 1.5rem;
    font-size: .88rem;
  }
  .dg-meta-grid dt { color: var(--text-dim); }
  .dg-meta-grid dd { margin: 0; font-variant-numeric: tabular-nums; }
  .dg-meta-grid > div { display: flex; justify-content: space-between; gap: .5rem; }

  .dg-toolbar { display: flex; gap: .6rem; margin-bottom: 1.1rem; }
  .dg-toolbar button {
    font: inherit;
    font-size: .82rem;
    font-weight: 600;
    background: var(--brass);
    color: var(--brass-ink);
    border: none;
    border-radius: 7px;
    padding: .45rem .85rem;
    cursor: pointer;
  }
  .dg-toolbar button:focus-visible, .dg-node > summary:focus-visible {
    outline: 2px solid var(--brass);
    outline-offset: 2px;
  }

  .dg-tree { border-left: 2px solid var(--line); padding-left: .9rem; }
  details.dg-node {
    margin: .3rem 0;
  }
  details.dg-node > summary {
    list-style: none;
    cursor: pointer;
    display: flex;
    align-items: baseline;
    gap: .55rem;
    padding: .15rem 0;
  }
  details.dg-node > summary::-webkit-details-marker { display: none; }
  details.dg-node > summary::before {
    content: "\\25B8";
    color: var(--text-dim);
    display: inline-block;
    width: 1em;
    transition: transform .15s ease;
  }
  details.dg-node[open] > summary::before { transform: rotate(90deg); }
  @media (prefers-reduced-motion: reduce) {
    details.dg-node > summary::before { transition: none; }
  }

  .dg-badge {
    font-size: .72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .03em;
    padding: .15rem .55rem;
    border-radius: 999px;
    white-space: nowrap;
  }
  .dg-badge.k-violet { background: var(--violet); color: var(--violet-ink); }
  .dg-badge.k-moss   { background: var(--moss);   color: var(--moss-ink); }
  .dg-badge.k-teal   { background: var(--teal);   color: var(--teal-ink); }
  .dg-badge.k-rust   { background: var(--rust);   color: var(--rust-ink); }
  .dg-badge.k-plum   { background: var(--plum);   color: var(--plum-ink); }
  .dg-badge.k-slate  { background: var(--slate);  color: var(--slate-ink); }

  .dg-idlevel { color: var(--text-dim); font-size: .8rem; font-variant-numeric: tabular-nums; }

  ul.dg-lines {
    margin: .3rem 0 .3rem 1.5rem;
    padding: 0;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: .8rem;
    color: var(--text);
  }
  ul.dg-lines li { margin: .12rem 0; }

  .dg-children {
    margin-left: .5rem;
    padding-left: .9rem;
    border-left: 2px solid var(--line);
  }
</style>
"""

_HTML_SCRIPT = """
<script>
  document.getElementById('dg-expand').addEventListener('click', () => {
    document.querySelectorAll('.dg-tree details').forEach((d) => { d.open = true; });
  });
  document.getElementById('dg-collapse').addEventListener('click', () => {
    document.querySelectorAll('.dg-tree details').forEach((d) => { d.open = false; });
  });
</script>
"""


def _node_to_html(node: Node, depth: int = 0) -> str:
    label, hue = _KIND_META.get(node.kind, (node.kind.title(), "slate"))
    lines_html = "".join(f"<li>{_html.escape(line)}</li>" for line in node.lines)
    children_html = "".join(_node_to_html(child, depth + 1) for child in node.children)
    open_attr = " open" if depth <= 1 else ""
    summary = (
        f'<span class="dg-badge k-{hue}">{_html.escape(label)}</span>'
        f'<span class="dg-idlevel">livello {node.level} &middot; #{node.id}</span>'
    )
    inner = f'<ul class="dg-lines">{lines_html}</ul>' if lines_html else ""
    children_wrap = f'<div class="dg-children">{children_html}</div>' if children_html else ""
    return f'<details class="dg-node"{open_attr}><summary>{summary}</summary>{inner}{children_wrap}</details>'


def render_html_body(dungeon: Dungeon) -> str:
    """The inner content of the HTML tree view (no doctype/html/head/body wrapper).

    Suitable for embedding directly in a page body, e.g. via Artifact.
    """
    tree_html = _node_to_html(dungeon.root)
    return f"""{_HTML_STYLE}
<div class="dg-app">
  <div class="dg-header">
    <h1>{_html.escape(dungeon.dungeon_type)}</h1>
    <dl class="dg-meta-grid">
      <div><dt>Dimensione</dt><dd>{_html.escape(dungeon.size_label)}</dd></div>
      <div><dt>Seed</dt><dd>{dungeon.seed}</dd></div>
      <div><dt>Stanze</dt><dd>{dungeon.room_count} / {dungeon.target_rooms}</dd></div>
      <div><dt>Nodi esplorati</dt><dd>{dungeon.node_count}</dd></div>
    </dl>
  </div>
  <div class="dg-toolbar">
    <button id="dg-expand" type="button">Espandi tutto</button>
    <button id="dg-collapse" type="button">Comprimi tutto</button>
  </div>
  <div class="dg-tree">{tree_html}</div>
</div>
{_HTML_SCRIPT}"""


def render_html(dungeon: Dungeon) -> str:
    """A full, standalone HTML document - open it directly in a browser."""
    title = f"Dungeon: {dungeon.dungeon_type} ({dungeon.size_label})"
    return (
        "<!doctype html>\n"
        f'<html lang="it"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_html.escape(title)}</title></head><body>"
        f"{render_html_body(dungeon)}"
        "</body></html>"
    )
