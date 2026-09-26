from __future__ import annotations

import pytest

from harbor_agent_infra.preparation.experiments import experiment_sha256, load_experiment


def test_load_experiment_resolves_required_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TEST_MODEL", "fixture-model")
    path = tmp_path / "experiment.yaml"
    path.write_text(
        """schema_version: experiment.v1
experiment_id: phase1
domain: verifier-grounded
tracks: [open_generation_rdkit]
agent:
  adapter: openclaw
  model: ${TEST_MODEL}
image:
  reference: node:24-bookworm-slim
  digest: sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e
  platform: linux/arm64
  pull_policy: if_missing
resources:
  profile: local-smoke
  config_file: local.yaml
vgb:
  package_lock: runtime-lock.json
  track: open_generation_rdkit
  task_ids: [rdkit_001_qed_max]
""",
        encoding="utf-8",
    )
    spec = load_experiment(path)
    assert spec.agent.model == "fixture-model"
    assert len(experiment_sha256(spec)) == 64


def test_load_experiment_rejects_missing_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("MISSING_MODEL", raising=False)
    path = tmp_path / "experiment.yaml"
    path.write_text("agent:\n  model: ${MISSING_MODEL}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="MISSING_MODEL"):
        load_experiment(path)
