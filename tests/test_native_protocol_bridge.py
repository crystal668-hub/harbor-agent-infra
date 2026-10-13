from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from scripts.native_protocol_bridge import create_app


class FakeResponse(BaseModel):
    type: str = "response.completed"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "gpt-test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gpt.example/v1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude-test-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://claude.example")
    return TestClient(create_app())


@pytest.mark.parametrize(
    "route,model,key,sdk_path,base",
    [
        (
            "messages",
            "gpt-6.1-sol",
            "gpt-test-key",
            "litellm.anthropic.messages.acreate",
            "https://gpt.example/v1",
        ),
        (
            "responses",
            "claude-opus-5.5",
            "claude-test-key",
            "litellm.aresponses",
            "https://claude.example/v1",
        ),
    ],
)
def test_bridge_routes_streams_without_exposing_credentials(
    client, monkeypatch, route, model, key, sdk_path, base
):
    async def events():
        if route == "messages":
            yield b'event: message_stop\ndata: {"type":"message_stop"}\n\n'
        else:
            yield FakeResponse()

    handler = AsyncMock(return_value=events())
    monkeypatch.setattr(sdk_path, handler)
    response = client.post(
        f"/v1/{route}",
        headers={"x-api-key": key},
        json={
            "model": model,
            "stream": True,
            "input": "fixture",
            **(
                {"reasoning": {"effort": "high", "summary": "auto"}} if route == "responses" else {}
            ),
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "message_stop" in response.text or "response.completed" in response.text
    assert key not in response.text
    kwargs = handler.await_args.kwargs
    assert kwargs["model"] == f"openai/{model}"
    assert kwargs["api_key"] == key and kwargs["api_base"] == base
    assert kwargs.get("use_chat_completions_api") is (True if route == "responses" else None)
    if route == "responses":
        assert kwargs["reasoning"] == {"effort": "high"}


def test_bridge_rejects_wrong_credentials_and_models(client):
    response = client.post("/v1/messages", json={"model": "gpt-6.1-sol"})
    assert response.status_code == 401
    response = client.post(
        "/v1/messages",
        headers={"authorization": "Bearer gpt-test-key"},
        json={"model": "other-model"},
    )
    assert response.status_code == 400


def test_bridge_does_not_return_sdk_exception_secrets(client, monkeypatch):
    monkeypatch.setattr(
        "litellm.aresponses",
        AsyncMock(side_effect=RuntimeError("credential=claude-test-key")),
    )
    response = client.post(
        "/v1/responses",
        headers={"authorization": "Bearer claude-test-key"},
        json={"model": "claude-opus-5.5", "input": "fixture"},
    )
    assert response.status_code == 502
    assert "claude-test-key" not in response.text
