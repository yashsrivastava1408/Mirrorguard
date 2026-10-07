"""The `mirrorguard` command line tool."""

import argparse
import asyncio
import inspect
import sys
from pathlib import Path

from dotenv import load_dotenv

from mirrorguard.commands import admin, bench, db, labels, library, models, serve
from mirrorguard.library.loader import LibraryError, load_library


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mirrorguard", description=__doc__)
    parser.add_argument("--data-dir", help="folder with personas/, scenarios/ and rubric.yaml")
    sub = parser.add_subparsers(dest="command", required=True)
    for group in (library, bench, labels, models, serve, db, admin):
        group.register(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    try:
        loaded = load_library(Path(args.data_dir) if args.data_dir else None)
    except LibraryError as exc:
        print(f"Library has {len(exc.problems)} problem(s):", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    outcome = args.handler(args, loaded)
    return asyncio.run(outcome) if inspect.isawaitable(outcome) else outcome


if __name__ == "__main__":
    sys.exit(main())
