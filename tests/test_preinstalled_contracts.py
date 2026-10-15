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
    assert created["experiment"]["groups"] == yaml.safe_load(original)["experiment"]["groups"]
    with pytest.raises(ValueError, match="must be new"):
        prepare(source, path, output, run)


def test_acceptance_matrix_is_finite_and_freezes_all_tracks_and_routes(tmp_path, monkeypatch):
    from scripts.verify_preinstalled_matrix import CASES, PROVIDERS, matrix

    monkeypatch.setenv("OPENCLAW_SKILLS_ROOT", "/fixture/skills")
    monkeypatch.setenv("VGB_PYTHON", "/fixture/vgb/python")
    path, _ = candidate_lock(tmp_path)
    entries = matrix(path, Path("examples/experiments"), tmp_path / "matrix")
    assert len(entries) == 16
    for name in NAMES:
        selected = [entry for entry in entries if entry["harness"] == name]
        assert {entry["provider"] for entry in selected} == set(PROVIDERS)
        assert {entry["track"] for entry in selected} == {track for track, _ in CASES}
        assert all(entry["config"]["experiment"]["agent"]["installation_mode"] == "preinstalled"
                   for entry in selected)
        assert all(entry["config"]["experiment"]["retry"]["max_retries"] == 0
                   for entry in selected)
