from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from harbor.agents.factory import AgentFactory
from harbor.models.trial.config import AgentConfig

from adapters.openclaw.adapter import OpenClawAgent
from adapters.openclaw.evidence import collect_evidence
from adapters.openclaw.failure import OpenClawFailureCode, classify_failure
from adapters.openclaw.session import SessionIdentity


def _agent(tmp_path: Path) -> OpenClawAgent:
    agent = OpenClawAgent(
        logs_dir=tmp_path / "logs",
        model_name="openai/fixture-model",
        version="9.5",
    )
    agent.session_id = "task__attempt-1__agent"
    return agent


def test_session_identity_is_explicit_and_attempt_scoped() -> None:
    identity = SessionIdentity.from_harbor_session("task__attempt-1__agent")
    retry = SessionIdentity.from_harbor_session("task__attempt-2__agent")
    assert identity.agent_id == "openclaw"
    assert identity.session_key == "agent:openclaw:explicit:task__attempt-1"
    assert identity.session_id != retry.session_id
    assert identity.environment()["OPENCLAW_STATE_DIR"].endswith(
        "/task__attempt-1"
    )


def test_session_identity_uses_harbor_context_for_retry_isolation() -> None:
    first = SessionIdentity.from_harbor_session(
        "task__attempt-1__agent", context_id=uuid4()
    )
    second = SessionIdentity.from_harbor_session(
        "task__attempt-1__agent", context_id=uuid4()
    )
    assert first.session_id != second.session_id
    assert first.session_key != second.session_key
    assert first.state_dir != second.state_dir


def test_openclaw_adapter_projects_context_id_into_identity(tmp_path: Path) -> None:
    first = _agent(tmp_path)
    second = _agent(tmp_path)
    first.context_id = uuid4()
    second.context_id = uuid4()
    assert first.session_identity().session_key != second.session_identity().session_key


def test_openclaw_config_and_command_project_identity(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    config = agent._build_full_openclaw_config()
    entry = config["agents"]["entries"]["openclaw"]
    assert config["agents"]["ownership"] == "explicit"
    assert entry["workspace"] == "/workspace"
    assert entry["agentDir"].endswith("/agents/openclaw")
    assert "--agent openclaw" in agent.build_cli_flags()
    assert "--session-key agent:openclaw:explicit:task__attempt-1" in agent.build_cli_flags()
    assert "--session-id task__attempt-1" in agent.build_cli_flags()
    assert agent.session_inventory_command() == (
        "openclaw sessions --json --agent openclaw --limit all"
    )
    assert "--session-key agent:openclaw:explicit:task__attempt-1" in (
        agent.trajectory_export_command()
    )


def test_openclaw_adapter_is_discoverable_through_harbor_factory() -> None:
    agent_class = AgentFactory.get_agent_class_from_config(
        AgentConfig(
            import_path="adapters.openclaw.adapter:OpenClawAgent",
            model_name="openai/fixture-model",
        )
    )
    assert agent_class.__name__ == "OpenClawAgent"
    assert agent_class.capabilities.atif is True


def test_evidence_manifest_hashes_files_without_copying_content(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "openclaw.txt").write_text('{"sessionId":"s"}\n', encoding="utf-8")
    identity = SessionIdentity.from_harbor_session("task__attempt-1__agent")
    manifest = collect_evidence(logs, identity)
    output = logs / "openclaw-evidence.json"
    manifest.write(output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "openclaw-evidence.v1"
    assert payload["identity"]["session_id"] == "task__attempt-1"
    assert payload["files"]["openclaw.txt"]["size"] > 0


def test_failure_mapping_is_stable() -> None:
    code, details = classify_failure(RuntimeError("session owner mismatch"))
    assert code is OpenClawFailureCode.SESSION_OWNER_MISMATCH
    assert details["exception_type"] == "RuntimeError"
