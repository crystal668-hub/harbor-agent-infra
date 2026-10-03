from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

from harbor.agents.factory import AgentFactory
from harbor.agents.installed.base import NonZeroAgentExitCodeError
from harbor.agents.installed.openclaw import OpenClaw as HarborOpenClaw
from harbor.models.trial.config import AgentConfig

from adapters.openclaw.adapter import OpenClawAgent
from adapters.openclaw.evidence import collect_evidence
from adapters.openclaw.failure import OpenClawFailureCode, classify_failure
from adapters.openclaw.session import SessionIdentity


def _agent(tmp_path: Path) -> OpenClawAgent:
    agent = OpenClawAgent(
        logs_dir=tmp_path / "logs",
        model_name="openai/fixture-model",
        version="2026.6.34",
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


def test_openclaw_config_and_command_project_identity(tmp_path: Path, monkeypatch) -> None:
    agent = _agent(tmp_path)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://provider.example/v1")
    assert agent._SETUP_CLI == "openclaw setup --workspace ."
    config = agent._build_full_openclaw_config()
    entries = config["agents"]["list"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["id"] == "openclaw"
    assert entry["workspace"] == "/workspace"
    assert entry["agentDir"].endswith("/agents/openclaw")
    assert config["models"]["providers"]["openai"]["models"] == [
        {"id": "fixture-model", "name": "fixture-model"}
    ]
    assert "--agent openclaw" in agent.build_cli_flags()
    assert "--session-key agent:openclaw:explicit:task__attempt-1" in agent.build_cli_flags()
    assert "--session-id task__attempt-1" in agent.build_cli_flags()
    assert agent.session_inventory_command() == (
        "openclaw sessions --json --agent openclaw --limit all"
    )


def test_openai_gpt_56_sol_custom_provider_preserves_thinking_profile(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://provider.example/v1")
    agent = OpenClawAgent(
        logs_dir=tmp_path / "logs",
        model_name="openai/gpt-5.6-sol",
        version="2026.6.34",
    )
    agent.session_id = "task__attempt-1__agent"
    model = agent._build_full_openclaw_config()["models"]["providers"]["openai"]["models"][0]
    assert model["id"] == "gpt-5.6-sol"
    assert model["thinkingLevelMap"]["xhigh"] == "xhigh"
    assert "xhigh" in model["compat"]["supportedReasoningEfforts"]
    assert "--session-key agent:openclaw:explicit:task__attempt-1" in (
        agent.trajectory_export_command()
    )


def test_qwen_openai_compatible_provider_is_configured_from_qwen_env(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("QWEN_BASE_URL", "https://qwen.example/v1")
    monkeypatch.setenv("QWEN_API_KEY", "test-qwen-key")
    agent = OpenClawAgent(
        logs_dir=tmp_path / "logs",
        model_name="qwen/qwen3.8-flash",
        version="2026.6.34",
    )
    agent.session_id = "task__attempt-1__agent"

    config = agent._build_full_openclaw_config()
    provider = config["models"]["providers"]["qwen"]
    assert provider["baseUrl"] == "https://qwen.example/v1"
    assert provider["models"] == [
        {"id": "qwen3.8-flash", "name": "qwen3.8-flash"}
    ]
    assert "qwen" in agent._SUPPORTED_PROVIDERS


def test_openclaw_adapter_is_discoverable_through_harbor_factory() -> None:
    agent_class = AgentFactory.get_agent_class_from_config(
        AgentConfig(
            import_path="adapters.openclaw.adapter:OpenClawAgent",
            model_name="openai/fixture-model",
        )
    )
    assert agent_class.__name__ == "OpenClawAgent"
    assert agent_class.capabilities.atif is True


def test_openclaw_retries_transient_debian_5xx(tmp_path: Path, monkeypatch) -> None:
    install = AsyncMock(
        side_effect=[
            NonZeroAgentExitCodeError("Failed to fetch http://deb.debian.org/a  502 Bad Gateway"),
            NonZeroAgentExitCodeError(
                "Failed to fetch http://deb.debian.org/b  500 unexpected EOF"
            ),
            None,
        ]
    )
    sleep = AsyncMock()
    monkeypatch.setattr(HarborOpenClaw, "ensure_system_dependencies", install)
    monkeypatch.setattr("adapters.openclaw.adapter.asyncio.sleep", sleep)
    asyncio.run(_agent(tmp_path).ensure_system_dependencies(None, ("curl",)))
    assert install.await_count == 3
    assert [call.args for call in sleep.await_args_list] == [(1,), (2,)]


def test_openclaw_does_not_retry_other_install_errors(tmp_path: Path, monkeypatch) -> None:
    install = AsyncMock(side_effect=NonZeroAgentExitCodeError("package not found"))
    monkeypatch.setattr(HarborOpenClaw, "ensure_system_dependencies", install)
    try:
        asyncio.run(_agent(tmp_path).ensure_system_dependencies(None, ("curl",)))
    except NonZeroAgentExitCodeError:
        pass
    else:
        raise AssertionError("expected package installation failure")
    install.assert_awaited_once()


def test_openclaw_retries_npm_connection_reset(tmp_path: Path, monkeypatch) -> None:
    install = AsyncMock(
        side_effect=[NonZeroAgentExitCodeError("npm error code ECONNRESET"), None]
    )
    sleep = AsyncMock()
    monkeypatch.setattr(HarborOpenClaw, "install", install)
    monkeypatch.setattr("adapters.openclaw.adapter.asyncio.sleep", sleep)
    asyncio.run(_agent(tmp_path).install(None))
    assert install.await_count == 2
    sleep.assert_awaited_once_with(1)


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
