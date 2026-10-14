from __future__ import annotations

from pathlib import Path

import pytest
from harbor.utils.env import resolve_env_vars
from pydantic import ValidationError

from harbor_agent_infra.contracts.experiment import AgentSpec
from harbor_agent_infra.harness_runner import (
    HermesHarnessRunner,
    OpenClawHarnessRunner,
    harness_runner_for,
)
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock


def test_harness_registry_selects_runner_from_validated_adapter() -> None:
    openclaw = harness_runner_for("openclaw")
    hermes = harness_runner_for("hermes")

    assert isinstance(openclaw, OpenClawHarnessRunner)
    assert openclaw.runner_id == "harbor_openclaw"
    assert isinstance(hermes, HermesHarnessRunner)
    assert hermes.runner_id == "harbor_hermes"


def test_harness_registry_rejects_unregistered_adapter() -> None:
    with pytest.raises(ValueError, match="unsupported agent harness"):
        harness_runner_for("unknown")


@pytest.mark.parametrize(
    "agent,provider,target",
    [
        ("codex", "anthropic", "OPENAI"),
        ("codex", "qwen", "OPENAI"),
        ("codex", "deepseek", "OPENAI"),
        ("claude-code", "openai", "ANTHROPIC"),
        ("claude-code", "qwen", "ANTHROPIC"),
        ("claude-code", "deepseek", "ANTHROPIC"),
    ],
)
def test_native_provider_routing_keeps_credentials_as_host_references(
    agent, provider, target, monkeypatch
) -> None:
    source = provider.upper()
    monkeypatch.setenv(f"{source}_API_KEY", "selected-provider-secret")
    monkeypatch.setenv("CROSS_MODEL_URL", "https://selected.example/v1")
    spec = AgentSpec(
        adapter=agent,
        model="exact-model-id",
        provider=provider,
        base_url_env="CROSS_MODEL_URL",
        reasoning_effort="high",
    )
    config = harness_runner_for(agent).build_agent_config(
        spec, load_runtime_lock(Path("runtime-lock.json"))
    )
    assert config.name == agent and config.import_path is None
    assert config.model_name == "exact-model-id"
    assert config.kwargs["reasoning_effort"] == "high"
    assert config.env == {
        f"{target}_API_KEY": f"${{{source}_API_KEY}}",
        f"{target}_BASE_URL": "${CROSS_MODEL_URL}",
    }
    assert resolve_env_vars(config.env) == {
        f"{target}_API_KEY": "selected-provider-secret",
        f"{target}_BASE_URL": "https://selected.example/v1",
    }
    persisted = config.model_dump_json()
    assert "selected-provider-secret" not in persisted
    assert "https://selected.example" not in persisted
    assert config.model_validate_json(persisted).env == config.env


def test_native_provider_uses_its_own_base_url_by_default() -> None:
    config = harness_runner_for("codex").build_agent_config(
        AgentSpec(adapter="codex", model="qwen3.8-flash", provider="qwen"),
        load_runtime_lock(Path("runtime-lock.json")),
    )
    assert config.env["OPENAI_BASE_URL"] == "${QWEN_BASE_URL}"


def test_unselected_provider_preserves_legacy_agent_serialization() -> None:
    # experiment_sha256 includes this payload; adding unused defaults must not
    # invalidate historical run manifests or failure-recovery configurations.
    spec = AgentSpec(adapter="codex", model="gpt-5.6-sol", reasoning_effort="high")
    assert spec.model_dump(mode="json") == {
        "adapter": "codex",
        "model": "gpt-5.6-sol",
        "thinking": None,
        "reasoning": None,
        "reasoning_effort": "high",
    }


@pytest.mark.parametrize(
    "options",
    [
        {"adapter": "hermes", "provider": "qwen"},
        {"adapter": "openclaw", "base_url_env": "ENDPOINT"},
        {"adapter": "codex", "base_url_env": "ENDPOINT"},
        {"adapter": "codex", "provider": "qwen", "base_url_env": "https://example/v1"},
    ],
)
def test_provider_routing_rejects_ambiguous_or_literal_configuration(options) -> None:
    with pytest.raises(ValidationError):
        AgentSpec(model="fixture", **options)


@pytest.mark.parametrize("cap", [0, -1, 1.5, True])
def test_output_cap_requires_positive_integer(cap):
    with pytest.raises(ValidationError):
        AgentSpec(adapter="hermes", model="fixture", max_output_tokens=cap)


def test_single_group_openclaw_keeps_explicit_reasoning_and_output_cap():
    spec = AgentSpec(
        adapter="openclaw",
        model="anthropic/claude-opus-5.5",
        thinking="high",
        max_output_tokens=64_000,
    )
    config = harness_runner_for("openclaw").build_agent_config(
        spec, load_runtime_lock(Path("runtime-lock.json")), paired=False
    )
    from harbor.agents.factory import AgentFactory

    agent = AgentFactory.create_agent_from_config(config, logs_dir=Path("/tmp/cap-test"))
    agent.session_id = "output-cap-test__agent"
    projected = agent._build_full_openclaw_config()
    assert config.kwargs["thinking"] == "high"
    assert projected["agents"]["defaults"]["models"][spec.model]["params"]["maxTokens"] == 64_000
    assert projected["models"]["providers"]["anthropic"]["models"][0]["maxTokens"] == 64_000


def test_codex_output_cap_rejects_direct_endpoint():
    spec = AgentSpec(
        adapter="codex", model="qwen3.8-max", provider="qwen", max_output_tokens=64_000
    )
    with pytest.raises(ValueError, match="bridge endpoint"):
        harness_runner_for("codex").build_agent_config(
            spec, load_runtime_lock(Path("runtime-lock.json"))
        )
