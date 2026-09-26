from __future__ import annotations

from pathlib import Path

from harbor.agents.factory import AgentFactory
from harbor.models.trial.config import AgentConfig

from adapters.fake_agent import FakeAgent


def test_fake_agent_has_stable_harbor_contract() -> None:
    agent = FakeAgent(logs_dir=Path("/tmp/fake-agent"))
    assert agent.name() == "fake-agent"
    assert agent.version() == "0.1.0"


def test_fake_agent_is_discoverable_through_harbor_factory() -> None:
    agent_class = AgentFactory.get_agent_class_from_config(
        AgentConfig(name="fake-agent", import_path="adapters.fake_agent:FakeAgent")
    )
    assert agent_class is FakeAgent
