from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harbor import JobConfig, RetryConfig
from harbor.models.environment_type import EnvironmentType
from harbor.models.trial.config import AgentConfig, EnvironmentConfig, TaskConfig

from harbor_agent_infra.contracts.experiment import (
    ExperimentGroupSpec,
    ExperimentSpec,
    ExperimentSpecV2,
)
from harbor_agent_infra.contracts.resource_profile import ResourceConfig
from harbor_agent_infra.harbor.preflight import CapabilityPreflight, preflight_docker_resources
from harbor_agent_infra.harbor.task_materializer import materialize_vgb_tasks
from harbor_agent_infra.preparation.experiments import experiment_sha256
from harbor_agent_infra.preparation.resource_profiles import config_sha256, select_profile
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock
from harbor_agent_infra.preparation.skill_inventory import (
    load_skill_allowlist,
    skill_allowlist_sha256,
)
from integrations.vgb.runtime import VgbRuntime


@dataclass(frozen=True)
class MaterializedJob:
    job_config: JobConfig
    experiment_sha256: str
    resource_config_sha256: str
    profile_name: str
    preflight: CapabilityPreflight
    openclaw_version: str
    agent_base_image: str
    group_id: str | None = None
    skill_allowlist_sha256: str | None = None


@dataclass(frozen=True)
class MaterializedPairedJobs:
    tasks: tuple[TaskConfig, ...]
    groups: dict[str, MaterializedJob]


def _locked_image(spec: ExperimentSpec | ExperimentSpecV2):
    package_lock = (
        spec.benchmark.package_lock
        if isinstance(spec, ExperimentSpecV2)
        else spec.vgb.package_lock
    )
    lock = load_runtime_lock(Path(package_lock))
    image_reference = spec.image.reference.split("@", 1)[0]
    if image_reference != lock.agent_base_image.reference.split("@", 1)[0]:
        raise ValueError("experiment image must match the locked agent base image")
    if spec.image.digest != lock.agent_base_image.digest:
        raise ValueError("experiment image digest does not match the runtime lock")
    if spec.image.platform != lock.agent_base_image.platform:
        raise ValueError("experiment image platform does not match the runtime lock")
    return lock


def materialize_job_config(
    spec: ExperimentSpec,
    resource_config: ResourceConfig,
) -> MaterializedJob:
    """Project one validated experiment into Harbor's native JobConfig."""
    profile = select_profile(resource_config, spec.resources.profile)
    lock = _locked_image(spec)
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
                kwargs={"version": lock.openclaw.version},
            )
        ],
    )
    return MaterializedJob(
        job_config=job_config,
        experiment_sha256=experiment_sha256(spec),
        resource_config_sha256=config_sha256(resource_config),
        profile_name=spec.resources.profile,
        preflight=preflight,
        openclaw_version=lock.openclaw.version,
        agent_base_image=lock.agent_base_image.immutable_reference,
    )


def materialize_group_job_config(
    spec: ExperimentSpecV2,
    group: ExperimentGroupSpec,
    resource_config: ResourceConfig,
    *,
    tasks: tuple[TaskConfig, ...],
    output_root: Path,
    skills_root: Path | None = None,
) -> MaterializedJob:
    """Project one paired experiment group into a native Harbor JobConfig."""
    if not tasks:
        raise ValueError("paired group requires at least one Harbor task")
    profile = select_profile(resource_config, spec.resources.profile)
    lock = _locked_image(spec)
    preflight = preflight_docker_resources(profile)

    skills: list[str] = []
    allowlist_digest = None
    group_allowlist_ref = group.skill_allowlist_ref
    if group.skills_enabled:
        if skills_root is None:
            raise ValueError("skills_on requires a skills_root directory")
        if group_allowlist_ref is None:
            raise ValueError("skills_on requires skill_allowlist_ref")
        allowlist = load_skill_allowlist(Path(group_allowlist_ref))
        allowlist_digest = skill_allowlist_sha256(allowlist)
        missing = [name for name in allowlist.skills if not (skills_root / name).is_dir()]
        if missing:
            raise ValueError(f"skill allowlist contains missing directories: {missing}")
        skills = [str(skills_root / name) for name in allowlist.skills]

    job_config = JobConfig(
        job_name=f"{spec.experiment_id}-{group.id}",
        jobs_dir=output_root / "jobs",
        n_attempts=spec.retry.n_attempts,
        n_concurrent_trials=resource_config.capacity.max_concurrent_trials,
        quiet=True,
        retry=RetryConfig(max_retries=spec.retry.max_retries),
        environment=EnvironmentConfig(
            type=EnvironmentType.DOCKER,
            delete=True,
            cpu_enforcement_policy=profile.cpu_enforcement_policy,
            memory_enforcement_policy=profile.memory_enforcement_policy,
            override_cpus=int(profile.cpus),
            override_memory_mb=profile.memory_mb,
        ),
        agents=[
            AgentConfig(
                import_path="adapters.openclaw.adapter:OpenClawAgent",
                model_name=spec.agent.model,
                skills=skills,
                kwargs={"version": lock.openclaw.version, "session_to_trajectory": True},
            )
        ],
        tasks=list(tasks),
    )
    return MaterializedJob(
        job_config=job_config,
        experiment_sha256=experiment_sha256(spec),
        resource_config_sha256=config_sha256(resource_config),
        profile_name=spec.resources.profile,
        preflight=preflight,
        openclaw_version=lock.openclaw.version,
        agent_base_image=lock.agent_base_image.immutable_reference,
        group_id=group.id,
        skill_allowlist_sha256=allowlist_digest,
    )


def materialize_paired_job_configs(
    spec: ExperimentSpecV2,
    resource_config: ResourceConfig,
    runtime: VgbRuntime,
    *,
    output_root: Path,
    skills_root: Path | None = None,
) -> MaterializedPairedJobs:
    """Materialize one task set and one native JobConfig per experiment group."""
    lock = _locked_image(spec)
    tasks = materialize_vgb_tasks(
        runtime,
        spec,
        output_root=output_root,
        image=lock.agent_base_image.immutable_reference,
    )
    groups = {
        group.id: materialize_group_job_config(
            spec,
            group,
            resource_config,
            tasks=tasks,
            output_root=output_root,
            skills_root=skills_root,
        )
        for group in spec.groups
    }
    return MaterializedPairedJobs(tasks=tasks, groups=groups)
