import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from scripts.native_protocol_bridge import create_app

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("stream", [False, True])
def test_claude_accepts_empty_assistant_history_through_bridge(stream):
    if os.environ.get("RUN_CLAUDE_BRIDGE_SMOKE") != "1":
        pytest.skip("set RUN_CLAUDE_BRIDGE_SMOKE=1 to call the Claude provider")
    load_dotenv(Path.cwd() / ".env", override=False)
    required = ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL")
    if any(not os.environ.get(name) for name in required):
        pytest.fail("Claude bridge smoke requires the Anthropic provider configuration")

    history = [{"role": "user", "content": "The tools returned OK. Reply only OK."}]
    for index in range(3):
        history.extend([
            {
                "type": "function_call",
                "name": "exec_command",
                "call_id": f"call_probe_{index}",
                "arguments": '{"cmd":"printf OK"}',
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": ""}],
            },
            {"type": "function_call_output", "call_id": f"call_probe_{index}", "output": "OK"},
        ])
    with TestClient(create_app()) as client:
        response = client.post(
            "/anthropic/v1/responses",
            headers={"authorization": f"Bearer {os.environ['ANTHROPIC_API_KEY']}"},
            json={
                "model": "claude-opus-5.5",
                "stream": stream,
                "input": history,
                "reasoning": {"effort": "high", "summary": "auto"},
                "tools": [{
                    "type": "function",
                    "name": "exec_command",
                    "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}}},
                }],
            },
        )
    assert response.status_code == 200, response.text
    if stream:
        events = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        assert any(event.get("type") == "response.completed" for event in events)
        assert not any(event.get("type") in {"error", "response.failed"} for event in events)
    else:
        assert response.json()["status"] == "completed"
