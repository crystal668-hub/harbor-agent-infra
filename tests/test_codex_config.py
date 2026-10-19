from copy import deepcopy
from pathlib import Path

import pytest
from harbor.agents.factory import AgentFactory
from harbor.utils.env import resolve_env_vars
from pydantic import ValidationError

from harbor_agent_infra.contracts.experiment import AgentSpec
from harbor_agent_infra.harness_runner import harness_runner_for
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock


def custom_spec(provider="qwen", **overrides):
    provider_id = f"{provider}-responses"
    provider_name = {"qwen": "Qwen", "deepseek": "DeepSeek"}[provider]
    return {
        "adapter": "codex",
        "provider": provider,
        "model": "qwen3.8-max" if provider == "qwen" else "deepseek-v4-pro",
        "base_url_env": f"CODEX_{provider.upper()}_BASE_URL",
        "reasoning_effort": "high",
        "max_output_tokens": 64_000,
        "codex_config": {
            "model_provider": provider_id,
            "model_providers": {provider_id: {
                "name": f"{provider_name} Responses via Harbor cap bridge",
                "env_key": "OPENAI_API_KEY",
                "wire_api": "responses",
                "requires_openai_auth": True,
                "supports_websockets": False,
            }},
        },
        **overrides,
    }


@pytest.mark.parametrize("provider", ["qwen", "deepseek"])
@pytest.mark.parametrize("installation_mode", ["runtime_install", "preinstalled"])
def test_native_config_binds_runtime_bridge_without_changing_other_settings(
    provider, installation_mode, tmp_path, monkeypatch
):
    monkeypatch.setenv(f"{provider.upper()}_API_KEY", "fixture-provider-secret")
    monkeypatch.setenv(f"CODEX_{provider.upper()}_BASE_URL", "http://bridge.example/route/v1")
    spec = AgentSpec(**custom_spec(provider, installation_mode=installation_mode))
    original = deepcopy(spec.codex_config)
    lock_path = (
        Path("runtime-lock.preinstalled.json")
        if installation_mode == "preinstalled"
        else Path("runtime-lock.json")
    )
    config = harness_runner_for("codex").build_agent_config(
        spec, load_runtime_lock(lock_path)
    )
    assert config.kwargs["config"] == original
    assert config.kwargs["reasoning_effort"] == "high"
    assert config.env["OPENAI_BASE_URL"] == f"${{CODEX_{provider.upper()}_BASE_URL}}"
    assert config.env["OPENAI_API_KEY"] == f"${{{provider.upper()}_API_KEY}}"
    assert resolve_env_vars(config.env) == {
        "OPENAI_API_KEY": "fixture-provider-secret",
        "OPENAI_BASE_URL": "http://bridge.example/route/v1",
    }
    assert config.model_name == spec.model and config.skills == []
    assert config.import_path == (
        "adapters.preinstalled:CodexAgent" if installation_mode == "preinstalled"
        else "adapters.codex:CodexAgent"
    )
    agent = AgentFactory.create_agent_from_config(config, logs_dir=tmp_path)
    endpoint = f"http://bridge.example:4141/{provider}/v1"
    effective = agent._build_effective_config(endpoint)
    assert effective["model_providers"][f"{provider}-responses"]["base_url"] == endpoint
    assert effective["openai_base_url"] == endpoint
    assert set(effective) == {"openai_base_url", "model_provider", "model_providers"}
    assert spec.codex_config == original
    assert config.kwargs["config"] == original
    assert "fixture-provider-secret" not in config.model_dump_json()
    # Each invocation binds the current endpoint, without mutating the base config.
    assert agent._build_effective_config(endpoint + "/new")["model_providers"][
        f"{provider}-responses"
    ]["base_url"] == endpoint + "/new"
    with pytest.raises(ValueError, match="cap-bridge URL"):
        agent._build_effective_config()


@pytest.mark.parametrize("overrides", [
    {"adapter": "claude-code"},
    {"provider": "openai"},
    {"model": "different-model"},
    {"base_url_env": "QWEN_BASE_URL"},
    {"max_output_tokens": None},
    {"reasoning_effort": "low"},
])
def test_custom_config_rejects_incompatible_agent_conditions(overrides):
    spec = custom_spec()
    spec.update(overrides)
    with pytest.raises(ValidationError):
        AgentSpec(**spec)


@pytest.mark.parametrize("change", [
    {"model_provider": "openai"},
    {"model_providers": {}},
    {"compact_prompt": "silently change the summary"},
    {"model_context_window": 999999},
    {"openai_base_url": "https://direct.example/v1"},
])
def test_native_config_rejects_implicit_condition_changes(change):
    spec = custom_spec()
    spec["codex_config"].update(change)
    with pytest.raises(ValidationError):
        AgentSpec(**spec)


@pytest.mark.parametrize("change", [
    {"wire_api": "chat"},
    {"env_key": "QWEN_API_KEY"},
    {"requires_openai_auth": False},
    {"supports_websockets": True},
    {"base_url": "https://direct.example/v1"},
    {"http_headers": {"Authorization": "secret"}},
])
def test_custom_provider_cannot_bypass_bridge_or_auth_contract(change):
    spec = custom_spec()
    spec["codex_config"]["model_providers"]["qwen-responses"].update(change)
    with pytest.raises(ValidationError):
        AgentSpec(**spec)
