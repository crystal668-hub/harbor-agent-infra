from copy import deepcopy
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


@pytest.mark.parametrize(
    "result",
    [
        {"id": "msg-fixture", "content": [{"type": "text", "text": "BRIDGE_OK"}]},
        FakeResponse(),
    ],
)
def test_nonstream_messages_route_serializes_dict_and_pydantic_results(client, monkeypatch, result):
    handler = AsyncMock(return_value=result)
    monkeypatch.setattr("litellm.anthropic.messages.acreate", handler)

    response = client.post(
        "/v1/messages",
        headers={"x-api-key": "gpt-test-key"},
        json={"model": "gpt-6.1-sol", "stream": False, "messages": []},
    )

    assert response.status_code == 200
    assert response.json() == (
        result.model_dump(mode="json", exclude_none=True)
        if isinstance(result, BaseModel) else result
    )


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


@pytest.mark.parametrize("route", ["/anthropic/v1/responses", "/v1/responses"])
def test_claude_route_omits_empty_assistant_text_after_tool_call(client, monkeypatch, route):
    handler = AsyncMock(return_value=FakeResponse())
    monkeypatch.setattr("litellm.aresponses", handler)
    tool_call = {
        "type": "function_call",
        "name": "exec_command",
        "call_id": "call-1",
        "arguments": '{"cmd":"printf OK"}',
    }
    tool_result = {
        "type": "function_call_output",
        "call_id": "call-1",
        "output": "OK",
    }
    assistant_text = {
        "type": "message",
        "role": "assistant",
        "content": [
            {"type": "output_text", "text": "Still working."},
            {"type": "output_text", "text": ""},
        ],
    }
    payload = {
        "model": "claude-opus-5.5",
        "input": [
            tool_call,
            tool_result,
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": ""}],
            },
            assistant_text,
            {"type": "message", "role": "user", "content": "Continue."},
        ],
    }

    response = client.post(
        route,
        headers={"authorization": "Bearer claude-test-key"},
        json=payload,
    )

    assert response.status_code == 200
    captured_input = handler.await_args.kwargs["input"]
    assert captured_input == [
        tool_call,
        tool_result,
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Still working."}],
        },
        {"type": "message", "role": "user", "content": "Continue."},
    ]


def test_claude_normalization_preserves_nonempty_and_nontext_content(client, monkeypatch):
    handler = AsyncMock(return_value=FakeResponse())
    monkeypatch.setattr("litellm.aresponses", handler)
    retained = [
        {"role": "assistant", "content": " "},
        {"type": "message", "role": "user", "content": ""},
        {"type": "message", "role": "developer", "content": "instructions"},
        {"type": "reasoning", "summary": []},
        {
            "type": "message",
            "role": "assistant",
            "id": "msg-refusal",
            "content": [{"type": "refusal", "refusal": "Cannot do that."}],
        },
    ]
    payload = {
        "model": "claude-opus-5.5",
        "input": [
            {"role": "assistant", "content": ""},
            {"type": "message", "role": "assistant", "content": []},
            *deepcopy(retained),
        ],
    }
    payload["input"][-1]["content"].append({"type": "output_text", "text": ""})
    response = client.post(
        "/anthropic/v1/responses",
        headers={"authorization": "Bearer claude-test-key"},
        json=payload,
    )
    assert response.status_code == 200
    assert handler.await_args.kwargs["input"] == retained


@pytest.mark.parametrize("rounds", [1, 3])
def test_claude_tool_history_passes_real_chat_conversion(client, monkeypatch, rounds):
    import litellm

    history = [{"role": "user", "content": "Use the supplied tool results to answer."}]
    for index in range(rounds):
        history.extend([
            {
                "type": "function_call",
                "name": "exec_command",
                "call_id": f"call-{index}",
                "arguments": '{"cmd":"printf OK"}',
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": ""}],
            },
            {"type": "function_call_output", "call_id": f"call-{index}", "output": "OK"},
        ])

    async def strict_chat_endpoint(**kwargs):
        messages = kwargs["messages"]
        for message in messages:
            content = message.get("content")
            if content == "" or (
                isinstance(content, list)
                and any(part.get("type") == "text" and part.get("text") == "" for part in content)
            ):
                raise ValueError("messages: text content blocks must be non-empty")
        calls = [call for message in messages for call in message.get("tool_calls", [])]
        results = [message for message in messages if message["role"] == "tool"]
        assert [call["id"] for call in calls] == [result["tool_call_id"] for result in results]
        assert len(calls) == rounds
        assert all(call["function"]["arguments"] == '{"cmd":"printf OK"}' for call in calls)
        assert all(result["content"] == "OK" for result in results)
        return litellm.ModelResponse(
            model="claude-opus-5.5",
            choices=[{"message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
        )

    endpoint = AsyncMock(side_effect=strict_chat_endpoint)
    monkeypatch.setattr(litellm, "acompletion", endpoint)
    response = client.post(
        "/anthropic/v1/responses",
        headers={"authorization": "Bearer claude-test-key"},
        json={"model": "claude-opus-5.5", "input": history},
    )
    assert response.status_code == 200, response.text
    assert any(
        part.get("text") == "OK"
        for item in response.json()["output"]
        for part in item.get("content", [])
    )
    endpoint.assert_awaited_once()
