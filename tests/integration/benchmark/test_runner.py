"""The benchmark runner with a real database."""

from mirrorguard.benchmark.conversation import ConversationEngine
from mirrorguard.benchmark.judge import Judge
from mirrorguard.benchmark.runner import BenchmarkRunner, plan_jobs
from mirrorguard.benchmark.simulator import PersonaSimulator
from mirrorguard.llm import LLMError
from mirrorguard.llm.fake import FakeModel
from tests.support.benchmark import CONTROL, MANIA
from tests.support.fakes import echo_model, judge_model


def make_runner(library, repository, target_factory, judge=None, **options):
    return BenchmarkRunner(
        library=library,
        repository=repository,
        engine=ConversationEngine(PersonaSimulator(echo_model("persona"))),
        judge=Judge(judge or judge_model(), library.rubric),
        target_factory=target_factory,
        turns=2,
        **options,
    )


async def test_run_scores_every_job_and_saves_it(library, repository):
    jobs = plan_jobs(library, ["m1", "m2"], scenario_ids=[MANIA, CONTROL])
    run_id = await repository.create_run("test", {"turns": 2}, jobs, library)
    progress = []
    runner = make_runner(
        library,
        repository,
        lambda job: echo_model(job.target_model),
        on_progress=lambda job, status: progress.append(status),
    )
    summary = await runner.run(run_id)
    assert (summary.done, summary.failed) == (4, 0)
    assert progress == ["done"] * 4
    assert await repository.status_counts(run_id) == {"done": 4}
    assert (await repository.get_run(run_id)).status == "finished"
    results = await repository.results(run_id)
    assert {(r.scenario_id, r.target_model) for r in results} == {
        (s, m) for s in (MANIA, CONTROL) for m in ("m1", "m2")
    }
    assert {r.persona_id for r in results} == {"mania", "control_healthy"}


async def test_a_failing_job_is_recorded_and_the_rest_carry_on(library, repository):
    def target_for(job):
        if job.target_model == "broken":
            return FakeModel("broken", lambda messages: (_ for _ in ()).throw(LLMError("down")))
        return echo_model(job.target_model)

    jobs = plan_jobs(library, ["good", "broken"], scenario_ids=[MANIA])
    run_id = await repository.create_run("test", {}, jobs, library)
    summary = await make_runner(library, repository, target_for).run(run_id)
    assert (summary.done, summary.failed) == (1, 1)
    assert await repository.status_counts(run_id) == {"done": 1, "failed": 1}
    assert (await repository.get_run(run_id)).status == "incomplete"


async def test_resume_retries_only_what_is_left(library, repository):
    state = {"broken": True}
    calls = []

    def target_for(job):
        calls.append(job.target_model)
        if job.target_model == "flaky" and state["broken"]:
            return FakeModel("flaky", lambda messages: (_ for _ in ()).throw(LLMError("down")))
        return echo_model(job.target_model)

    jobs = plan_jobs(library, ["good", "flaky"], scenario_ids=[MANIA])
    run_id = await repository.create_run("test", {}, jobs, library)
    runner = make_runner(library, repository, target_for)
    await runner.run(run_id)
    state["broken"] = False
    calls.clear()
    summary = await runner.run(run_id)
    assert (summary.done, summary.failed) == (1, 0)
    assert calls == ["flaky"]
    assert await repository.status_counts(run_id) == {"done": 2}


async def test_a_saved_conversation_is_only_judged_again_not_replayed(library, repository):
    jobs = plan_jobs(library, ["m"], scenario_ids=[MANIA])
    run_id = await repository.create_run("test", {}, jobs, library)
    broken_judge = FakeModel("judge", lambda messages: (_ for _ in ()).throw(LLMError("down")))
    target_calls = []

    def target_for(job):
        target_calls.append(job.key)
        return echo_model("m")

    await make_runner(library, repository, target_for, judge=broken_judge).run(run_id)
    assert await repository.status_counts(run_id) == {"failed": 1}
    pending = await repository.unfinished_jobs(run_id)
    assert pending[0].transcript is not None and len(pending[0].transcript) == 4

    summary = await make_runner(library, repository, target_for).run(run_id)
    assert summary.done == 1 and len(target_calls) == 1


async def test_runs_are_listed_newest_first(library, repository):
    first = await repository.create_run("first", {}, [], library)
    second = await repository.create_run("second", {}, [], library)
    assert [run.id for run in await repository.list_runs()] == [second, first]
    assert await repository.get_run("missing") is None
