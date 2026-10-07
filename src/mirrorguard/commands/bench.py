"""Commands for the benchmark: plan, run, resume, list, report. Also `db` and `models`."""

import argparse
import json
import math
import sys
from dataclasses import asdict

from mirrorguard.benchmark import report
from mirrorguard.benchmark.conversation import ConversationEngine
from mirrorguard.benchmark.judge import Judge
from mirrorguard.benchmark.repository import BenchmarkRepository
from mirrorguard.benchmark.runner import BenchmarkRunner, plan_jobs
from mirrorguard.benchmark.simulator import PersonaSimulator
from mirrorguard.benchmark.types import Job
from mirrorguard.config import Settings, get_settings
from mirrorguard.db import Database
from mirrorguard.llm import LLMError, Message
from mirrorguard.llm.factory import ModelFactory, make_model_factory
from mirrorguard.loader import Library

GUARDRAIL_MODES = {"off": (False,), "on": (True,), "both": (False, True)}


def _split(value: str | None) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()] if value else []


def _jobs(args: argparse.Namespace, library: Library, settings: Settings) -> list[Job]:
    return plan_jobs(
        library,
        _split(args.targets) or settings.target_models,
        scenario_ids=_split(args.scenarios) or None,
        guardrail_modes=GUARDRAIL_MODES[args.guardrail],
        repeats=args.repeats,
    )


def estimate_calls(jobs: list[Job], library: Library, turns: int | None) -> int:
    """Rough number of model calls a run will make, to plan around free-tier limits."""
    total = 0
    for job in jobs:
        n = turns or library.scenarios[job.scenario_id].turns
        persona_calls = n - 1
        judge_calls = math.ceil(n / 8) + 1
        # One risk check per turn. High-risk turns add a reply check, not counted here.
        guardrail_calls = n if job.guardrail else 0
        total += persona_calls + n + judge_calls + guardrail_calls
    return total


def build_runner(
    library: Library,
    repository: BenchmarkRepository,
    settings: Settings,
    models: ModelFactory,
    *,
    turns: int | None,
    concurrency: int | None = None,
) -> BenchmarkRunner:
    from mirrorguard.guardrail.factory import build_target_factory

    return BenchmarkRunner(
        library=library,
        repository=repository,
        engine=ConversationEngine(PersonaSimulator(models(settings.persona_model))),
        judge=Judge(models(settings.judge_model), library.rubric),
        target_factory=build_target_factory(settings, models),
        concurrency=concurrency or settings.benchmark_concurrency,
        turns=turns,
        on_progress=lambda job, status: print(f"  [{status}] {job.key}", flush=True),
    )


async def _execute(run_id: str, runner: BenchmarkRunner, repository: BenchmarkRepository) -> int:
    summary = await runner.run(run_id)
    print(f"Run {run_id}: {summary.done} done, {summary.failed} failed.")
    if summary.failed:
        print(f"Run `mirrorguard bench resume {run_id}` to retry the failed jobs.")
    return 0 if not summary.failed else 2


async def _cmd_db_init(args: argparse.Namespace, library: Library) -> int:
    settings = get_settings()
    database = Database(settings.database_url)
    await database.create_tables()
    await database.dispose()
    print("Database tables are ready.")
    return 0


def _cmd_db_migrate(args: argparse.Namespace, library: Library) -> int:
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    import mirrorguard

    config = Config()
    config.set_main_option("script_location", str(Path(mirrorguard.__file__).parent / "migrations"))
    command.upgrade(config, "head")
    print("Database is up to date.")
    return 0


def _cmd_plan(args: argparse.Namespace, library: Library) -> int:
    jobs = _jobs(args, library, get_settings())
    print(
        f"{len(jobs)} conversations, about {estimate_calls(jobs, library, args.turns)} model calls."
    )
    return 0


async def _cmd_run(args: argparse.Namespace, library: Library) -> int:
    settings = get_settings()
    jobs = _jobs(args, library, settings)
    database = Database(settings.database_url)
    await database.create_tables()
    repository = BenchmarkRepository(database)
    config = {
        "targets": sorted({job.target_model for job in jobs}),
        "persona_model": settings.persona_model,
        "judge_model": settings.judge_model,
        "rubric_version": library.rubric.version,
        "turns": args.turns,
        "repeats": args.repeats,
        "guardrail": args.guardrail,
    }
    run_id = await repository.create_run(args.name, config, jobs, library)
    print(f"Started run {run_id} with {len(jobs)} conversations.")
    runner = build_runner(
        library,
        repository,
        settings,
        make_model_factory(settings),
        turns=args.turns,
        concurrency=args.concurrency,
    )
    try:
        return await _execute(run_id, runner, repository)
    finally:
        await database.dispose()


async def _cmd_resume(args: argparse.Namespace, library: Library) -> int:
    settings = get_settings()
    database = Database(settings.database_url)
    repository = BenchmarkRepository(database)
    try:
        run = await repository.get_run(args.run_id)
        if run is None:
            print(f"No run with id '{args.run_id}'.", file=sys.stderr)
            return 1
        runner = build_runner(
            library,
            repository,
            settings,
            make_model_factory(settings),
            turns=run.config.get("turns"),
            concurrency=args.concurrency,
        )
        return await _execute(run.id, runner, repository)
    finally:
        await database.dispose()


async def _cmd_list_runs(args: argparse.Namespace, library: Library) -> int:
    database = Database(get_settings().database_url)
    repository = BenchmarkRepository(database)
    try:
        rows = []
        for run in await repository.list_runs():
            counts = await repository.status_counts(run.id)
            done, total = counts.get("done", 0), sum(counts.values())
            rows.append([run.id, run.name, run.status, f"{done}/{total}", run.created_at])
        print(report.format_table(["id", "name", "status", "done", "created"], rows))
        return 0
    finally:
        await database.dispose()


async def _cmd_report(args: argparse.Namespace, library: Library) -> int:
    database = Database(get_settings().database_url)
    repository = BenchmarkRepository(database)
    try:
        results = await repository.results(args.run_id)
    finally:
        await database.dispose()
    if not results:
        print("No scored conversations in this run yet.", file=sys.stderr)
        return 1
    board = report.leaderboard(results, library)
    personas = report.by_persona(results)
    effect = report.guardrail_effect(results)
    languages = report.by_language(results, library)
    if args.format == "json":
        payload = {
            "leaderboard": [asdict(row) for row in board],
            "by_persona": [asdict(row) for row in personas],
            "by_language": [asdict(row) for row in languages],
            "guardrail_effect": [asdict(row) for row in effect],
        }
        print(json.dumps(payload, indent=2))
        return 0
    print("Leaderboard (0 is honest, 1 is very sycophantic)\n")
    print(
        report.format_table(
            ["model", "guardrail", "n", "score", "vulnerable", "control", "gap"],
            [list(asdict(row).values()) for row in board],
        )
    )
    print("\nBy persona\n")
    print(
        report.format_table(
            ["model", "guardrail", "persona", "n", "score"],
            [list(asdict(row).values()) for row in personas],
        )
    )
    if len({row.language for row in languages}) > 1:
        print("\nBy language (vulnerable personas only)\n")
        print(
            report.format_table(
                ["model", "guardrail", "language", "n", "score"],
                [list(asdict(row).values()) for row in languages],
            )
        )
    if effect:
        print("\nGuardrail effect (a positive reduction means the guardrail helped)\n")
        print(
            report.format_table(
                ["model", "persona", "off", "on", "reduction"],
                [list(asdict(row).values()) for row in effect],
            )
        )
    return 0


async def _cmd_models_check(args: argparse.Namespace, library: Library) -> int:
    settings = get_settings()
    models = make_model_factory(settings)
    names = sorted(
        {
            settings.persona_model,
            settings.judge_model,
            settings.risk_model,
            settings.rewriter_model,
            *settings.target_models,
        }
    )
    failures = 0
    for name in names:
        try:
            await models(name).complete(
                [Message(role="user", content="Reply with the single word OK.")], max_tokens=20
            )
            print(f"  ok      {name}")
        except LLMError as exc:
            failures += 1
            print(f"  FAILED  {name}: {str(exc)[:160]}")
    return 0 if not failures else 1


def _cmd_serve(args: argparse.Namespace, library: Library) -> int:
    import uvicorn

    uvicorn.run(
        "mirrorguard.api.app:app_from_settings",
        factory=True,
        host=args.host,
        port=args.port,
        workers=args.workers,
    )
    return 0


def _add_job_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--targets", help="comma-separated models (default: MG_TARGET_MODELS)")
    parser.add_argument("--scenarios", help="comma-separated scenario ids (default: all)")
    parser.add_argument("--turns", type=int, help="turns per conversation (default: per scenario)")
    parser.add_argument("--repeats", type=int, default=1, help="runs of each job (default: 1)")
    parser.add_argument("--guardrail", choices=list(GUARDRAIL_MODES), default="off")


def register(sub: argparse._SubParsersAction) -> None:
    db_sub = sub.add_parser("db", help="database commands").add_subparsers(required=True)
    db_sub.add_parser("init", help="create the tables directly (local SQLite)").set_defaults(
        handler=_cmd_db_init
    )
    db_sub.add_parser("migrate", help="bring a production database up to date").set_defaults(
        handler=_cmd_db_migrate
    )

    models_sub = sub.add_parser("models", help="model commands").add_subparsers(required=True)
    models_sub.add_parser("check", help="check that every configured model answers").set_defaults(
        handler=_cmd_models_check
    )

    serve = sub.add_parser("serve", help="start the guardrail API server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--workers", type=int, default=1, help="server processes to run")
    serve.set_defaults(handler=_cmd_serve)

    bench_sub = sub.add_parser("bench", help="benchmark commands").add_subparsers(required=True)

    plan = bench_sub.add_parser("plan", help="show how big a run would be, without running it")
    _add_job_options(plan)
    plan.set_defaults(handler=_cmd_plan)

    run = bench_sub.add_parser("run", help="start a benchmark run")
    _add_job_options(run)
    run.add_argument("--name", default="benchmark", help="a label for this run")
    run.add_argument("--concurrency", type=int, help="conversations to run at once")
    run.set_defaults(handler=_cmd_run)

    resume = bench_sub.add_parser("resume", help="continue a run that stopped or had failures")
    resume.add_argument("run_id")
    resume.add_argument("--concurrency", type=int)
    resume.set_defaults(handler=_cmd_resume)

    bench_sub.add_parser("list", help="list benchmark runs").set_defaults(handler=_cmd_list_runs)

    rep = bench_sub.add_parser("report", help="show the results of a run")
    rep.add_argument("run_id")
    rep.add_argument("--format", choices=["table", "json"], default="table")
    rep.set_defaults(handler=_cmd_report)
