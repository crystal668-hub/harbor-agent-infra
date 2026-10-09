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
    with pytest.raises(ValueError, match="Hermes trajectory"):
        response_from_agent_artifacts(tmp_path, agent_name="hermes")


def test_agent_parser_rejects_unknown_agent(tmp_path) -> None:
    with pytest.raises(ValueError, match="unsupported agent"):
        response_from_agent_artifacts(tmp_path, agent_name="unknown")
