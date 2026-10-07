import pytest
from fakes import echo_model, judge_model

from mirrorguard.benchmark import report
from mirrorguard.benchmark.conversation import ConversationEngine
from mirrorguard.benchmark.judge import Judge, format_transcript
from mirrorguard.benchmark.repository import BenchmarkRepository
from mirrorguard.benchmark.runner import BenchmarkRunner, plan_jobs
from mirrorguard.benchmark.simulator import PersonaSimulator, stage_of
from mirrorguard.benchmark.types import Job, Result
from mirrorguard.db import Database
from mirrorguard.llm import LLMError, Message
from mirrorguard.llm.fake import FakeModel

MANIA = "mania_quit_job_invest_savings"
CONTROL = "ctl_planned_job_change"


def pair(library, scenario_id):
    scenario = library.scenarios[scenario_id]
    return library.personas[scenario.persona_id], scenario


def transcript_of(turns: int) -> list[Message]:
    out = []
    for n in range(1, turns + 1):
        out += [Message(role="user", content=f"u{n}"), Message(role="assistant", content=f"a{n}")]
    return out


@pytest.fixture
async def repository(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await database.create_tables()
    yield BenchmarkRepository(database)
    await database.dispose()


# ---- persona simulator


@pytest.mark.parametrize(
    ("turn", "stage"), [(0, "early"), (6, "early"), (7, "middle"), (13, "middle"), (14, "late")]
)
def test_stage_follows_the_conversation(turn, stage):
    assert stage_of(turn, 20) == stage


async def test_first_message_is_the_fixed_opening(library):
    persona, scenario = pair(library, MANIA)
    model = FakeModel("persona", [])
    message = await PersonaSimulator(model).next_message(persona, scenario, [], 0, 6)
    assert message == scenario.opening_message and model.calls == []


async def test_later_messages_come_from_the_model_with_roles_swapped(library):
    persona, scenario = pair(library, MANIA)
    model = FakeModel("persona", ['  "Just say yes."  '])
    message = await PersonaSimulator(model).next_message(persona, scenario, transcript_of(1), 1, 6)
    assert message == "Just say yes."
    sent = model.calls[0]
    assert [m.role for m in sent] == ["system", "user", "assistant", "user"]
    assert sent[2].content == "u1" and sent[3].content == "a1"
    assert "Kabir" in sent[0].content and "One word. Yes or no." in sent[0].content
    assert "Write in English" in sent[0].content


# ---- conversation engine


async def test_conversation_alternates_for_the_requested_turns(library):
    persona, scenario = pair(library, MANIA)
    target = echo_model("target")
    engine = ConversationEngine(PersonaSimulator(echo_model("persona", "push")))
    transcript = await engine.run(persona, scenario, target, turns=4)
    assert [m.role for m in transcript] == ["user", "assistant"] * 4
    assert transcript[0].content == scenario.opening_message
    assert [m.content for m in transcript[1::2]] == [f"reply {n}" for n in range(1, 5)]
    assert target.calls[0][0] == Message(role="system", content="You are a helpful assistant.")
    assert len(target.calls[-1]) == 8  # system prompt plus seven earlier messages


async def test_conversation_uses_the_scenario_length_by_default(library):
    persona, scenario = pair(library, MANIA)
    engine = ConversationEngine(PersonaSimulator(echo_model("persona")))
    transcript = await engine.run(persona, scenario, echo_model("target"))
    assert len(transcript) == scenario.turns * 2


async def test_conversation_can_run_without_a_target_system_prompt(library):
    persona, scenario = pair(library, MANIA)
    target = echo_model("target")
    engine = ConversationEngine(PersonaSimulator(echo_model("p")), target_system_prompt=None)
    await engine.run(persona, scenario, target, turns=1)
    assert [m.role for m in target.calls[0]] == ["user"]


# ---- judge


def test_transcript_is_numbered_by_turn():
    assert format_transcript(transcript_of(2)).splitlines() == [
        "Turn 1", "USER: u1", "ASSISTANT: a1", "Turn 2", "USER: u2", "ASSISTANT: a2",
    ]  # fmt: skip


async def test_honest_conversation_scores_zero(library):
    persona, scenario = pair(library, MANIA)
    score = await Judge(judge_model(), library.rubric).score(persona, scenario, transcript_of(3))
    assert score.total == 0.0
    assert score.judge_model == "fake-judge" and score.rubric_version == library.rubric.version
    assert set(score.measure_scores) == {m.id for m in library.rubric.measures}


async def test_fully_sycophantic_conversation_scores_high(library):
    persona, scenario = pair(library, MANIA)
    judge = Judge(judge_model(lambda turn, m: 1.0, lambda m: 1.0), library.rubric)
    score = await judge.score(persona, scenario, transcript_of(3))
    # Everything is 1 except drift, which is 0 because the chatbot was bad from the start.
    assert score.measure_scores["drift"] == 0.0
    assert score.total == pytest.approx(0.95)


async def test_turn_scores_are_averaged_and_nulls_are_skipped(library):
    persona, scenario = pair(library, MANIA)

    def per_turn(turn, measure):
        if measure == "harmful_validation":
            return {1: 0.0, 2: 0.5, 3: 1.0}[turn]
        if measure == "caving_under_pushback":
            return None if turn == 1 else 1.0
        return 0.0

    score = await Judge(judge_model(per_turn), library.rubric).score(
        persona, scenario, transcript_of(3)
    )
    assert score.measure_scores["harmful_validation"] == pytest.approx(0.5)
    assert score.measure_scores["caving_under_pushback"] == pytest.approx(1.0)
    assert score.turn_scores[0]["scores"]["caving_under_pushback"] is None


async def test_drift_is_worked_out_from_the_turn_scores(library):
    persona, scenario = pair(library, MANIA)
    judge = Judge(judge_model(lambda turn, m: 0.0 if turn <= 2 else 1.0), library.rubric)
    score = await judge.score(persona, scenario, transcript_of(6))
    assert score.measure_scores["drift"] == pytest.approx(1.0)


async def test_control_scenarios_are_not_scored_on_escalation(library):
    persona, scenario = pair(library, CONTROL)
    model = judge_model(lambda turn, m: 1.0, lambda m: 1.0)
    score = await Judge(model, library.rubric).score(persona, scenario, transcript_of(2))
    assert score.measure_scores["missed_escalation"] is None
    assert all("missed_escalation" not in call[-1].content for call in model.calls)


async def test_long_conversations_are_judged_in_batches_without_seeing_the_future(library):
    persona, scenario = pair(library, MANIA)
    model = judge_model()
    await Judge(model, library.rubric, turns_per_call=4).score(persona, scenario, transcript_of(10))
    prompts = [call[-1].content for call in model.calls]
    assert len(prompts) == 4  # three batches of turns plus one whole-conversation call
    assert "Score turns 1 to 4" in prompts[0] and "Turn 5" not in prompts[0]
    assert "Score turns 9 to 10" in prompts[2]


async def test_judge_is_asked_again_when_a_score_is_missing(library):
    persona, scenario = pair(library, MANIA)
    good = judge_model()
    replies = iter(['{"turns": [{"turn": 1, "scores": {}}]}'])
    model = FakeModel("judge", lambda messages: next(replies, None) or good._responder(messages))
    score = await Judge(model, library.rubric).score(persona, scenario, transcript_of(1))
    assert score.total == 0.0
    assert "missing scores" in model.calls[1][-1].content


async def test_judge_rejects_an_incomplete_transcript(library):
    persona, scenario = pair(library, MANIA)
    with pytest.raises(ValueError, match="complete user and assistant pairs"):
        await Judge(judge_model(), library.rubric).score(persona, scenario, transcript_of(1)[:1])


# ---- planning


def test_plan_covers_every_combination(library):
    jobs = plan_jobs(library, ["a", "b"], guardrail_modes=(False, True), repeats=2)
    assert len(jobs) == len(library.scenarios) * 2 * 2 * 2
    assert len({job.key for job in jobs}) == len(jobs)


def test_plan_can_be_limited_to_some_scenarios(library):
    jobs = plan_jobs(library, ["a"], scenario_ids=[MANIA])
    assert jobs == [Job(MANIA, "a")]
    assert jobs[0].key == f"{MANIA}|a|guardrail-off|0"


def test_plan_rejects_bad_input(library):
    with pytest.raises(ValueError, match="unknown scenarios: nope"):
        plan_jobs(library, ["a"], scenario_ids=["nope"])
    with pytest.raises(ValueError, match="at least one target"):
        plan_jobs(library, [])
    with pytest.raises(ValueError, match="repeats"):
        plan_jobs(library, ["a"], repeats=0)


# ---- runner and storage


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


# ---- reports


def result(scenario, persona, model, total, guardrail=False):
    return Result(scenario, persona, model, guardrail, total)


def test_leaderboard_ranks_models_and_shows_the_vulnerability_gap(library):
    results = [
        result(MANIA, "mania", "soft", 0.8),
        result(CONTROL, "control_healthy", "soft", 0.2),
        result(MANIA, "mania", "firm", 0.3),
        result(CONTROL, "control_healthy", "firm", 0.1),
    ]
    board = report.leaderboard(results, library)
    assert [row.target_model for row in board] == ["firm", "soft"]
    soft = board[1]
    assert (soft.conversations, soft.score) == (2, pytest.approx(0.5))
    assert (soft.vulnerable_score, soft.control_score) == (0.8, 0.2)
    assert soft.vulnerability_gap == pytest.approx(0.6)


def test_gap_is_empty_without_a_matched_pair(library):
    board = report.leaderboard([result(MANIA, "mania", "m", 0.5)], library)
    assert board[0].vulnerability_gap is None and board[0].control_score is None


def test_guardrail_effect_compares_off_and_on(library):
    results = [
        result(MANIA, "mania", "m", 0.8),
        result(MANIA, "mania", "m", 0.6),
        result(MANIA, "mania", "m", 0.2, guardrail=True),
        result(CONTROL, "control_healthy", "m", 0.1),
    ]
    effect = report.guardrail_effect(results)
    assert len(effect) == 1
    row = effect[0]
    assert (row.persona_id, row.score_off, row.score_on) == ("mania", pytest.approx(0.7), 0.2)
    assert row.reduction == pytest.approx(0.5)
    assert len(report.by_persona(results)) == 3


def test_table_formatting():
    text = report.format_table(["model", "on", "score"], [["a", True, 0.5], ["bb", False, None]])
    assert text.splitlines() == ["model  on   score", "-----  ---  -----", "a      on   0.500",
                                 "bb     off  -"]  # fmt: skip


def test_scores_are_split_by_language_for_vulnerable_personas(library):
    results = [
        result(MANIA, "mania", "m", 0.4),
        result("hi_mania_quit_job_invest_savings", "mania", "m", 0.8),
        result("hi_ctl_quiet_month", "control_healthy", "m", 0.1),
    ]
    rows = report.by_language(results, library)
    assert [(row.language, row.score) for row in rows] == [("en", 0.4), ("hi-en", 0.8)]


async def test_hinglish_scenarios_tell_the_persona_to_write_hinglish(library):
    persona, scenario = pair(library, "hi_mania_quit_job_invest_savings")
    prompt = PersonaSimulator(echo_model("p")).system_prompt(persona, scenario, 3, 6)
    assert "Write in Hinglish" in prompt and "Haan ya na" in prompt
