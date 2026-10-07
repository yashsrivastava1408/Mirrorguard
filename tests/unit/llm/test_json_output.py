"""Asking a model for JSON and checking the answer."""

import pytest
from pydantic import BaseModel

from mirrorguard.llm import LLMOutputError, Message, complete_json
from mirrorguard.llm.fake import FakeModel
from mirrorguard.llm.json_output import extract_json

HELLO = [Message(role="user", content="hello")]


class Answer(BaseModel):
    value: int


def test_extract_json_handles_fences_and_chatter():
    assert extract_json('```json\n{"value": 1}\n```') == '{"value": 1}'
    assert extract_json('Sure! Here it is: {"value": 2} Hope that helps.') == '{"value": 2}'
    with pytest.raises(ValueError):
        extract_json("no json here")


async def test_complete_json_parses_a_good_answer():
    model = FakeModel("m", ['{"value": 7}'])
    assert (await complete_json(model, HELLO, Answer)).value == 7


async def test_complete_json_asks_again_after_a_bad_answer():
    model = FakeModel("m", ["not json", '{"value": 3}'])
    assert (await complete_json(model, HELLO, Answer)).value == 3
    assert "could not be used" in model.calls[1][-1].content


async def test_complete_json_runs_the_extra_check():
    def must_be_positive(answer: Answer) -> None:
        if answer.value <= 0:
            raise ValueError("value must be positive")

    model = FakeModel("m", ['{"value": -1}', '{"value": 5}'])
    assert (await complete_json(model, HELLO, Answer, check=must_be_positive)).value == 5
    assert "value must be positive" in model.calls[1][-1].content


async def test_complete_json_gives_up_after_the_allowed_attempts():
    model = FakeModel("m", ["bad", "bad", "bad"])
    with pytest.raises(LLMOutputError, match="after 3 tries"):
        await complete_json(model, HELLO, Answer)
    assert len(model.calls) == 3
