from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from harbor_agent_infra.cli import build_parser, main


class _FakeVgbRuntime:
    def metadata(self) -> dict[str, object]:
        return {"tracks": ["open_generation_rdkit"]}

    def prompts(self, track: str) -> list[dict[str, object]]:
        assert track == "open_generation_rdkit"
        return [{"task_id": "rdkit_001_qed_max", "prompt": "Make a molecule."}]


def test_run_parser_accepts_single_group() -> None:
    args = build_parser().parse_args(
        [
            "run",
            "--experiment",
            "experiment.yaml",
            "--resource-config",
            "resources.yaml",
            "--output-dir",
            "run-artifacts/single",
            "--group",
            "skills_off",
        ]
    )
    assert args.group == "skills_off"


def test_run_options_are_limited_to_standard_experiment_inputs():
    parser = build_parser()
    subcommands = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    options = {option for action in subcommands.choices["run"]._actions
               for option in action.option_strings}
    assert options == {
        "-h", "--help", "--config", "--experiment", "--resource-config",
        "--output-dir", "--skills-root", "--group", "--formal-repeat",
        "--formal-provider", "--formal-root",
    }


def test_unknown_run_operation_is_rejected_before_config_or_artifact_access(monkeypatch, tmp_path):
    config = Mock(side_effect=AssertionError("configuration must not be loaded"))
    monkeypatch.setattr("harbor_agent_infra.cli.load_run_config", config)
    artifact = tmp_path / "results.json"
    artifact.write_text("original evidence")
    with pytest.raises(SystemExit) as error:
        main(["run", "--config", "fixture.yaml", "--output-dir", str(tmp_path),
              "--unsupported-operation"])
    assert error.value.code == 2
    config.assert_not_called()
    assert artifact.read_text() == "original evidence"








def test_materialize_command_writes_job_snapshot(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENCLAW_MODEL", "fixture-model")
    monkeypatch.setenv("HARBOR_AGENT_BASE_IMAGE_REFERENCE", "hai-base-env")
    monkeypatch.setenv(
        "HARBOR_AGENT_BASE_IMAGE_DIGEST",
        "sha256:f40ae2b67be7805ff7e59f47f5f9b20d8a9569c64b93c51930ef03082517f936",
    )
    monkeypatch.setenv("RESOURCE_PROFILE", "local-smoke")
    monkeypatch.setenv("RESOURCE_PROFILE_FILE", "local.yaml")
    experiment = tmp_path / "experiment.yaml"
    experiment.write_text(
        """schema_version: experiment.v1
experiment_id: cli-smoke
domain: verifier-grounded
tracks: [open_generation_rdkit]
agent:
  adapter: openclaw
  model: ${OPENCLAW_MODEL}
image:
  reference: ${HARBOR_AGENT_BASE_IMAGE_REFERENCE}
  digest: ${HARBOR_AGENT_BASE_IMAGE_DIGEST}
  platform: linux/arm64
  pull_policy: if_missing
resources:
  profile: ${RESOURCE_PROFILE}
  config_file: ${RESOURCE_PROFILE_FILE}
vgb:
  package_lock: runtime-lock.json
  track: open_generation_rdkit
  task_ids: [rdkit_001_qed_max]
""",
        encoding="utf-8",
    )
    resources = tmp_path / "resources.yaml"
    resources.write_text(
        """schema_version: resource-profiles.v1
capacity:
  source: harbor-job
  max_concurrent_trials: 1
profiles:
  local-smoke:
    cpus: 1
    memory_mb: 512
    cpu_enforcement_policy: limit
    memory_enforcement_policy: limit
""",
        encoding="utf-8",
    )
    output = tmp_path / "run" / "materialized.json"
    assert main(
        [
            "materialize",
            "--experiment",
            str(experiment),
            "--resource-config",
            str(resources),
            "--output",
            str(output),
        ]
    ) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "harbor-job-materialization.v1"
    assert payload["job_config"]["n_concurrent_trials"] == 1
    assert payload["job_config"]["environment"]["override_memory_mb"] == 512
    assert payload["job_config"]["agents"][0]["kwargs"]["version"] == "2026.6.34"
    assert payload["agent_base_image"].endswith(
        "@sha256:f40ae2b67be7805ff7e59f47f5f9b20d8a9569c64b93c51930ef03082517f936"
    )
    assert payload["agent_python"]["package_install_policy"] == "agent-managed"
    assert payload["agent_chemistry"]["xtb_version"] == "6.7.1"


def test_materialize_v2_command_writes_paired_job_snapshot(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENCLAW_MODEL", "fixture-model")
    monkeypatch.setenv("HARBOR_AGENT_BASE_IMAGE_REFERENCE", "hai-base-env")
    monkeypatch.setenv(
        "HARBOR_AGENT_BASE_IMAGE_DIGEST",
        "sha256:f40ae2b67be7805ff7e59f47f5f9b20d8a9569c64b93c51930ef03082517f936",
    )
    monkeypatch.setenv("RESOURCE_PROFILE", "local-smoke")
    monkeypatch.setenv("RESOURCE_PROFILE_FILE", "local.yaml")
    monkeypatch.setattr(
        "harbor_agent_infra.cli.VgbRuntime.from_environment",
        lambda: _FakeVgbRuntime(),
    )
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(
        '{"schema_version":"skill-allowlist.v1","skills":["rdkit"]}\n',
        encoding="utf-8",
    )
    skills_root = tmp_path / "skills"
    (skills_root / "rdkit").mkdir(parents=True)
    experiment = tmp_path / "experiment.yaml"
    experiment.write_text(
        f"""schema_version: experiment.v2
experiment_id: cli-paired
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
    skill_allowlist_ref: {allowlist}
  - id: skills_off
    label: "off"
    skills_enabled: false
    skill_allowlist_ref: null
agent:
  adapter: openclaw
  model: ${{OPENCLAW_MODEL}}
image:
  reference: ${{HARBOR_AGENT_BASE_IMAGE_REFERENCE}}
  digest: ${{HARBOR_AGENT_BASE_IMAGE_DIGEST}}
  platform: linux/arm64
  pull_policy: if_missing
resources:
  profile: ${{RESOURCE_PROFILE}}
  config_file: ${{RESOURCE_PROFILE_FILE}}
""",
        encoding="utf-8",
    )
    resources = tmp_path / "resources.yaml"
    resources.write_text(
        """schema_version: resource-profiles.v1
capacity: {source: harbor-job, max_concurrent_trials: 1}
profiles:
  local-smoke:
    cpus: 1
    memory_mb: 512
    cpu_enforcement_policy: limit
    memory_enforcement_policy: limit
""",
        encoding="utf-8",
    )
    output = tmp_path / "run" / "materialized.json"
    assert main(
        [
            "materialize",
            "--experiment",
            str(experiment),
            "--resource-config",
            str(resources),
            "--output",
            str(output),
            "--skills-root",
            str(skills_root),
        ]
    ) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "harbor-paired-materialization.v1"
    assert set(payload["groups"]) == {"skills_on", "skills_off"}
    on = payload["groups"]["skills_on"]["job_config"]
    off = payload["groups"]["skills_off"]["job_config"]
    assert on["tasks"] == off["tasks"]
    assert on["agents"][0]["skills"] == [str(skills_root / "rdkit")]
    assert off["agents"][0]["skills"] == []


def test_view_command_delegates_to_multi_run_viewer(monkeypatch, tmp_path) -> None:
    artifacts_dir = tmp_path / "run-artifacts"
    artifacts_dir.mkdir()
    calls = []
    monkeypatch.setattr(
        "harbor_agent_infra.cli._run_harbor_viewer",
        lambda path, *, port, host: calls.append((path, port, host)),
    )
    assert main(["view", "--artifacts-dir", str(artifacts_dir), "--port", "8123"]) == 0
    assert calls == [(artifacts_dir, 8123, "127.0.0.1")]


def test_view_command_defaults_to_run_artifacts_and_port_8080(monkeypatch, tmp_path) -> None:
    artifacts_dir = tmp_path / "run-artifacts"
    artifacts_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr(
        "harbor_agent_infra.cli._run_harbor_viewer",
        lambda path, *, port, host: calls.append((path, port, host)),
    )

    assert main(["view"]) == 0
    assert calls == [(Path("run-artifacts"), 8080, "127.0.0.1")]
