"""Commands for judge validation: make labelling sheets and compare labels."""

import argparse
import sys
from pathlib import Path

from mirrorguard.benchmark.report import format_table
from mirrorguard.benchmark.repository import BenchmarkRepository
from mirrorguard.config import get_settings
from mirrorguard.db import Database
from mirrorguard.loader import Library
from mirrorguard.validation import labels


async def _conversations(run_id: str):
    database = Database(get_settings().database_url)
    try:
        return await BenchmarkRepository(database).scored_conversations(run_id)
    finally:
        await database.dispose()


async def _cmd_export(args: argparse.Namespace, library: Library) -> int:
    conversations = await _conversations(args.run_id)
    if not conversations:
        print("No scored conversations in this run.", file=sys.stderr)
        return 1
    summaries = {p.id: p.summary for p in library.personas.values()}
    count = labels.write_sheet(
        Path(args.out), conversations, library.rubric, summaries, sample=args.sample, seed=args.seed
    )
    print(f"Wrote {count} conversations to {args.out}.")
    print("Give one copy to each rater. They fill each measure with 0, 0.5 or 1,")
    print("or leave it blank when it does not apply. See docs/RUBRIC.md for the meanings.")
    return 0


def _print(title: str, comparison: labels.Comparison) -> None:
    print(f"\n{title}\n")
    print(
        format_table(
            ["measure", "pairs", "kappa", "mean error"],
            [[m.measure_id, m.pairs, m.kappa, m.mean_absolute_error] for m in comparison.measures],
        )
    )
    if comparison.overall:
        o = comparison.overall
        print(
            "\nOverall verdict (sycophantic or not): "
            f"accuracy {o.accuracy:.2f}, precision {_show(o.precision)}, "
            f"recall {_show(o.recall)}, F1 {_show(o.f1)}"
        )


def _show(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


async def _cmd_compare(args: argparse.Namespace, library: Library) -> int:
    try:
        sheets = [labels.read_sheet(Path(path), library.rubric) for path in args.sheets]
    except (ValueError, OSError) as exc:
        print(f"Could not read the sheets: {exc}", file=sys.stderr)
        return 1
    judge = labels.judge_labels(await _conversations(args.run_id), library.rubric)
    if len(sheets) >= 2:
        _print("Rater 1 against rater 2", labels.compare(sheets[0], sheets[1], library.rubric))
    for number, sheet in enumerate(sheets, start=1):
        _print(f"Judge against rater {number}", labels.compare(judge, sheet, library.rubric))
    print("\nKappa: 1 is perfect agreement, 0 is chance. Above 0.6 is usually called good.")
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    labels_sub = sub.add_parser("labels", help="human labelling commands").add_subparsers(
        required=True
    )
    export = labels_sub.add_parser("export", help="write a blind labelling sheet for raters")
    export.add_argument("run_id")
    export.add_argument("--out", default="labels.csv")
    export.add_argument("--sample", type=int, help="how many conversations (default: all)")
    export.add_argument("--seed", type=int, default=0)
    export.set_defaults(handler=_cmd_export)

    compare = labels_sub.add_parser("compare", help="compare filled-in sheets with the judge")
    compare.add_argument("run_id")
    compare.add_argument("sheets", nargs="+", help="one filled-in CSV per rater")
    compare.set_defaults(handler=_cmd_compare)
