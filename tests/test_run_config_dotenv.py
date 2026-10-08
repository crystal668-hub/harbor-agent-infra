from pathlib import Path

from harbor_agent_infra.preparation.run_config import load_run_config


def _write_config(path: Path) -> None:
    path.write_text(
        """schema_version: harbor-run.v1
run:
  output_dir: run-artifacts/test
  skills_root: ${OPENCLAW_SKILLS_ROOT}
  vgb_python: ${VGB_PYTHON}
resources:
  schema_version: resource-profiles.v1
  capacity:
    source: harbor-job
    max_concurrent_trials: 1
  profiles:
    local:
      cpus: 1
      memory_mb: 512
      cpu_enforcement_policy: limit
      memory_enforcement_policy: limit
experiment:
  schema_version: experiment.v2
  experiment_id: dotenv-test
  domain: verifier-grounded
  benchmark:
    package_lock: runtime-lock.json
    cases:
      - track: open_generation_rdkit
        task_ids: [rdkit_001_qed_max]
  groups:
    - id: skills_on
      label: "on"
      skills_enabled: true
      skill_allowlist_ref: configs/skills/benchmark-allowlist.v1.json
    - id: skills_off
      label: "off"
      skills_enabled: false
      skill_allowlist_ref: null
  agent:
    adapter: openclaw
    model: fixture/model
  image:
    reference: hai-base-env
    digest: sha256:e3faddf399e7898938d5e3f76c8aa8455d69d571849aa2940da8ed6e613b5c68
    platform: linux/arm64
    pull_policy: if_missing
  resources:
    profile: local
    config_file: embedded
""",
        encoding="utf-8",
    )


def test_load_run_config_reads_nearest_dotenv(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "configs" / "experiments" / "run.yaml"
    config.parent.mkdir(parents=True)
    _write_config(config)
    (tmp_path / ".env").write_text(
        "OPENCLAW_SKILLS_ROOT=/tmp/skills\nVGB_PYTHON=/tmp/vgb/bin/python\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENCLAW_SKILLS_ROOT", raising=False)
    monkeypatch.delenv("VGB_PYTHON", raising=False)

    loaded = load_run_config(config)

    assert loaded.run.skills_root == "/tmp/skills"
    assert loaded.run.vgb_python == "/tmp/vgb/bin/python"


def test_load_run_config_preserves_explicit_environment_precedence(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / "run.yaml"
    _write_config(config)
    (tmp_path / ".env").write_text(
        "OPENCLAW_SKILLS_ROOT=/tmp/from-dotenv\nVGB_PYTHON=/tmp/from-dotenv/python\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENCLAW_SKILLS_ROOT", "/tmp/from-shell")
    monkeypatch.setenv("VGB_PYTHON", "/tmp/from-shell/python")

    loaded = load_run_config(config)

    assert loaded.run.skills_root == "/tmp/from-shell"
    assert loaded.run.vgb_python == "/tmp/from-shell/python"
