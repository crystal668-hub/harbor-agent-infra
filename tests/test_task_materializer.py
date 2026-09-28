from __future__ import annotations

import json
from pathlib import Path

import pytest

from harbor_agent_infra.contracts.experiment import ExperimentSpecV2
from harbor_agent_infra.contracts.resource_profile import ResourceConfig
from harbor_agent_infra.harbor.job_config import (
    materialize_group_job_config,
    materialize_paired_job_configs,
)
from harbor_agent_infra.harbor.task_materializer import materialize_vgb_tasks, task_identity


class FakeVgbRuntime:
    def metadata(self) -> dict[str, object]:
        return {"tracks": ["open_generation_rdkit"]}

    def prompts(self, track: str) -> list[dict[str, object]]:
        assert track == "open_generation_rdkit"
        return [{"task_id": "rdkit_001_qed_max", "prompt": "Make a molecule."}]


def _spec(tmp_path: Path) -> ExperimentSpecV2:
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(
        '{"schema_version":"skill-allowlist.v1","skills":["rdkit","ase"]}\n',
        encoding="utf-8",
    )
    return ExperimentSpecV2.model_validate(
        {
            "schema_version": "experiment.v2",
            "experiment_id": "paired",
            "domain": "verifier-grounded",
            "benchmark": {
                "package_lock": "runtime-lock.json",
                "cases": [
                    {
                        "track": "open_generation_rdkit",
                        "task_ids": ["rdkit_001_qed_max"],
                    }
                ],
            },
            "groups": [
                {
                    "id": "skills_on",
                    "label": "on",
                    "skills_enabled": True,
                    "skill_allowlist_ref": str(allowlist),
                },
                {
                    "id": "skills_off",
                    "label": "off",
                    "skills_enabled": False,
                    "skill_allowlist_ref": None,
                },
            ],
            "agent": {"adapter": "openclaw", "model": "fixture-model"},
            "image": {
                "reference": "node:24-bookworm-slim",
                "digest": "sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e",
                "platform": "linux/arm64",
                "pull_policy": "if_missing",
            },
            "resources": {"profile": "local-smoke", "config_file": "local.yaml"},
        }
    )


def _resources() -> ResourceConfig:
    return ResourceConfig.model_validate(
        {
            "schema_version": "resource-profiles.v1",
            "capacity": {"source": "harbor-job", "max_concurrent_trials": 2},
            "profiles": {
                "local-smoke": {
                    "cpus": 1,
                    "memory_mb": 512,
                    "cpu_enforcement_policy": "limit",
                    "memory_enforcement_policy": "limit",
                }
            },
        }
    )


def test_materialize_vgb_tasks_writes_harbor_task(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    tasks = materialize_vgb_tasks(
        FakeVgbRuntime(),
        spec,
        output_root=tmp_path / "run",
        image="node:24-bookworm-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e",
    )
    assert len(tasks) == 1
    task_dir = Path(tasks[0].path)
    assert task_dir.name == "open_generation_rdkit__rdkit_001_qed_max"
    assert (task_dir / "instruction.md").read_text() == "Make a molecule."
    assert (task_dir / "tests/test.sh").stat().st_mode & 0o111
    assert task_identity(tasks) == (str(task_dir),)
    prompt = json.loads((task_dir / "agent-trial-input.v1.json").read_text())
    assert prompt["task_id"] == "rdkit_001_qed_max"


def test_group_job_configs_share_tasks_and_differ_only_by_skills(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    skills_root = tmp_path / "skills"
    (skills_root / "rdkit").mkdir(parents=True)
    (skills_root / "ase").mkdir()
    tasks = materialize_vgb_tasks(
        FakeVgbRuntime(),
        spec,
        output_root=tmp_path / "run",
        image="node:24-bookworm-slim",
    )
    on = materialize_group_job_config(
        spec,
        spec.groups[0],
        _resources(),
        tasks=tasks,
        output_root=tmp_path / "run",
        skills_root=skills_root,
    )
    off = materialize_group_job_config(
        spec,
        spec.groups[1],
        _resources(),
        tasks=tasks,
        output_root=tmp_path / "run",
    )
    assert [task.path for task in on.job_config.tasks] == [
        task.path for task in off.job_config.tasks
    ]
    assert on.job_config.agents[0].skills == [str(skills_root / "rdkit"), str(skills_root / "ase")]
    assert off.job_config.agents[0].skills == []
    assert on.group_id == "skills_on"
    assert on.skill_allowlist_sha256 is not None
    assert on.skill_allowlist_path == str((tmp_path / "allowlist.json").resolve())
    assert len(on.skill_allowlist_file_sha256 or "") == 64
    assert [item["name"] for item in on.injected_skills] == ["rdkit", "ase"]
    assert all(len(item["content_sha256"]) == 64 for item in on.injected_skills)
    assert off.injected_skills == ()
    assert off.skills_root is None
    assert on.job_config.job_name == "paired-skills_on"
    assert off.job_config.job_name == "paired-skills_off"
    assert on.job_config.jobs_dir == off.job_config.jobs_dir
    assert on.job_config.job_name != off.job_config.job_name
    assert on.job_config.verifier.import_path == "adapters.vgb_verifier:VgbVerifier"
    assert on.network_policies == off.network_policies
    assert on.network_policies[0]["agent"] == {
        "network_mode": "public",
        "allowed_hosts": [],
    }


def test_skills_on_rejects_missing_skill_directory(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    tasks = materialize_vgb_tasks(
        FakeVgbRuntime(), spec, output_root=tmp_path / "run", image="node:24-bookworm-slim"
    )
    with pytest.raises(ValueError, match="missing directories"):
        materialize_group_job_config(
            spec,
            spec.groups[0],
            _resources(),
            tasks=tasks,
            output_root=tmp_path / "run",
            skills_root=tmp_path / "missing-skills",
        )


def test_paired_materializer_builds_two_native_jobs(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    skills_root = tmp_path / "skills"
    (skills_root / "rdkit").mkdir(parents=True)
    (skills_root / "ase").mkdir()
    paired = materialize_paired_job_configs(
        spec,
        _resources(),
        FakeVgbRuntime(),
        output_root=tmp_path / "run",
        skills_root=skills_root,
    )
    assert set(paired.groups) == {"skills_on", "skills_off"}
    assert len(paired.tasks) == 1
    for materialized in paired.groups.values():
        reloaded = type(materialized.job_config).model_validate(
            materialized.job_config.model_dump(mode="json")
        )
        assert reloaded.job_name == materialized.job_config.job_name
