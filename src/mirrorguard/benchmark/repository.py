"""Saves and loads benchmark runs. The only benchmark code that touches the database."""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select, update

from mirrorguard.benchmark.types import ConversationScore, Job, Result
from mirrorguard.db import Database
from mirrorguard.db.models import BenchmarkRun, ConversationRecord, ScoreRecord, now
from mirrorguard.llm import Message
from mirrorguard.loader import Library


@dataclass(frozen=True)
class PendingJob:
    conversation_id: str
    job: Job
    transcript: list[Message] | None


@dataclass(frozen=True)
class ScoredConversation:
    conversation_id: str
    scenario_id: str
    persona_id: str
    target_model: str
    guardrail: bool
    transcript: list[Message]
    measure_scores: dict[str, float | None]
    total: float
    summary: str


class BenchmarkRepository:
    def __init__(self, database: Database):
        self._db = database

    async def create_run(
        self, name: str, config: dict, jobs: Sequence[Job], library: Library
    ) -> str:
        async with self._db.session() as session, session.begin():
            run = BenchmarkRun(name=name, config=config)
            session.add(run)
            await session.flush()
            session.add_all(
                ConversationRecord(
                    run_id=run.id,
                    job_key=job.key,
                    scenario_id=job.scenario_id,
                    persona_id=library.scenarios[job.scenario_id].persona_id,
                    target_model=job.target_model,
                    guardrail=job.guardrail,
                    repeat=job.repeat,
                )
                for job in jobs
            )
            return run.id

    async def get_run(self, run_id: str) -> BenchmarkRun | None:
        async with self._db.session() as session:
            return await session.get(BenchmarkRun, run_id)

    async def list_runs(self) -> list[BenchmarkRun]:
        async with self._db.session() as session:
            rows = await session.scalars(
                select(BenchmarkRun).order_by(BenchmarkRun.created_at.desc())
            )
            return list(rows)

    async def set_run_status(self, run_id: str, status: str) -> None:
        async with self._db.session() as session, session.begin():
            await session.execute(
                update(BenchmarkRun).where(BenchmarkRun.id == run_id).values(status=status)
            )

    async def unfinished_jobs(self, run_id: str) -> list[PendingJob]:
        """Jobs still to do. A job whose conversation is saved only needs judging."""
        async with self._db.session() as session:
            rows = await session.scalars(
                select(ConversationRecord)
                .where(ConversationRecord.run_id == run_id, ConversationRecord.status != "done")
                .order_by(ConversationRecord.job_key)
            )
            return [
                PendingJob(
                    conversation_id=row.id,
                    job=Job(row.scenario_id, row.target_model, row.guardrail, row.repeat),
                    transcript=(
                        [Message.model_validate(m) for m in row.transcript]
                        if row.transcript
                        else None
                    ),
                )
                for row in rows
            ]

    async def save_transcript(
        self, conversation_id: str, transcript: Sequence[Message], trace: list | None = None
    ) -> None:
        async with self._db.session() as session, session.begin():
            await session.execute(
                update(ConversationRecord)
                .where(ConversationRecord.id == conversation_id)
                .values(
                    transcript=[m.model_dump() for m in transcript],
                    guardrail_trace=trace,
                    status="conversed",
                    error=None,
                )
            )

    async def save_score(self, conversation_id: str, score: ConversationScore) -> None:
        async with self._db.session() as session, session.begin():
            session.add(
                ScoreRecord(
                    conversation_id=conversation_id,
                    judge_model=score.judge_model,
                    rubric_version=score.rubric_version,
                    measure_scores=score.measure_scores,
                    turn_scores=score.turn_scores,
                    total=score.total,
                    summary=score.summary,
                )
            )
            await session.execute(
                update(ConversationRecord)
                .where(ConversationRecord.id == conversation_id)
                .values(status="done", finished_at=now())
            )

    async def save_failure(self, conversation_id: str, error: str) -> None:
        async with self._db.session() as session, session.begin():
            await session.execute(
                update(ConversationRecord)
                .where(ConversationRecord.id == conversation_id)
                .values(status="failed", error=error[:2000])
            )

    async def status_counts(self, run_id: str) -> dict[str, int]:
        async with self._db.session() as session:
            rows = await session.scalars(
                select(ConversationRecord.status).where(ConversationRecord.run_id == run_id)
            )
            counts: dict[str, int] = {}
            for status in rows:
                counts[status] = counts.get(status, 0) + 1
            return counts

    async def results(self, run_id: str) -> list[Result]:
        async with self._db.session() as session:
            rows = await session.execute(
                select(ConversationRecord, ScoreRecord)
                .join(ScoreRecord, ScoreRecord.conversation_id == ConversationRecord.id)
                .where(ConversationRecord.run_id == run_id)
            )
            return [
                Result(
                    scenario_id=conversation.scenario_id,
                    persona_id=conversation.persona_id,
                    target_model=conversation.target_model,
                    guardrail=conversation.guardrail,
                    total=score.total,
                    measure_scores=score.measure_scores,
                )
                for conversation, score in rows
            ]

    async def scored_conversations(self, run_id: str) -> list[ScoredConversation]:
        """Full transcripts with their scores, for review and for human labelling."""
        async with self._db.session() as session:
            rows = await session.execute(
                select(ConversationRecord, ScoreRecord)
                .join(ScoreRecord, ScoreRecord.conversation_id == ConversationRecord.id)
                .where(ConversationRecord.run_id == run_id)
                .order_by(ConversationRecord.job_key)
            )
            return [
                ScoredConversation(
                    conversation_id=conversation.id,
                    scenario_id=conversation.scenario_id,
                    persona_id=conversation.persona_id,
                    target_model=conversation.target_model,
                    guardrail=conversation.guardrail,
                    transcript=[Message.model_validate(m) for m in conversation.transcript],
                    measure_scores=score.measure_scores,
                    total=score.total,
                    summary=score.summary,
                )
                for conversation, score in rows
            ]
