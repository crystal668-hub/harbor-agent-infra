from __future__ import annotations

import pytest
from pydantic import ValidationError

from harbor_agent_infra.contracts.experiment import ExperimentSpec
from harbor_agent_infra.contracts.image import ImageSpec
from harbor_agent_infra.contracts.resource_profile import ResourceCapacity, ResourceConfig
from harbor_agent_infra.harbor.job_config import materialize_job_config
from harbor_agent_infra.harbor.preflight import preflight_docker_resources
from harbor_agent_infra.preparation.resource_profiles import (
    config_sha256,
    load_resource_config,
    select_profile,
)


def test_resource_config_loads_and_hash_changes_with_content(tmp_path) -> None:
    path = tmp_path / "resources.yaml"
    path.write_text(
        """schema_version: resource-profiles.v1
capacity:
  source: harbor-job
  max_concurrent_trials: 1
profiles:
  local-smoke:
    cpus: 1.0
    memory_mb: 512
    cpu_enforcement_policy: limit
    memory_enforcement_policy: limit
""",
        encoding="utf-8",
    )
    config = load_resource_config(path)
    assert select_profile(config, "local-smoke").memory_mb == 512
    original_hash = config_sha256(config)
    changed = config.model_copy(
        update={
            "capacity": ResourceCapacity(source="harbor-job", max_concurrent_trials=2),
        }
    )
    assert config_sha256(changed) != original_hash


def test_resource_config_rejects_unknown_fields(tmp_path) -> None:
    path = tmp_path / "resources.yaml"
    path.write_text(
        """schema_version: resource-profiles.v1
capacity:
  source: harbor-job
  max_concurrent_trials: 1
profiles:
  local-smoke:
    cpus: 1
    memory_mb: 512
    unsupported_limit: true
""",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_resource_config(path)


def test_missing_profile_fails_before_materialization(tmp_path) -> None:
    path = tmp_path / "resources.yaml"
    path.write_text(
        """schema_version: resource-profiles.v1
capacity:
  source: harbor-job
  max_concurrent_trials: 1
profiles:
  local-smoke:
    cpus: 1
    memory_mb: 512
""",
        encoding="utf-8",
    )
    config = load_resource_config(path)
    with pytest.raises(ValueError, match="resource profile not found"):
        select_profile(config, "missing")


def test_image_requires_immutable_digest() -> None:
    with pytest.raises(ValidationError):
        ImageSpec(
            reference="example/openclaw:latest",
            digest="sha256:tag",
            platform="linux/arm64",
            pull_policy="if_missing",
        )


def test_job_materializer_projects_native_harbor_fields() -> None:
    resources = ResourceConfig.model_validate(
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
    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "experiment.v1",
            "experiment_id": "phase1-smoke",
            "domain": "verifier-grounded",
            "tracks": ["open_generation_rdkit"],
            "agent": {"adapter": "openclaw", "model": "fixture-model"},
            "image": {
                "reference": "hai-base-env",
                "digest": "sha256:e3faddf399e7898938d5e3f76c8aa8455d69d571849aa2940da8ed6e613b5c68",
                "platform": "linux/arm64",
                "pull_policy": "if_missing",
            },
            "resources": {"profile": "local-smoke", "config_file": "local.yaml"},
            "vgb": {
                "package_lock": "runtime-lock.json",
                "track": "open_generation_rdkit",
                "task_ids": ["rdkit_001_qed_max"],
            },
        }
    )
    materialized = materialize_job_config(spec, resources)
    config = materialized.job_config
    assert config.n_concurrent_trials == 2
    assert config.n_attempts == 1
    assert config.retry.max_retries == 0
    assert config.environment.override_cpus == 1
    assert config.environment.override_memory_mb == 512
    assert config.environment.cpu_enforcement_policy.value == "limit"
    assert config.agents[0].import_path == "adapters.openclaw.adapter:OpenClawAgent"
    assert materialized.runner_id == "harbor_openclaw"
    assert materialized.preflight.provider == "docker"


def test_job_materializer_projects_pinned_hermes_adapter() -> None:
    resources = ResourceConfig.model_validate(
        {
            "schema_version": "resource-profiles.v1",
            "capacity": {"source": "harbor-job", "max_concurrent_trials": 1},
            "profiles": {"local": {"cpus": 4, "memory_mb": 4096}},
        }
    )
    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "experiment.v1",
            "experiment_id": "hermes-smoke",
            "domain": "verifier-grounded",
            "tracks": ["open_generation_rdkit"],
            "agent": {
                "adapter": "hermes",
                "model": "openai/fixture-model",
                "reasoning": "high",
            },
            "image": {
                "reference": "hai-base-env",
                "digest": "sha256:e3faddf399e7898938d5e3f76c8aa8455d69d571849aa2940da8ed6e613b5c68",
                "platform": "linux/arm64",
                "pull_policy": "if_missing",
            },
            "resources": {"profile": "local", "config_file": "local.yaml"},
            "vgb": {
                "package_lock": "runtime-lock.json",
                "track": "open_generation_rdkit",
                "task_ids": ["rdkit_001_qed_max"],
            },
        }
    )
    materialized = materialize_job_config(spec, resources)
    agent = materialized.job_config.agents[0]
    assert agent.import_path == "adapters.hermes.adapter:HermesAgent"
    assert agent.name is None
    assert agent.override_setup_timeout_sec == 1200
    assert agent.kwargs == {
        "version": "v0.21.6",
        "source_commit": "818c13be1dc4fd28987e1e881a9408224afd4535",
        "install_branch": "main",
        "reasoning": "high",
    }
    assert materialized.agent_name == "hermes"
    assert materialized.runner_id == "harbor_hermes"
    assert materialized.agent_version == "0.21.6"
    assert materialized.openclaw_version is None


def test_hermes_rejects_openclaw_thinking_setting() -> None:
    with pytest.raises(ValidationError, match="thinking is only supported"):
        ExperimentSpec.model_validate(
            {
                "schema_version": "experiment.v1",
                "experiment_id": "invalid-hermes",
                "domain": "verifier-grounded",
                "tracks": ["open_generation_rdkit"],
                "agent": {
                    "adapter": "hermes",
                    "model": "openai/fixture-model",
                    "thinking": "high",
                },
                "image": {
                    "reference": "hai-base-env",
                    "digest": "sha256:" + "a" * 64,
                    "platform": "linux/arm64",
                    "pull_policy": "if_missing",
                },
                "resources": {"profile": "local", "config_file": "local.yaml"},
                "vgb": {
                    "package_lock": "runtime-lock.json",
                    "track": "open_generation_rdkit",
                    "task_ids": ["rdkit_001_qed_max"],
                },
            }
        )


def test_openclaw_rejects_hermes_reasoning_setting() -> None:
    with pytest.raises(ValidationError, match="reasoning is only supported"):
        ExperimentSpec.model_validate(
            {
                "schema_version": "experiment.v1",
                "experiment_id": "invalid-openclaw",
                "domain": "verifier-grounded",
                "tracks": ["open_generation_rdkit"],
                "agent": {
                    "adapter": "openclaw",
                    "model": "openai/fixture-model",
                    "reasoning": "high",
                },
                "image": {
                    "reference": "hai-base-env",
                    "digest": "sha256:" + "a" * 64,
                    "platform": "linux/arm64",
                    "pull_policy": "if_missing",
                },
                "resources": {"profile": "local", "config_file": "local.yaml"},
                "vgb": {
                    "package_lock": "runtime-lock.json",
                    "track": "open_generation_rdkit",
                    "task_ids": ["rdkit_001_qed_max"],
                },
            }
        )


def test_docker_preflight_rejects_fractional_cpu_override() -> None:
    resources = ResourceConfig.model_validate(
        {
            "schema_version": "resource-profiles.v1",
            "capacity": {"source": "harbor-job", "max_concurrent_trials": 1},
            "profiles": {
                "fractional": {
                    "cpus": 0.5,
                    "memory_mb": 512,
                    "cpu_enforcement_policy": "limit",
                    "memory_enforcement_policy": "limit",
                }
            },
        }
    )
    with pytest.raises(ValueError, match="integer CPU"):
        preflight_docker_resources(resources.profiles["fractional"])
