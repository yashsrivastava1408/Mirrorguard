"""Checks a held reply and rewrites it when it is sycophantic. Used at high risk only."""

from collections.abc import Sequence
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from mirrorguard.llm import ChatModel, LLMError, Message, complete_json

_CHECK_SYSTEM = """\
You review a reply that an AI assistant is about to send to a user who may be at \
serious risk. Decide whether the reply is safe to send.

The reply fails if it does any of these:
- Agrees with, or builds on, a belief or plan that is false, risky or hard to undo.
- Gives in after the user pushed back on an honest point.
- Flatters the user or praises a risky plan.
- Gives no honest reality check where one is clearly needed.
- Presents the assistant as a replacement for people in the user's life or for professional help.
- Fails to encourage reaching a trusted person or a professional when the risk is clear.
- Is cold, lecturing or dismissive. A good reply is honest and kind together.

Reply with only this JSON:
{"ok": true, "issues": ["one short phrase for each problem, empty when ok"]}"""

_REWRITE_SYSTEM = """\
You rewrite a reply from an AI assistant to a user who may be at serious risk.
Write the reply the assistant should have given.
- Be warm and respectful, and be honest.
- Do not agree with a belief or plan that is false, risky or hard to undo.
- Give one gentle, clear reality check.
- Do not flatter and do not lecture.
- Encourage the user to reach a trusted person, a doctor or a counsellor.
- Do not diagnose the user or name a condition.
- Keep about the same length and language as the original reply.
Write only the new reply, with nothing before or after it."""


class _Verdict(BaseModel):
    ok: bool
    issues: list[str] = Field(default_factory=list)


class _State(TypedDict, total=False):
    reply: str
    issues: list[str]
    first_issues: list[str]
    rewrites: int


def _conversation(messages: Sequence[Message], window: int) -> str:
    recent = [m for m in messages if m.role != "system"][-window:]
    return "\n".join(f"{m.role.upper()}: {m.content}" for m in recent)


class LLMReplyGuard:
    """A check-and-rewrite loop.

    If the checker itself fails, the original reply is sent: it was already written
    under the stronger steering, and a broken checker must not block the user.
    """

    def __init__(self, checker: ChatModel, rewriter: ChatModel, *, window: int = 8):
        self._checker = checker
        self._rewriter = rewriter
        self._window = window

    async def _check(self, conversation: str, reply: str) -> _Verdict:
        return await complete_json(
            self._checker,
            [
                Message(role="system", content=_CHECK_SYSTEM),
                Message(
                    role="user",
                    content=f"Conversation\n{conversation}\n\nReply to review\n{reply}",
                ),
            ],
            _Verdict,
            attempts=2,
            max_tokens=300,
        )

    async def _rewrite(self, conversation: str, reply: str, issues: Sequence[str]) -> str:
        problems = "\n".join(f"- {issue}" for issue in issues)
        text = await self._rewriter.complete(
            [
                Message(role="system", content=_REWRITE_SYSTEM),
                Message(
                    role="user",
                    content=(
                        f"Conversation\n{conversation}\n\nOriginal reply\n{reply}\n\n"
                        f"Problems with the original reply\n{problems}"
                    ),
                ),
            ],
            temperature=0.3,
            max_tokens=700,
        )
        return text.strip()

    async def review(
        self, messages: Sequence[Message], reply: str, *, max_rewrites: int
    ) -> tuple[str, tuple[str, ...]]:
        conversation = _conversation(messages, self._window)

        async def check(state: _State) -> dict:
            verdict = await self._check(conversation, state["reply"])
            issues = [] if verdict.ok else (verdict.issues or ["failed the safety check"])
            update: dict = {"issues": issues}
            if "first_issues" not in state:
                update["first_issues"] = issues
            return update

        async def rewrite(state: _State) -> dict:
            new_reply = await self._rewrite(conversation, state["reply"], state["issues"])
            return {"reply": new_reply or state["reply"], "rewrites": state["rewrites"] + 1}

        def after_check(state: _State) -> str:
            return "rewrite" if state["issues"] and state["rewrites"] < max_rewrites else END

        graph = StateGraph(_State)
        graph.add_node("check", check)
        graph.add_node("rewrite", rewrite)
        graph.add_edge(START, "check")
        graph.add_conditional_edges("check", after_check)
        graph.add_edge("rewrite", "check")
        try:
            final = await graph.compile().ainvoke({"reply": reply, "rewrites": 0})
        except LLMError:
            return reply, ()
        return final["reply"], tuple(final["first_issues"])
