import asyncio
import json
import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from mirrorguard.llm import LLMError, LLMOutputError, Message, RetryableLLMError, complete_json
from mirrorguard.llm.fake import FakeModel
from mirrorguard.llm.json_output import extract_json
from mirrorguard.llm.litellm_model import LiteLLMModel
from mirrorguard.llm.resilient import ResilientModel, Throttle

HELLO = [Message(role="user", content="hello")]


class Answer(BaseModel):
    value: int


class FlakyModel:
    """Fails a set number of times, then answers."""

    name = "flaky"

    def __init__(self, failures: int, retry_after: float | None = None):
        self.failures = failures
        self.retry_after = retry_after
        self.attempts = 0

    async def complete(self, messages, *, temperature=0.7, max_tokens=None):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise RetryableLLMError("rate limited", retry_after=self.retry_after)
        return "fine"

    async def stream(self, messages, *, temperature=0.7, max_tokens=None):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise RetryableLLMError("rate limited")
        yield "a "
        yield "b"


class Recorder:
    def __init__(self):
        self.sleeps: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def throttle(**overrides):
    return Throttle(**{"requests_per_minute": 6000, "max_concurrency": 8, **overrides})


# ---- JSON output


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


# ---- pacing and retries


async def test_throttle_spaces_out_call_starts():
    now = [0.0]
    recorder = Recorder()
    limiter = Throttle(
        requests_per_minute=60, max_concurrency=5, clock=lambda: now[0], sleep=recorder.sleep
    )
    for _ in range(3):
        async with limiter:
            pass
    assert recorder.sleeps == [1.0, 2.0]


async def test_throttle_limits_calls_running_at_once():
    limiter = throttle(max_concurrency=2)
    running = peak = 0

    async def work():
        nonlocal running, peak
        async with limiter:
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.01)
            running -= 1

    await asyncio.gather(*(work() for _ in range(8)))
    assert peak == 2


def test_throttle_rejects_bad_limits():
    with pytest.raises(ValueError):
        Throttle(requests_per_minute=0, max_concurrency=1)


async def test_retries_until_the_call_succeeds():
    inner, recorder = FlakyModel(failures=2), Recorder()
    model = ResilientModel(inner, throttle(), max_retries=3, sleep=recorder.sleep)
    assert await model.complete(HELLO) == "fine"
    assert inner.attempts == 3 and len(recorder.sleeps) == 2
    assert recorder.sleeps[1] > recorder.sleeps[0] * 0.99  # backoff grows


async def test_gives_up_after_max_retries():
    inner = FlakyModel(failures=10)
    model = ResilientModel(inner, throttle(), max_retries=2, sleep=Recorder().sleep)
    with pytest.raises(RetryableLLMError):
        await model.complete(HELLO)
    assert inner.attempts == 3


async def test_waits_as_long_as_the_provider_asks():
    recorder = Recorder()
    model = ResilientModel(
        FlakyModel(failures=1, retry_after=7.0), throttle(), sleep=recorder.sleep
    )
    await model.complete(HELLO)
    assert recorder.sleeps == [7.0]


async def test_stream_retries_before_any_text_is_sent():
    inner = FlakyModel(failures=1)
    model = ResilientModel(inner, throttle(), sleep=Recorder().sleep)
    assert [piece async for piece in model.stream(HELLO)] == ["a ", "b"]
    assert inner.attempts == 2


# ---- the real client, against a local stand-in for an OpenAI-style server


def _stand_in_server() -> FastAPI:
    app = FastAPI()
    app.state.requests = []

    @app.post("/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        app.state.requests.append(body)
        text = body["messages"][-1]["content"]
        if text == "limit":
            return JSONResponse(
                {"error": {"message": "slow down", "type": "rate_limit"}},
                status_code=429,
                headers={"retry-after": "3"},
            )
        if text == "broken":
            return JSONResponse({"error": {"message": "bad request"}}, status_code=400)
        if body.get("stream"):

            async def events():
                for word in ["one ", "two ", "three"]:
                    chunk = {
                        "id": "c",
                        "object": "chat.completion.chunk",
                        "model": body["model"],
                        "choices": [{"index": 0, "delta": {"content": word}}],
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(events(), media_type="text/event-stream")
        return {
            "id": "c",
            "object": "chat.completion",
            "model": body["model"],
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": f"echo: {text}"},
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    return app


@pytest.fixture(scope="module")
def server():
    app = _stand_in_server()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    instance = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=instance.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not instance.started and time.time() < deadline:
        time.sleep(0.02)
    yield app, f"http://127.0.0.1:{port}"
    instance.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def real_client(server):
    app, base = server
    return LiteLLMModel("openai/stand-in", api_base=base, api_key="test-key", timeout=10), app


async def test_real_client_completes_over_http(real_client):
    model, app = real_client
    system = Message(role="system", content="be brief")
    reply = await model.complete([system, *HELLO], temperature=0.2, max_tokens=50)
    assert reply == "echo: hello"
    sent = app.state.requests[-1]
    assert sent["messages"][0] == {"role": "system", "content": "be brief"}
    assert sent["temperature"] == 0.2 and sent["max_tokens"] == 50


async def test_real_client_streams_over_http(real_client):
    model, _ = real_client
    assert "".join([piece async for piece in model.stream(HELLO)]) == "one two three"


async def test_real_client_marks_rate_limits_as_retryable(real_client):
    model, _ = real_client
    with pytest.raises(RetryableLLMError):
        await model.complete([Message(role="user", content="limit")])


async def test_real_client_marks_bad_requests_as_final(real_client):
    model, _ = real_client
    with pytest.raises(LLMError) as info:
        await model.complete([Message(role="user", content="broken")])
    assert not isinstance(info.value, RetryableLLMError)
