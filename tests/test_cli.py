from __future__ import annotations

import json

from harbor_agent_infra.cli import _with_selected_task_names, build_parser, main
from harbor_agent_infra.contracts.experiment import ExperimentSpecV2


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


def test_run_parser_accepts_failed_record_rerun() -> None:
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
            "--rerun-failed",
            "old/results.json",
        ]
    )
    assert args.rerun_failed.name == "results.json"


def test_run_parser_accepts_explicit_task_rerun() -> None:
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
            "--task-name",
            "open_generation_rdkit__rdkit_001_qed_max",
            "--job-name-suffix",
            "rerun-batch-1",
        ]
    )
    assert args.task_name == ["open_generation_rdkit__rdkit_001_qed_max"]
    assert args.job_name_suffix == "rerun-batch-1"


def test_selected_failed_tasks_filter_configured_cases(tmp_path) -> None:
    spec = ExperimentSpecV2.model_validate(
        {
            "schema_version": "experiment.v2",
            "experiment_id": "test",
            "domain": "verifier-grounded",
            "benchmark": {
                "package_lock": "runtime-lock.json",
                "cases": [
                    {"track": "open_generation_rdkit", "task_ids": ["rdkit_001_qed_max"]},
                    {"track": "open_generation_xtb", "task_ids": ["xtb_001_gap_window"]},
                ],
            },
            "groups": [
                {"id": "skills_on", "label": "on", "skills_enabled": True,
                 "skill_allowlist_ref": str(tmp_path / "allowlist.json")},
                {"id": "skills_off", "label": "off", "skills_enabled": False},
            ],
            "agent": {"adapter": "openclaw", "model": "test"},
            "image": {
                "reference": "image",
                "digest": "sha256:" + "a" * 64,
                "platform": "linux/arm64",
                "pull_policy": "if_missing",
            },
            "resources": {"profile": "test", "config_file": "test.yaml"},
        }
    )
    selected = _with_selected_task_names(
        spec, frozenset({"open_generation_xtb__xtb_001_gap_window"})
    )
    assert [case.task_ids for case in selected.benchmark.cases] == [["xtb_001_gap_window"]]


def test_materialize_command_writes_job_snapshot(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENCLAW_MODEL", "fixture-model")
    monkeypatch.setenv("HARBOR_AGENT_BASE_IMAGE_REFERENCE", "hai-base-env")
    monkeypatch.setenv(
        "HARBOR_AGENT_BASE_IMAGE_DIGEST",
        "sha256:e3faddf399e7898938d5e3f76c8aa8455d69d571849aa2940da8ed6e613b5c68",
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
        "@sha256:e3faddf399e7898938d5e3f76c8aa8455d69d571849aa2940da8ed6e613b5c68"
    )
    assert payload["agent_python"]["package_install_policy"] == "agent-managed"
    assert payload["agent_chemistry"]["xtb_version"] == "6.5.1"


def test_materialize_v2_command_writes_paired_job_snapshot(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENCLAW_MODEL", "fixture-model")
    monkeypatch.setenv("HARBOR_AGENT_BASE_IMAGE_REFERENCE", "hai-base-env")
    monkeypatch.setenv(
        "HARBOR_AGENT_BASE_IMAGE_DIGEST",
        "sha256:e3faddf399e7898938d5e3f76c8aa8455d69d571849aa2940da8ed6e613b5c68",
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


def test_view_command_delegates_to_harbor_viewer(monkeypatch, tmp_path) -> None:
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    calls = []
    monkeypatch.setattr(
        "harbor_agent_infra.cli._run_harbor_viewer",
        lambda path, *, port, host: calls.append((path, port, host)),
    )
    assert main(["view", "--jobs-dir", str(jobs_dir), "--port", "8123"]) == 0
    assert calls == [(jobs_dir, "8123", "127.0.0.1")]
