"""The endpoints behind the dashboard."""

import pytest

from mirrorguard.benchmark.conversation import ConversationEngine
from mirrorguard.benchmark.judge import Judge
from mirrorguard.benchmark.runner import BenchmarkRunner, plan_jobs
from mirrorguard.benchmark.simulator import PersonaSimulator
from mirrorguard.db import Database
from mirrorguard.guardrail.policy import Policy
from mirrorguard.guardrail.stores.policy_store import DatabasePolicyStore
from tests.support.api import AUTH, OTHER, chat
from tests.support.fakes import echo_model, judge_model


async def send(harness, text, session="s1", headers=AUTH):
    await harness.client.post(
        "/v1/chat/completions", json=chat(text), headers={**headers, "X-Session-Id": session}
    )
    await harness.services.sink.flush()


async def test_stats_count_turns_levels_and_actions(harness):
    await send(harness, "hello")
    await send(harness, "I have not slept")
    await send(harness, "I want to end it all", session="s2")
    await send(harness, "scorer-down", session="s3")
    await send(harness, "someone else's traffic", headers=OTHER)
    body = (await harness.client.get("/v1/stats", headers=AUTH)).json()
    assert (body["hours"], body["turns"], body["sessions"]) == (24, 4, 3)
    assert body["by_level"] == {"low": 1, "medium": 2, "high": 1}
    assert body["by_action"] == {"pass": 1, "steer": 2, "check": 1}
    assert (body["crisis"], body["scorer_fallbacks"], body["rewritten"]) == (1, 1, 0)
    assert len(body["timeline"]) == 1
    assert {k: body["timeline"][0][k] for k in ("low", "medium", "high")} == body["by_level"]


async def test_stats_are_empty_for_a_new_tenant_and_reject_bad_ranges(harness):
    body = (await harness.client.get("/v1/stats", headers=AUTH)).json()
    assert body["turns"] == 0 and body["timeline"] == []
    assert body["by_level"] == {"low": 0, "medium": 0, "high": 0}
    assert (await harness.client.get("/v1/stats?hours=0", headers=AUTH)).status_code == 400
    assert (await harness.client.get("/v1/stats")).status_code == 401


async def test_events_are_listed_newest_first_with_filters_and_pages(harness):
    for text in ("hello", "I have not slept", "fine", "I have not slept again"):
        await send(harness, text, session=text)
    get = harness.client.get
    everything = (await get("/v1/events", headers=AUTH)).json()
    assert [e["user_message"] for e in everything["events"]][0] == "I have not slept again"
    assert len(everything["events"]) == 4 and everything["next_before"] is None

    medium = (await get("/v1/events?risk_level=medium", headers=AUTH)).json()["events"]
    assert {e["user_message"] for e in medium} == {"I have not slept", "I have not slept again"}
    assert medium[0]["signals"] == ["no sleep"] and medium[0]["review"] is None

    page = (await get("/v1/events?limit=3", headers=AUTH)).json()
    assert len(page["events"]) == 3 and page["next_before"]
    rest = await get("/v1/events", params={"before": page["next_before"]}, headers=AUTH)
    assert [e["user_message"] for e in rest.json()["events"]] == ["hello"]

    assert (await get("/v1/events", headers=OTHER)).json()["events"] == []


async def test_review_queue_and_verdicts(harness):
    await send(harness, "hello")
    await send(harness, "I have not slept", session="risky")
    get, post = harness.client.get, harness.client.post
    queue = (await get("/v1/events?unreviewed=true", headers=AUTH)).json()["events"]
    assert [e["user_message"] for e in queue] == ["I have not slept"]
    event_id = queue[0]["id"]

    wrong_tenant = await post(
        f"/v1/events/{event_id}/review", json={"verdict": "correct"}, headers=OTHER
    )
    assert wrong_tenant.status_code == 404
    bad = await post(f"/v1/events/{event_id}/review", json={"verdict": "maybe"}, headers=AUTH)
    assert bad.status_code == 400

    saved = await post(
        f"/v1/events/{event_id}/review",
        json={"verdict": "incorrect", "note": "user was joking", "reviewer": "asha"},
        headers=AUTH,
    )
    assert saved.json() == {"status": "saved"}
    assert (await get("/v1/events?unreviewed=true", headers=AUTH)).json()["events"] == []
    listed = (await get("/v1/events?risk_level=medium", headers=AUTH)).json()["events"][0]
    assert listed["review"] == {
        "verdict": "incorrect", "note": "user was joking", "reviewer": "asha",
    }  # fmt: skip

    # A second verdict replaces the first.
    await post(f"/v1/events/{event_id}/review", json={"verdict": "correct"}, headers=AUTH)
    stats = (await get("/v1/stats", headers=AUTH)).json()
    assert stats["reviews"] == {"correct": 1}


async def test_policy_can_be_read_and_changed_per_tenant(harness):
    get, put = harness.client.get, harness.client.put
    default = (await get("/v1/policy", headers=AUTH)).json()
    assert default["medium_action"] == "steer" and default["shadow_mode"] is False

    changed = {**default, "shadow_mode": True, "session_window": 3}
    assert (await put("/v1/policy", json=changed, headers=AUTH)).status_code == 200
    assert (await get("/v1/policy", headers=AUTH)).json()["shadow_mode"] is True
    assert (await get("/v1/policy", headers=OTHER)).json()["shadow_mode"] is False

    # The change takes effect on the next chat turn.
    response = await harness.client.post(
        "/v1/chat/completions", json=chat("I have not slept"), headers=AUTH
    )
    assert response.json()["mirrorguard"]["shadow"] is True
    assert harness.upstream.calls[-1][0].role == "user"  # nothing was added to the prompt


@pytest.mark.parametrize(
    "change", [{"medium_action": "ignore"}, {"session_window": 0}, {"surprise": 1}]
)
async def test_invalid_policy_is_refused(harness, change):
    default = (await harness.client.get("/v1/policy", headers=AUTH)).json()
    response = await harness.client.put("/v1/policy", json={**default, **change}, headers=AUTH)
    assert response.status_code == 400


async def test_policy_store_caches_reads_for_a_short_time(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'p.db'}")
    await database.create_tables()
    now = [0.0]
    writer = DatabasePolicyStore(database, ttl_seconds=0)
    reader = DatabasePolicyStore(database, ttl_seconds=15, clock=lambda: now[0])
    assert (await reader.get("t")).shadow_mode is False
    await writer.set("t", Policy(shadow_mode=True))  # another server copy changes the policy
    assert (await reader.get("t")).shadow_mode is False  # still cached
    now[0] = 16.0
    assert (await reader.get("t")).shadow_mode is True
    await reader.set("t", Policy(session_window=9))  # a local change is seen at once
    assert (await reader.get("t")).session_window == 9
    await database.dispose()


async def test_benchmark_results_are_served(harness):
    services = harness.services
    library = services.library
    jobs = plan_jobs(
        library, ["bot"], scenario_ids=["mania_quit_job_invest_savings", "ctl_planned_job_change"]
    )
    run_id = await services.benchmarks.create_run("demo", {"turns": 2}, jobs, library)
    await BenchmarkRunner(
        library=library,
        repository=services.benchmarks,
        engine=ConversationEngine(PersonaSimulator(echo_model("persona"))),
        judge=Judge(judge_model(lambda turn, m: 1.0, lambda m: 1.0), library.rubric),
        target_factory=lambda job: echo_model("bot"),
        turns=2,
    ).run(run_id)

    get = harness.client.get
    runs = (await get("/v1/benchmarks", headers=AUTH)).json()["runs"]
    assert [(r["name"], r["status"], r["done"], r["total"]) for r in runs] == [
        ("demo", "finished", 2, 2)
    ]
    report = (await get(f"/v1/benchmarks/{run_id}", headers=AUTH)).json()
    assert report["leaderboard"][0]["target_model"] == "bot"
    assert report["leaderboard"][0]["conversations"] == 2
    assert {row["persona_id"] for row in report["by_persona"]} == {"mania", "control_healthy"}

    conversations = (await get(f"/v1/benchmarks/{run_id}/conversations", headers=AUTH)).json()
    first = conversations["conversations"][0]
    assert len(first["transcript"]) == 4 and first["transcript"][0]["role"] == "user"
    assert "harmful_validation" in first["measure_scores"]

    assert (await get("/v1/benchmarks/nope", headers=AUTH)).status_code == 404
    assert (await get("/v1/benchmarks")).status_code == 401


async def test_dashboard_origin_is_allowed_by_cors(harness):
    response = await harness.client.options(
        "/v1/stats",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    blocked = await harness.client.options(
        "/v1/stats",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in blocked.headers
