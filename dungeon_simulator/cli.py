"""Command-line entry point for the dungeon simulator."""

from __future__ import annotations

import argparse
import json
import sys

from .generator import DEFAULT_LIMITLESS_ROOMS, DEFAULT_PARTY_LEVEL, DungeonGenerator
from .render import render_html, render_text, to_dict


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dungeon-simulator",
        description="Procedurally generate a solo dungeon crawl from the size/type/room/passage/door/stairs tables.",
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed, for a reproducible dungeon.")
    parser.add_argument("--format", choices=["text", "json", "html"], default="text",
                         help="Output format. 'html' produces a browsable, collapsible tree view.")
    parser.add_argument("--verbose-empty", action="store_true",
                         help="Also print explicit 'empty' results for passage contents rolls.")
    parser.add_argument("--limitless-cap", type=int, default=DEFAULT_LIMITLESS_ROOMS,
                         help="Room cap used when the Dungeon Size Table rolls 'Limitless'.")
    parser.add_argument("--party-level", type=int, default=DEFAULT_PARTY_LEVEL,
                         help="Party level, used by the Trap Table's level-scaled damage.")
    parser.add_argument("--max-depth", type=int, default=None,
                         help="Cap exploration to this many room/passage/door/stairs hops from the "
                              "entrance, on top of the Dungeon Size Table's own room-count budget.")
    parser.add_argument("-o", "--output", type=str, default=None, help="Write output to this file instead of stdout.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    generator = DungeonGenerator(
        seed=args.seed,
        limitless_room_cap=args.limitless_cap,
        verbose_empty=args.verbose_empty,
        party_level=args.party_level,
        max_depth=args.max_depth,
    )
    dungeon = generator.generate()

    if args.format == "json":
        output = json.dumps(to_dict(dungeon), indent=2)
    elif args.format == "html":
        output = render_html(dungeon)
    else:
        output = render_text(dungeon)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(output + "\n")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
