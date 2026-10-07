"""Planning benchmark jobs."""

import pytest

from mirrorguard.benchmark.runner import plan_jobs
from mirrorguard.benchmark.types import Job
from tests.support.benchmark import MANIA


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
