"""Plans benchmark jobs and runs them, a few at a time, saving as it goes."""

import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import product

from mirrorguard.benchmark.conversation import ConversationEngine
from mirrorguard.benchmark.judge import Judge
from mirrorguard.benchmark.repository import BenchmarkRepository, PendingJob
from mirrorguard.benchmark.types import Job
from mirrorguard.llm import ChatModel
from mirrorguard.loader import Library

log = logging.getLogger(__name__)

TargetFactory = Callable[[Job], ChatModel]
ProgressCallback = Callable[[Job, str], None]


def plan_jobs(
    library: Library,
    targets: Sequence[str],
    *,
    scenario_ids: Sequence[str] | None = None,
    guardrail_modes: Sequence[bool] = (False,),
    repeats: int = 1,
) -> list[Job]:
    """Every combination of scenario, target model, guardrail mode and repeat."""
    if not targets:
        raise ValueError("at least one target model is needed")
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    chosen = list(scenario_ids) if scenario_ids else list(library.scenarios)
    unknown = [s for s in chosen if s not in library.scenarios]
    if unknown:
        raise ValueError(f"unknown scenarios: {', '.join(unknown)}")
    return [
        Job(scenario_id, target, guardrail, repeat)
        for scenario_id, target, guardrail, repeat in product(
            chosen, targets, guardrail_modes, range(repeats)
        )
    ]


@dataclass(frozen=True)
class RunSummary:
    done: int
    failed: int


class BenchmarkRunner:
    """Safe to stop and start again: finished jobs are skipped, half-done ones resume."""

    def __init__(
        self,
        *,
        library: Library,
        repository: BenchmarkRepository,
        engine: ConversationEngine,
        judge: Judge,
        target_factory: TargetFactory,
        concurrency: int = 4,
        turns: int | None = None,
        on_progress: ProgressCallback | None = None,
    ):
        self._library = library
        self._repository = repository
        self._engine = engine
        self._judge = judge
        self._target_factory = target_factory
        self._concurrency = concurrency
        self._turns = turns
        self._on_progress = on_progress

    async def _run_job(self, pending: PendingJob) -> bool:
        job = pending.job
        scenario = self._library.scenarios[job.scenario_id]
        persona = self._library.personas[scenario.persona_id]
        try:
            transcript = pending.transcript
            if transcript is None:
                target = self._target_factory(job)
                transcript = await self._engine.run(persona, scenario, target, turns=self._turns)
                await self._repository.save_transcript(
                    pending.conversation_id, transcript, getattr(target, "trace", None)
                )
            score = await self._judge.score(persona, scenario, transcript)
            await self._repository.save_score(pending.conversation_id, score)
        except Exception as exc:  # one bad job must not stop a long run
            log.warning("job %s failed: %s", job.key, exc)
            await self._repository.save_failure(
                pending.conversation_id, f"{type(exc).__name__}: {exc}"
            )
            self._report(job, "failed")
            return False
        self._report(job, "done")
        return True

    def _report(self, job: Job, status: str) -> None:
        if self._on_progress is not None:
            self._on_progress(job, status)

    async def run(self, run_id: str) -> RunSummary:
        pending = await self._repository.unfinished_jobs(run_id)
        await self._repository.set_run_status(run_id, "running")
        slots = asyncio.Semaphore(self._concurrency)

        async def guarded(item: PendingJob) -> bool:
            async with slots:
                return await self._run_job(item)

        outcomes = await asyncio.gather(*(guarded(item) for item in pending))
        failed = outcomes.count(False)
        await self._repository.set_run_status(run_id, "finished" if not failed else "incomplete")
        return RunSummary(done=outcomes.count(True), failed=failed)
