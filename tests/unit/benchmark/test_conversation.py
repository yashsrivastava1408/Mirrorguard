"""The conversation engine."""

from mirrorguard.benchmark.conversation import ConversationEngine
from mirrorguard.benchmark.simulator import PersonaSimulator
from mirrorguard.llm import Message
from tests.support.benchmark import MANIA, pair
from tests.support.fakes import echo_model


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
