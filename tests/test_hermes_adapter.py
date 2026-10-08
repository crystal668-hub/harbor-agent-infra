from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from harbor.agents.factory import AgentFactory
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


def test_hermes_rejects_non_commit_source(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="source_commit"):
        HermesAgent(
            logs_dir=tmp_path / "logs",
            model_name="openai/fixture-model",
            version="v0.21.6",
            source_commit="main",
            install_branch="main",
        )
