from pathlib import Path

from harbor_agent_infra.preparation.run_config import load_run_config


def test_load_consolidated_run_config_expands_external_paths(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_SKILLS_ROOT", "/tmp/openclaw-skills")
    config = load_run_config(Path("configs/experiments/openclaw-vgb-paired.config.yaml"))

    assert config.schema_version == "harbor-run.v1"
    assert config.experiment.experiment_id == "openclaw-vgb-paired"
    assert config.resources.profiles["openclaw"].cpus == 4
    assert config.resources.profiles["openclaw"].memory_mb == 8192
    assert config.run.skills_root == "/tmp/openclaw-skills"
    assert config.task.agent_timeout_sec == 7200
    assert config.task.verifier_network_mode == "public"
