from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import yaml
from harbor.agents.factory import AgentFactory
from harbor.agents.installed.base import NonZeroAgentExitCodeError
from harbor.models.trial.config import AgentConfig

from adapters.hermes.adapter import HermesAgent

SOURCE_COMMIT = "818c13be1dc4fd28987e1e881a9408224afd4535"


def _agent(tmp_path: Path) -> HermesAgent:
    return HermesAgent(
        logs_dir=tmp_path / "logs",
        model_name="openai/fixture-model",
        version="v0.21.6",
        source_commit=SOURCE_COMMIT,
        install_branch="main",
    )


def test_hermes_adapter_is_discoverable_through_harbor_factory() -> None:
    agent_class = AgentFactory.get_agent_class_from_config(
        AgentConfig(
            import_path="adapters.hermes.adapter:HermesAgent",
            model_name="openai/fixture-model",
            kwargs={
                "version": "v0.21.6",
                "source_commit": SOURCE_COMMIT,
                "install_branch": "main",
            },
        )
    )
    assert agent_class is HermesAgent
    assert agent_class.capabilities.atif is True


def test_hermes_uses_current_version_command(tmp_path: Path) -> None:
    assert _agent(tmp_path).get_version_command().endswith("hermes --version")


def test_hermes_config_disables_onboarding(tmp_path: Path) -> None:
    config = yaml.safe_load(_agent(tmp_path)._build_config_yaml("qwen3.8-flash"))
    assert config["onboarding"]["profile_build"] == "off"
    assert all(config["onboarding"]["seen"].values())


def test_hermes_config_projects_reasoning_effort(tmp_path: Path) -> None:
    agent = HermesAgent(
        logs_dir=tmp_path / "logs",
        model_name="openai/fixture-model",
        version="v0.21.6",
        source_commit=SOURCE_COMMIT,
        install_branch="main",
        reasoning="high",
    )

    config = yaml.safe_load(agent._build_config_yaml("fixture-model"))

    assert config["agent"]["reasoning_effort"] == "high"


def test_hermes_install_pins_installer_and_checkout(tmp_path: Path, monkeypatch) -> None:
    agent = _agent(tmp_path)
    dependencies = AsyncMock()
    execute = AsyncMock()
    monkeypatch.setattr(agent, "ensure_system_dependencies", dependencies)
    monkeypatch.setattr(agent, "exec_as_agent", execute)

    asyncio.run(agent.install(None))

    dependencies.assert_awaited_once_with(None, ("curl", "git", "ripgrep", "xz"))
    command = execute.await_args.kwargs["command"]
    assert f"/{SOURCE_COMMIT}/scripts/install.sh" in command
    assert "curl --retry 5 --retry-all-errors --retry-delay 2" in command
    assert "--branch main" in command
    assert f"--commit {SOURCE_COMMIT}" in command
    assert command.endswith("hermes --version")
    assert "hermes version" not in command
    assert command.index("export HERMES_HOME") < command.index("curl --retry")


def test_hermes_retries_package_manager_install_failures(tmp_path: Path, monkeypatch) -> None:
    agent = _agent(tmp_path)
    dependencies = AsyncMock()
    execute = AsyncMock(side_effect=[NonZeroAgentExitCodeError("pm install failed"), None])
    sleep = AsyncMock()
    monkeypatch.setattr(agent, "ensure_system_dependencies", dependencies)
    monkeypatch.setattr(agent, "exec_as_agent", execute)
    monkeypatch.setattr("adapters.hermes.adapter.asyncio.sleep", sleep)

    asyncio.run(agent.install(None))

    assert execute.await_count == 2
    sleep.assert_awaited_once_with(1)


def test_hermes_qwen_export_prefers_oneshot_sessions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QWEN_API_KEY", "test-key")
    monkeypatch.setenv("QWEN_BASE_URL", "https://qwen.example/v1")
    agent = HermesAgent(
        logs_dir=tmp_path / "logs",
        model_name="qwen/qwen3.8-flash",
        version="v0.21.6",
        source_commit=SOURCE_COMMIT,
        install_branch="main",
        reasoning="high",
    )
    execute = AsyncMock(
        side_effect=[
            SimpleNamespace(stdout=""),
            SimpleNamespace(stdout=""),
            SimpleNamespace(stdout=""),
        ]
    )
    monkeypatch.setattr(agent, "exec_as_agent", execute)

    asyncio.run(agent.run("reply with marker", None, None))

    config_command = execute.await_args_list[0].kwargs["command"]
    assert "rm -f /workspace/BOOTSTRAP.md /workspace/IDENTITY.md" in config_command
    run_command = execute.await_args_list[1].kwargs["command"]
    assert "--reasoning high" in run_command
    export_command = execute.await_args_list[-1].kwargs["command"]
    assert "--source oneshot" in export_command
    assert "--source cli" in export_command


def test_hermes_rejects_non_commit_source(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="source_commit"):
        HermesAgent(
            logs_dir=tmp_path / "logs",
            model_name="openai/fixture-model",
            version="v0.21.6",
            source_commit="main",
            install_branch="main",
        )


def test_hermes_requires_qwen_credentials(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_BASE_URL", raising=False)
    agent = HermesAgent(
        logs_dir=tmp_path / "logs",
        model_name="qwen/qwen3.8-flash",
        version="v0.21.6",
        source_commit=SOURCE_COMMIT,
        install_branch="main",
    )
    with pytest.raises(ValueError, match="QWEN_API_KEY"):
        asyncio.run(agent.run("reply with marker", None, None))
