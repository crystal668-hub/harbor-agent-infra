from __future__ import annotations

import json

import pytest

from integrations.vgb.agent_output import response_from_agent_artifacts


def test_hermes_parser_uses_final_visible_agent_message(tmp_path) -> None:
    trajectory = tmp_path / "trajectory.json"
    trajectory.write_text(
        json.dumps(
            {
                "steps": [
                    {"source": "user", "message": "prompt"},
                    {"source": "agent", "message": "[tool call]"},
                    {"source": "agent", "message": "final answer"},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert response_from_agent_artifacts(tmp_path, agent_name="hermes") == "final answer"


@pytest.mark.parametrize(
    "payload",
    [{}, {"steps": []}, {"steps": [{"source": "agent", "message": "[tool call]"}]}],
)
def test_hermes_parser_rejects_missing_final_message(tmp_path, payload) -> None:
    (tmp_path / "trajectory.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="ATIF trajectory"):
        response_from_agent_artifacts(tmp_path, agent_name="hermes")


def test_agent_parser_rejects_unknown_agent(tmp_path) -> None:
    with pytest.raises(ValueError, match="unsupported agent"):
        response_from_agent_artifacts(tmp_path, agent_name="unknown")


@pytest.mark.parametrize("agent", ["hermes", "codex", "claude-code"])
def test_atif_reads_text_after_tools_and_ignores_placeholder(tmp_path, agent):
    payload = {
        "agent": {"name": agent},
        "steps": [
            {"source": "user", "message": "not an answer"},
            {"source": "agent", "message": "working", "tool_calls": [{}, {}]},
            {
                "source": "agent",
                "message": [{"type": "text", "text": "answer"}, {"type": "image", "url": "image"}],
            },
            {"source": "agent", "message": " [tool call] "},
        ],
    }
    path = tmp_path / "trajectory.json"
    path.write_text(json.dumps(payload))
    assert response_from_agent_artifacts(tmp_path, agent_name=agent) == "answer"
    payload["agent"]["name"] = "different-agent"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="mismatch"):
        response_from_agent_artifacts(tmp_path, agent_name=agent)
    path.write_text("broken json")
    with pytest.raises(ValueError, match="not valid JSON"):
        response_from_agent_artifacts(tmp_path, agent_name=agent)
