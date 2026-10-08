from __future__ import annotations

import pytest

from harbor_agent_infra.preparation.experiments import experiment_sha256, load_experiment
from harbor_agent_infra.preparation.skill_inventory import (
    load_skill_allowlist,
    skill_allowlist_sha256,
    skill_directory_sha256,
)


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
  reference: hai-base-env
  digest: sha256:e3faddf399e7898938d5e3f76c8aa8455d69d571849aa2940da8ed6e613b5c68
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


def test_load_experiment_v2_requires_paired_skill_groups(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TEST_MODEL", "fixture-model")
    path = tmp_path / "experiment.yaml"
    path.write_text(
        """schema_version: experiment.v2
experiment_id: paired
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
    skill_allowlist_ref: allowlist.json
  - id: skills_off
    label: "off"
    skills_enabled: false
    skill_allowlist_ref: null
agent:
  adapter: openclaw
  model: ${TEST_MODEL}
image:
  reference: hai-base-env
  digest: sha256:e3faddf399e7898938d5e3f76c8aa8455d69d571849aa2940da8ed6e613b5c68
  platform: linux/arm64
  pull_policy: if_missing
resources:
  profile: local-smoke
  config_file: local.yaml
""",
        encoding="utf-8",
    )
    spec = load_experiment(path)
    assert spec.schema_version == "experiment.v2"
    assert {group.id for group in spec.groups} == {"skills_on", "skills_off"}
    assert len(experiment_sha256(spec)) == 64


def test_v2_rejects_duplicate_tasks_and_invalid_group_mode(tmp_path) -> None:
    path = tmp_path / "experiment.yaml"
    path.write_text(
        """schema_version: experiment.v2
experiment_id: invalid
domain: verifier-grounded
benchmark:
  package_lock: runtime-lock.json
  cases:
    - track: open_generation_rdkit
      task_ids: [rdkit_001_qed_max]
    - track: open_generation_xtb
      task_ids: [rdkit_001_qed_max]
groups:
  - id: skills_on
    label: "on"
    skills_enabled: false
    skill_allowlist_ref: allowlist.json
  - id: skills_off
    label: "off"
    skills_enabled: false
    skill_allowlist_ref: null
agent: {adapter: openclaw, model: fixture}
image:
  reference: hai-base-env
  digest: sha256:e3faddf399e7898938d5e3f76c8aa8455d69d571849aa2940da8ed6e613b5c68
  platform: linux/arm64
  pull_policy: if_missing
resources: {profile: local-smoke, config_file: local.yaml}
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="task_ids|skills_enabled"):
        load_experiment(path)


def test_skill_allowlist_hash_is_stable(tmp_path) -> None:
    path = tmp_path / "allowlist.json"
    path.write_text(
        '{"schema_version":"skill-allowlist.v1","skills":["rdkit","ase"]}\n',
        encoding="utf-8",
    )
    allowlist = load_skill_allowlist(path)
    assert allowlist.skills == ["rdkit", "ase"]
    assert len(skill_allowlist_sha256(allowlist)) == 64


def test_skill_directory_hash_tracks_content_and_names(tmp_path) -> None:
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("first", encoding="utf-8")
    first = skill_directory_sha256(skill)
    (skill / "SKILL.md").write_text("second", encoding="utf-8")
    assert skill_directory_sha256(skill) != first
    (skill / "SKILL.md").rename(skill / "README.md")
    assert skill_directory_sha256(skill) != first
