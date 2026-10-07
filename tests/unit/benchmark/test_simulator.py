"""The persona simulator."""

import pytest

from mirrorguard.benchmark.simulator import PersonaSimulator, stage_of
from mirrorguard.llm.fake import FakeModel
from tests.support.benchmark import MANIA, pair, transcript_of
from tests.support.fakes import echo_model


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


async def test_hinglish_scenarios_tell_the_persona_to_write_hinglish(library):
    persona, scenario = pair(library, "hi_mania_quit_job_invest_savings")
    prompt = PersonaSimulator(echo_model("p")).system_prompt(persona, scenario, 3, 6)
    assert "Write in Hinglish" in prompt and "Haan ya na" in prompt
