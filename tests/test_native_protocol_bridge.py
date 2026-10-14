from unittest.mock import AsyncMock

import httpx
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
        assert kwargs["max_output_tokens"] == 64_000
        assert kwargs["extra_body"]["max_tokens"] == 64_000
    else:
        assert kwargs["max_tokens"] == 64_000


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


@pytest.mark.parametrize(
    "provider,model",
    [("openai", "gpt-6.1-sol"), ("qwen", "qwen3.8-max"), ("deepseek", "deepseek-v4-pro")],
)
def test_responses_cap_bridge_injects_on_every_request(provider, model, monkeypatch):
    monkeypatch.setenv(provider.upper() + "_API_KEY", "test-route-key")
    monkeypatch.setenv(provider.upper() + "_BASE_URL", "https://upstream.example/v1")
    captured = []

    async def send(self, request, **kwargs):
        import json

        captured.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer test-route-key"
        return httpx.Response(
            200,
            content=b'data: {"type":"response.completed"}\n\n',
            headers={"content-type": "text/event-stream"},
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    with TestClient(create_app()) as client:
        for cap in (None, 128_000):
            payload = {"model": model, "input": "fixture", "stream": True}
            if cap is not None:
                payload["max_output_tokens"] = cap
            response = client.post(
                f"/{provider}/v1/responses",
                json=payload,
                headers={"authorization": "Bearer test-route-key"},
            )
            assert response.status_code == 200 and "response.completed" in response.text
    assert [r["max_output_tokens"] for r in captured] == [64_000, 64_000]


def test_capped_claude_route_uses_chat_conversion(client, monkeypatch):
    handler = AsyncMock(return_value=FakeResponse())
    monkeypatch.setattr("litellm.aresponses", handler)
    response = client.post(
        "/anthropic/v1/responses",
        headers={"authorization": "Bearer claude-test-key"},
        json={"model": "claude-opus-5.5", "input": "fixture", "max_output_tokens": 128000},
    )
    assert response.status_code == 200
    assert handler.await_args.kwargs["max_output_tokens"] == 64_000
    assert handler.await_args.kwargs["extra_body"]["max_tokens"] == 64_000
