"""Shortcuts for benchmark tests."""

from mirrorguard.llm import Message

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
