"""Runs one conversation between the pretend user and the target chatbot."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from mirrorguard.benchmark.simulator import PersonaSimulator
from mirrorguard.library.schemas import Persona, Scenario
from mirrorguard.llm import ChatModel, Message

DEFAULT_TARGET_PROMPT = "You are a helpful assistant."


class _State(TypedDict):
    transcript: list[Message]
    turn: int


class ConversationEngine:
    """A two-step loop: the persona speaks, the target replies, until the turns run out."""

    def __init__(
        self,
        simulator: PersonaSimulator,
        *,
        target_system_prompt: str | None = DEFAULT_TARGET_PROMPT,
        target_temperature: float = 0.7,
        target_max_tokens: int = 600,
    ):
        self._simulator = simulator
        self._target_system_prompt = target_system_prompt
        self._target_temperature = target_temperature
        self._target_max_tokens = target_max_tokens

    def _build(self, persona: Persona, scenario: Scenario, target: ChatModel, turns: int):
        async def user_turn(state: _State) -> dict:
            text = await self._simulator.next_message(
                persona, scenario, state["transcript"], state["turn"], turns
            )
            return {"transcript": [*state["transcript"], Message(role="user", content=text)]}

        async def assistant_turn(state: _State) -> dict:
            messages = list(state["transcript"])
            if self._target_system_prompt:
                messages.insert(0, Message(role="system", content=self._target_system_prompt))
            text = await target.complete(
                messages,
                temperature=self._target_temperature,
                max_tokens=self._target_max_tokens,
            )
            return {
                "transcript": [*state["transcript"], Message(role="assistant", content=text)],
                "turn": state["turn"] + 1,
            }

        graph = StateGraph(_State)
        graph.add_node("user_turn", user_turn)
        graph.add_node("assistant_turn", assistant_turn)
        graph.add_edge(START, "user_turn")
        graph.add_edge("user_turn", "assistant_turn")
        graph.add_conditional_edges(
            "assistant_turn", lambda state: "user_turn" if state["turn"] < turns else END
        )
        return graph.compile()

    async def run(
        self,
        persona: Persona,
        scenario: Scenario,
        target: ChatModel,
        *,
        turns: int | None = None,
    ) -> list[Message]:
        total = turns or scenario.turns
        if total < 1:
            raise ValueError("a conversation needs at least one turn")
        graph = self._build(persona, scenario, target, total)
        final = await graph.ainvoke(
            {"transcript": [], "turn": 0}, config={"recursion_limit": total * 2 + 10}
        )
        return final["transcript"]
