from pathlib import Path

import pytest
import yaml
from test_task_materializer import FakeVgbRuntime

from harbor_agent_infra.contracts.run import RunConfig
from harbor_agent_infra.harbor.job_config import materialize_paired_job_configs
from harbor_agent_infra.preparation.experiments import expand_required


@pytest.mark.parametrize(
    "agent,filename,model",
    [
        ("codex", "vgb-gpt.config.yaml", "gpt-6.1-sol"),
        ("claude-code", "vgb-claude.config.yaml", "claude-opus-5.5"),
        ("codex", "vgb-claude.config.yaml", "claude-opus-5.5"),
        ("codex", "vgb-qwen.config.yaml", "qwen3.8-max"),
        ("codex", "vgb-deepseek.config.yaml", "deepseek-v4-pro"),
        ("claude-code", "vgb-gpt.config.yaml", "gpt-6.1-sol"),
        ("claude-code", "vgb-qwen.config.yaml", "qwen3.8-max"),
        ("claude-code", "vgb-deepseek.config.yaml", "deepseek-v4-pro"),
    ],
)
def test_native_templates_materialize_only_requested_group(
    agent, filename, model, tmp_path, monkeypatch
):
    monkeypatch.setenv("OPENCLAW_SKILLS_ROOT", str(tmp_path / "not-needed"))
    monkeypatch.setenv("VGB_PYTHON", "/unused/vgb/python")
    path = Path("examples/experiments") / agent / filename
    config = RunConfig.model_validate(expand_required(yaml.safe_load(path.read_text())))
    jobs = materialize_paired_job_configs(
        config.experiment,
        config.resources,
        FakeVgbRuntime(),
        group_id="skills_off",
        output_root=tmp_path,
    )
    assert list(jobs.groups) == ["skills_off"]
    native = jobs.groups["skills_off"].job_config.agents[0]
    custom_codex = agent == "codex" and config.experiment.agent.codex_config is not None
    if custom_codex:
        assert native.name is None and native.import_path == "adapters.codex:CodexAgent"
        assert native.kwargs["config"] == config.experiment.agent.codex_config
    else:
        assert native.name == agent and native.import_path is None
    assert native.model_name == model and native.kwargs["reasoning_effort"] == "high"
    assert native.skills == []
    assert config.experiment.agent.max_output_tokens == 64_000
    credential_env = dict(native.env)
    if agent == "claude-code":
        assert credential_env.pop("CLAUDE_CODE_MAX_OUTPUT_TOKENS") == "64000"
    if config.experiment.agent.provider is None:
        assert credential_env == {}
    else:
        assert all(
            value.startswith("${") and value.endswith("}") for value in credential_env.values()
        )
    assert jobs.groups["skills_off"].job_config.retry.max_retries == 0


@pytest.mark.parametrize("agent", ["openclaw", "hermes"])
@pytest.mark.parametrize(
    "label,model",
    [
        ("gpt", "openai/gpt-6.1-sol"),
        ("qwen", "qwen/qwen3.8-max"),
        ("claude", "anthropic/claude-opus-5.5"),
        ("deepseek", "deepseek/deepseek-v4-pro"),
    ],
)
def test_provider_templates_materialize_selected_models_with_high_effort(
    agent, label, model, tmp_path, monkeypatch
):
    monkeypatch.setenv("OPENCLAW_SKILLS_ROOT", str(tmp_path / "not-needed"))
    monkeypatch.setenv("VGB_PYTHON", "/unused/vgb/python")
    path = Path("examples/experiments") / agent / f"vgb-{label}.config.yaml"
    config = RunConfig.model_validate(expand_required(yaml.safe_load(path.read_text())))
    jobs = materialize_paired_job_configs(
        config.experiment,
        config.resources,
        FakeVgbRuntime(),
        group_id="skills_off",
        output_root=tmp_path,
    )
    assert list(jobs.groups) == ["skills_off"]
    native = jobs.groups["skills_off"].job_config.agents[0]
    class_name = "OpenClawAgent" if agent == "openclaw" else "HermesAgent"
    assert native.import_path == f"adapters.{agent}.adapter:{class_name}"
    assert native.model_name == model
    assert native.kwargs["thinking" if agent == "openclaw" else "reasoning"] == "high"
    assert native.skills == [] and native.env == {}
