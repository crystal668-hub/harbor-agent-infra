from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harbor import JobConfig, RetryConfig
from harbor.models.environment_type import EnvironmentType
from harbor.models.trial.config import AgentConfig, EnvironmentConfig

from harbor_agent_infra.contracts.experiment import ExperimentSpec
from harbor_agent_infra.contracts.resource_profile import ResourceConfig
from harbor_agent_infra.harbor.preflight import CapabilityPreflight, preflight_docker_resources
from harbor_agent_infra.preparation.experiments import experiment_sha256
from harbor_agent_infra.preparation.resource_profiles import config_sha256, select_profile


@dataclass(frozen=True)
class MaterializedJob:
    job_config: JobConfig
    experiment_sha256: str
    resource_config_sha256: str
    profile_name: str
    preflight: CapabilityPreflight


def materialize_job_config(
    spec: ExperimentSpec,
    resource_config: ResourceConfig,
) -> MaterializedJob:
    """Project one validated experiment into Harbor's native JobConfig."""
    profile = select_profile(resource_config, spec.resources.profile)
    preflight = preflight_docker_resources(profile)
    job_config = JobConfig(
        job_name=spec.experiment_id,
        jobs_dir=Path("run-artifacts") / spec.experiment_id,
        n_attempts=spec.retry.n_attempts,
        n_concurrent_trials=resource_config.capacity.max_concurrent_trials,
        retry=RetryConfig(max_retries=spec.retry.max_retries),
        environment=EnvironmentConfig(
            type=EnvironmentType.DOCKER,
            cpu_enforcement_policy=profile.cpu_enforcement_policy,
            memory_enforcement_policy=profile.memory_enforcement_policy,
            override_cpus=int(profile.cpus),
            override_memory_mb=profile.memory_mb,
        ),
        agents=[
            AgentConfig(
                import_path="adapters.openclaw.adapter:OpenClawAgent",
                model_name=spec.agent.model,
            )
        ],
    )
    return MaterializedJob(
        job_config=job_config,
        experiment_sha256=experiment_sha256(spec),
        resource_config_sha256=config_sha256(resource_config),
        profile_name=spec.resources.profile,
        preflight=preflight,
    )
