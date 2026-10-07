"""The real model client, against a local stand-in for an OpenAI-style server."""

import json
import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from mirrorguard.llm import LLMError, Message, RetryableLLMError
from mirrorguard.llm.litellm_model import LiteLLMModel

HELLO = [Message(role="user", content="hello")]


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
