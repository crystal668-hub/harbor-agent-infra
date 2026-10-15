from __future__ import annotations

import json
from pathlib import Path

import pytest

from harbor_agent_infra.contracts.experiment import AgentSpec, ExperimentSpec
from harbor_agent_infra.contracts.resource_profile import ResourceConfig
from harbor_agent_infra.harbor.job_config import materialize_job_config
from harbor_agent_infra.harness_runner import harness_runner_for
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock

NAMES = ("openclaw", "hermes", "codex", "claude-code")


def candidate_lock(tmp_path):
    raw = json.loads(Path("runtime-lock.json").read_text())
    versions = load_runtime_lock(Path("runtime-lock.json"))
    raw["harness_images"] = {
        name: {
            "reference": f"test/{name}", "digest": "sha256:" + str(i + 1) * 64,
            "platform": "linux/arm64", "version": versions.harness_version(name),
            "manifest_sha256": "a" * 64,
            **({"source_commit": versions.hermes.source_commit} if name == "hermes" else {}),
        }
        for i, name in enumerate(NAMES)
    }
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(raw))
    return path, raw


@pytest.mark.parametrize("name", NAMES)
def test_explicit_preinstalled_mode_selects_one_locked_image(tmp_path, name):
    path, _ = candidate_lock(tmp_path)
    lock = load_runtime_lock(path)
    agent = AgentSpec(adapter=name, model="openai/fixture", installation_mode="preinstalled")
    image = lock.execution_image(name, agent.installation_mode)
    spec = ExperimentSpec.model_validate({
        "schema_version": "experiment.v1", "experiment_id": "preinstalled-contract",
        "domain": "verifier-grounded", "tracks": ["open_generation_rdkit"],
        "agent": agent.model_dump(),
        "image": {"reference": image.reference, "digest": image.digest,
                  "platform": image.platform, "pull_policy": "never"},
        "resources": {"profile": "local", "config_file": "local.yaml"},
        "vgb": {"package_lock": str(path), "track": "open_generation_rdkit",
                "task_ids": ["fixture"]},
    })
    resources = ResourceConfig.model_validate({
        "schema_version": "resource-profiles.v1",
        "capacity": {"source": "harbor-job", "max_concurrent_trials": 1},
        "profiles": {"local": {"cpus": 1, "memory_mb": 512}},
    })
    materialized = materialize_job_config(spec, resources)
    config = materialized.job_config.agents[0]
    assert config.kwargs["preinstalled"]["manifest_sha256"] == image.manifest_sha256
    assert config.kwargs["preinstalled"]["image"] == image.immutable_reference
    assert config.kwargs["version"] == (
        lock.hermes.source_tag if name == "hermes" else lock.harness_version(name)
    )
    assert config.import_path.startswith("adapters.")
    assert materialized.agent_execution_image == image.immutable_reference
    assert materialized.agent_base_image == lock.agent_base_image.immutable_reference
    wrong = spec.model_copy(update={"image": spec.image.model_copy(update={
        "digest": lock.agent_base_image.digest,
    })})
    with pytest.raises(ValueError, match="digest"):
        materialize_job_config(wrong, resources)


@pytest.mark.parametrize("field,value", [
    ("version", "0.0.0"), ("digest", "latest"), ("platform", "linux/amd64"),
    ("manifest_sha256", ""), ("source_commit", "f" * 40), ("unexpected", True),
])
def test_image_lock_rejects_identity_drift(tmp_path, field, value):
    path, raw = candidate_lock(tmp_path)
    raw["harness_images"]["hermes"][field] = value
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="harness image"):
        load_runtime_lock(path)


def test_legacy_serialization_and_missing_image_are_explicit():
    lock = load_runtime_lock(Path("runtime-lock.json"))
    agent = AgentSpec(adapter="codex", model="fixture")
    assert "installation_mode" not in agent.model_dump()
    assert lock.execution_image("codex") == lock.agent_base_image
    assert "preinstalled" not in harness_runner_for("codex").build_agent_config(agent, lock).kwargs
    with pytest.raises(ValueError, match="missing preinstalled"):
        harness_runner_for("codex").build_agent_config(
            agent.model_copy(update={"installation_mode": "preinstalled"}), lock
        )


def test_preinstalled_hermes_forwards_configured_anthropic_endpoint(tmp_path, monkeypatch):
    from harbor.utils.env import resolve_env_vars

    path, _ = candidate_lock(tmp_path)
    lock = load_runtime_lock(path)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://selected.example")
    spec = AgentSpec(adapter="hermes", model="anthropic/claude-opus-5.5")
    legacy = harness_runner_for("hermes").build_agent_config(spec, lock)
    assert legacy.env == {}
    selected = harness_runner_for("hermes").build_agent_config(
        spec.model_copy(update={"installation_mode": "preinstalled"}), lock,
    )
    assert resolve_env_vars(selected.env)["ANTHROPIC_BASE_URL"] == "https://selected.example"
    assert "selected.example" not in selected.model_dump_json()


def test_candidate_config_preserves_source_and_only_changes_new_run(tmp_path, monkeypatch):
    import yaml

    from scripts.prepare_preinstalled_run import prepare

    monkeypatch.setenv("OPENCLAW_SKILLS_ROOT", "/fixture/skills")
    monkeypatch.setenv("VGB_PYTHON", "/fixture/vgb/python")
    path, _ = candidate_lock(tmp_path)
    source = Path("examples/experiments/codex/vgb-gpt.config.yaml")
    original = source.read_bytes()
    output = tmp_path / "candidate.yaml"
    run = tmp_path / "new-run"
    result = prepare(source, path, output, run)
    created = yaml.safe_load(output.read_text())
    assert source.read_bytes() == original
    assert not run.exists()
    assert result["group"] == "skills_off"
    assert created["experiment"]["agent"]["installation_mode"] == "preinstalled"
    assert created["experiment"]["agent"]["base_url_env"] == "CODEX_GPT_BASE_URL"
    assert created["run"]["vgb_python"] == "${VGB_PYTHON}"
    assert [group["id"] for group in created["experiment"]["groups"]] == ["skills_off"]
    with pytest.raises(ValueError, match="must be new"):
        prepare(source, path, output, run)


@pytest.mark.parametrize("group_ids", [["skills_off"], ["skills_on"], ["skills_off", "skills_off"]])
def test_single_group_candidate_schema_preserves_skills_off_default(monkeypatch, group_ids):
    import yaml
    from pydantic import ValidationError

    from harbor_agent_infra.contracts.run import RunConfig
    from harbor_agent_infra.preparation.experiments import expand_required

    monkeypatch.setenv("OPENCLAW_SKILLS_ROOT", "/fixture/skills")
    monkeypatch.setenv("VGB_PYTHON", "/fixture/vgb/python")
    payload = yaml.safe_load(Path("examples/experiments/codex/vgb-gpt.config.yaml").read_text())
    groups = {group["id"]: group for group in payload["experiment"]["groups"]}
    payload["experiment"]["groups"] = [groups[name] for name in group_ids]
    if group_ids == ["skills_off"]:
        assert len(RunConfig.model_validate(expand_required(payload)).experiment.groups) == 1
    else:
        with pytest.raises(ValidationError, match="groups must contain"):
            RunConfig.model_validate(expand_required(payload))


def test_acceptance_matrix_is_finite_and_freezes_all_tracks_and_routes(tmp_path, monkeypatch):
    from scripts.verify_preinstalled_matrix import ACCEPTANCE_PREFIX, CASES, PROVIDERS, matrix

    monkeypatch.setenv("OPENCLAW_SKILLS_ROOT", "/fixture/skills")
    monkeypatch.setenv("VGB_PYTHON", "/fixture/vgb/python")
    path, _ = candidate_lock(tmp_path)
    entries = matrix(path, Path("examples/experiments"), tmp_path / "matrix")
    assert len(entries) == 16
    assert all(entry["instruction_prefix"] == ACCEPTANCE_PREFIX for entry in entries)
    for name in NAMES:
        selected = [entry for entry in entries if entry["harness"] == name]
        assert {entry["provider"] for entry in selected} == set(PROVIDERS)
        assert {entry["track"] for entry in selected} == {track for track, _ in CASES}
        assert all(entry["config"]["experiment"]["agent"]["installation_mode"] == "preinstalled"
                   for entry in selected)
        assert all(entry["config"]["experiment"]["retry"]["max_retries"] == 0
                   for entry in selected)


def test_acceptance_cancellation_persists_terminal_status_and_stops_dispatch(tmp_path, monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock

    from scripts import verify_preinstalled_matrix as module

    monkeypatch.setenv("OPENCLAW_SKILLS_ROOT", "/fixture/skills")
    monkeypatch.setenv("VGB_PYTHON", "/fixture/vgb/python")
    path, _ = candidate_lock(tmp_path)
    execute = AsyncMock(side_effect=asyncio.CancelledError())
    monkeypatch.setattr(module, "require_idle_docker", lambda: None)
    monkeypatch.setattr(module.VgbRuntime, "from_executable", lambda _: None)
    monkeypatch.setattr(module, "run_group_jobs", execute)
    output = tmp_path / "cancelled-matrix"
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(module.run_matrix(path, Path("examples/experiments"), output))
    report = json.loads((output / "report.json").read_text())
    assert report["status"] == "cancelled"
    assert len(report["entries"]) == 1
    assert report["entries"][0]["status"] == "cancelled"
    assert execute.await_count == 1


def test_vgb_tasks_and_chemistry_preflight_resolve_the_execution_image(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from test_chemistry import evidence
    from test_task_materializer import FakeVgbRuntime, _resources, _spec

    from harbor_agent_infra.harbor.job_config import materialize_paired_job_configs
    from integrations.vgb import chemistry

    path, _ = candidate_lock(tmp_path)
    lock = load_runtime_lock(path)
    selected = lock.harness_images["openclaw"]
    spec = _spec(tmp_path)
    spec = spec.model_copy(update={
        "agent": spec.agent.model_copy(update={"installation_mode": "preinstalled"}),
        "image": spec.image.model_copy(update={
            "reference": selected.reference, "digest": selected.digest,
        }),
        "benchmark": spec.benchmark.model_copy(update={"package_lock": str(path)}),
    })
    materialized = materialize_paired_job_configs(
        spec, _resources(), FakeVgbRuntime(), output_root=tmp_path / "materialized",
        group_id="skills_off",
    )
    task_toml = (materialized.tasks[0].path / "task.toml").read_text()
    assert selected.immutable_reference in task_toml
    host, _ = evidence()
    monkeypatch.setattr(chemistry, "runtime_settings", lambda _: (tmp_path, path))
    monkeypatch.setattr(chemistry, "probe_host", lambda *args: host)
    inspected = []

    def inspect(reference, **kwargs):
        inspected.append((reference, kwargs["digest"]))
        return SimpleNamespace(to_dict=lambda: {"reference": reference})

    def run(command, **kwargs):
        assert selected.immutable_reference in command
        return SimpleNamespace(stdout=json.dumps(host))

    monkeypatch.setattr("harbor_agent_infra.preparation.image_manager.inspect_image", inspect)
    monkeypatch.setattr(chemistry.subprocess, "run", run)
    chemistry.preflight_chemistry(
        SimpleNamespace(python_executable=tmp_path / "python"), path,
        output_path=tmp_path / "chemistry-report.json", agent_name="openclaw",
        installation_mode="preinstalled",
    )
    assert inspected == [(selected.reference, selected.digest)]
