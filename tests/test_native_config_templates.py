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
        ("codex", "vgb-gpt.config.yaml", "gpt-5.6-sol"),
        ("claude-code", "vgb-claude.config.yaml", "claude-opus-5.5"),
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
    assert native.name == agent and native.import_path is None
    assert native.model_name == model and native.kwargs["reasoning_effort"] == "high"
    assert native.skills == [] and native.env == {}
    assert jobs.groups["skills_off"].job_config.retry.max_retries == 0
