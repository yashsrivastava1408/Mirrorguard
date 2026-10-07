"""Command line tool: check, list and show the test material."""

import argparse
import sys
from pathlib import Path

from mirrorguard.loader import Library, LibraryError, load_library
from mirrorguard.render import render_personas, render_rubric


def _cmd_validate(library: Library, args: argparse.Namespace) -> int:
    controls = sum(1 for p in library.personas.values() if p.is_control)
    print("Library is valid.")
    print(f"  personas : {len(library.personas)} ({controls} control)")
    print(f"  scenarios: {len(library.scenarios)}")
    print(f"  measures : {len(library.rubric.measures)} (rubric version {library.rubric.version})")
    return 0


def _cmd_list(library: Library, args: argparse.Namespace) -> int:
    if args.what == "personas":
        for p in library.personas.values():
            kind = "control" if p.is_control else p.vulnerability_state.value
            print(f"{p.id:<22} {kind:<18} {p.name}")
    elif args.what == "scenarios":
        for s in library.scenarios.values():
            print(f"{s.id:<34} {s.persona_id:<22} {s.title}")
    else:
        for m in library.rubric.measures:
            print(f"{m.id:<26} {m.weight:<6.2f} {m.name}")
    return 0


def _cmd_show(library: Library, args: argparse.Namespace) -> int:
    item = library.personas.get(args.id) or library.scenarios.get(args.id)
    if item is None:
        print(f"No persona or scenario with id '{args.id}'.", file=sys.stderr)
        return 1
    for field, value in item.model_dump(mode="json").items():
        if isinstance(value, list):
            print(f"{field}:")
            for entry in value:
                print(f"  - {entry}")
        elif isinstance(value, dict):
            print(f"{field}:")
            for key, entry in value.items():
                print(f"  {key}: {entry}")
        else:
            print(f"{field}: {value}")
    return 0


def _cmd_export_docs(library: Library, args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "RUBRIC.md").write_text(render_rubric(library), encoding="utf-8")
    (out / "PERSONAS.md").write_text(render_personas(library), encoding="utf-8")
    print(f"Wrote {out / 'RUBRIC.md'} and {out / 'PERSONAS.md'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mirrorguard", description=__doc__)
    parser.add_argument("--data-dir", help="folder with personas/, scenarios/ and rubric.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate", help="check the test material for mistakes")

    list_parser = sub.add_parser("list", help="list personas, scenarios or measures")
    list_parser.add_argument("what", choices=["personas", "scenarios", "measures"])

    show_parser = sub.add_parser("show", help="show one persona or scenario")
    show_parser.add_argument("id")

    docs_parser = sub.add_parser("export-docs", help="write RUBRIC.md and PERSONAS.md")
    docs_parser.add_argument("--out", default="docs", help="output folder (default: docs)")
    return parser


COMMANDS = {
    "validate": _cmd_validate,
    "list": _cmd_list,
    "show": _cmd_show,
    "export-docs": _cmd_export_docs,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        library = load_library(Path(args.data_dir) if args.data_dir else None)
    except LibraryError as exc:
        print(f"Library has {len(exc.problems)} problem(s):", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    return COMMANDS[args.command](library, args)


if __name__ == "__main__":
    sys.exit(main())
