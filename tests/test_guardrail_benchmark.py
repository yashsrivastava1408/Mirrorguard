"""The benchmark run with the guardrail in front of the target (Phase 5)."""

from fakes import echo_model, judge_model
from test_guardrail import KeywordScorer

from mirrorguard.benchmark import report
from mirrorguard.benchmark.conversation import ConversationEngine
from mirrorguard.benchmark.judge import Judge
from mirrorguard.benchmark.repository import BenchmarkRepository
from mirrorguard.benchmark.runner import BenchmarkRunner, plan_jobs
from mirrorguard.benchmark.simulator import PersonaSimulator
from mirrorguard.db import Database
from mirrorguard.guardrail.benchmark_target import GuardedChatModel
from mirrorguard.guardrail.pipeline import Guardrail
from mirrorguard.llm import Message
from mirrorguard.llm.fake import FakeModel

MANIA = "mania_quit_job_invest_savings"
CONTROL = "ctl_planned_job_change"


def agreeable_unless_steered(messages):
    """Over-agrees by default, and is honest when the steering guidance is present."""
    steered = messages[0].role == "system" and "Do not simply agree" in messages[0].content
    return "I do not think that is safe yet." if steered else "Yes! Go for it."


async def test_guarded_model_records_what_the_guardrail_did():
    guardrail = Guardrail(scorer=KeywordScorer())
    model = GuardedChatModel(FakeModel("up", agreeable_unless_steered), guardrail, "s1")
    assert model.name == "up"
    first = await model.complete([Message(role="user", content="hello")])
    second = await model.complete([Message(role="user", content="I have not slept")])
    assert (first, second) == ("Yes! Go for it.", "I do not think that is safe yet.")
    assert [(t["turn"], t["action"]) for t in model.trace] == [(1, "pass"), (2, "steer")]
    assert model.trace[1]["signals"] == ["no sleep"]
    assert [p async for p in model.stream([Message(role="user", content="ok")])]


async def test_benchmark_shows_the_guardrail_lowering_the_score(library, tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'bench.db'}")
    await database.create_tables()
    repository = BenchmarkRepository(database)
    guardrail = Guardrail(scorer=KeywordScorer())

    def target_for(job):
        upstream = FakeModel(job.target_model, agreeable_unless_steered)
        return GuardedChatModel(upstream, guardrail, job.key) if job.guardrail else upstream

    # A judge that marks any reply containing "Yes!" as fully sycophantic.
    def judge_responder():
        import json
        import re

        def respond(messages):
            head, tail = messages[1].content.rsplit("Reply with only this JSON", 1)
            keys = re.findall(r'"([a-z_]+)": 0', tail)
            replies = re.findall(r"ASSISTANT: (.*)", head)
            batch = re.search(r"Score turns (\d+) to (\d+)", head)
            if batch:
                first, last = int(batch.group(1)), int(batch.group(2))
                turns = [
                    {"turn": n, "scores": {k: float("Yes!" in replies[n - 1]) for k in keys}}
                    for n in range(first, last + 1)
                ]
                return json.dumps({"turns": turns})
            share = sum("Yes!" in r for r in replies) / len(replies)
            return json.dumps({"scores": {k: round(share) for k in keys}, "summary": ""})

        return FakeModel("judge", respond)

    jobs = plan_jobs(library, ["bot"], scenario_ids=[MANIA, CONTROL], guardrail_modes=(False, True))
    run_id = await repository.create_run("guardrail test", {}, jobs, library)
    runner = BenchmarkRunner(
        library=library,
        repository=repository,
        engine=ConversationEngine(PersonaSimulator(echo_model("persona", "say yes"))),
        judge=Judge(judge_responder(), library.rubric),
        target_factory=target_for,
        turns=3,
    )
    summary = await runner.run(run_id)
    assert (summary.done, summary.failed) == (4, 0)

    results = await repository.results(run_id)
    effect = {row.persona_id: row for row in report.guardrail_effect(results)}
    # The mania opening message mentions no sleep, so the guardrail steers every turn.
    assert effect["mania"].score_off > 0.9
    assert effect["mania"].score_on == 0.0
    assert effect["mania"].reduction > 0.9
    # The calm control user is never steered, so the guardrail changes nothing there.
    assert effect["control_healthy"].reduction == 0.0

    saved = await repository.scored_conversations(run_id)
    assert {c.guardrail for c in saved} == {False, True}
    pending = await repository.unfinished_jobs(run_id)
    assert pending == []
    await database.dispose()


async def test_guardrail_trace_is_saved_with_the_conversation(library, tmp_path):
    from sqlalchemy import select

    from mirrorguard.db.models import ConversationRecord

    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'trace.db'}")
    await database.create_tables()
    repository = BenchmarkRepository(database)
    guardrail = Guardrail(scorer=KeywordScorer())
    jobs = plan_jobs(library, ["bot"], scenario_ids=[MANIA], guardrail_modes=(True,))
    run_id = await repository.create_run("trace", {}, jobs, library)
    runner = BenchmarkRunner(
        library=library,
        repository=repository,
        engine=ConversationEngine(PersonaSimulator(echo_model("persona"))),
        judge=Judge(judge_model(), library.rubric),
        target_factory=lambda job: GuardedChatModel(echo_model("bot"), guardrail, job.key),
        turns=2,
    )
    await runner.run(run_id)
    async with database.session() as session:
        record = (await session.scalars(select(ConversationRecord))).one()
    assert [t["action"] for t in record.guardrail_trace] == ["steer", "steer"]
    await database.dispose()
