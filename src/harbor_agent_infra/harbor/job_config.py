from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harbor import JobConfig, RetryConfig
from harbor.models.environment_type import EnvironmentType
from harbor.models.task.config import TaskConfig as HarborTaskConfig
from harbor.models.task.verifier_mode import resolve_task_verifier_mode
from harbor.models.trial.config import AgentConfig, EnvironmentConfig, TaskConfig, VerifierConfig
from harbor.trial.network_policy import resolve_trial_network_plan

from harbor_agent_infra.contracts.experiment import (
    ExperimentGroupSpec,
    ExperimentSpec,
    ExperimentSpecV2,
)
from harbor_agent_infra.contracts.resource_profile import ResourceConfig
from harbor_agent_infra.harbor.preflight import CapabilityPreflight, preflight_docker_resources
from harbor_agent_infra.harbor.task_materializer import (
    TaskRuntimeSettings,
    materialize_vgb_tasks,
)
from harbor_agent_infra.preparation.experiments import experiment_sha256
from harbor_agent_infra.preparation.resource_profiles import config_sha256, select_profile
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock
from harbor_agent_infra.preparation.skill_inventory import (
    load_skill_allowlist,
    skill_allowlist_sha256,
    skill_directory_sha256,
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
    skill_allowlist_path: str | None = None
    skill_allowlist_file_sha256: str | None = None
    skills_root: str | None = None
    injected_skills: tuple[dict[str, str], ...] = ()
    network_policies: tuple[dict[str, object], ...] = ()
    agent_python: dict[str, object] | None = None
    agent_chemistry: dict[str, object] | None = None


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
        agent_python={
            "python": {
                "command": lock.agent_python.python_command,
                "alias": lock.agent_python.python_alias,
                "version": lock.agent_python.python_version,
            },
            "pip": {
                "command": lock.agent_python.pip_command,
                "alias": lock.agent_python.pip_alias,
                "version": lock.agent_python.pip_version,
            },
            "package_install_policy": lock.agent_python.package_install_policy,
            "preinstalled_packages": list(lock.agent_python.preinstalled_packages),
        },
        agent_chemistry={
            "rdkit_version": lock.agent_chemistry.rdkit_version,
            "rdkit_source": lock.agent_chemistry.rdkit_source,
            "rdkit_wheel_sha256": lock.agent_chemistry.rdkit_wheel_sha256,
            "numpy_version": lock.agent_chemistry.numpy_version,
            "pillow_version": lock.agent_chemistry.pillow_version,
            "xtb_version": lock.agent_chemistry.xtb_version,
            "xtb_package": lock.agent_chemistry.xtb_package,
            "xtb_source": lock.agent_chemistry.xtb_source,
        },
    )


def materialize_group_job_config(
    spec: ExperimentSpecV2,
    group: ExperimentGroupSpec,
    resource_config: ResourceConfig,
    *,
    tasks: tuple[TaskConfig, ...],
    output_root: Path,
    skills_root: Path | None = None,
    delete_containers: bool = True,
) -> MaterializedJob:
    """Project one paired experiment group into a native Harbor JobConfig."""
    if not tasks:
        raise ValueError("paired group requires at least one Harbor task")
    profile = select_profile(resource_config, spec.resources.profile)
    lock = _locked_image(spec)
    preflight = preflight_docker_resources(profile)

    skills: list[str] = []
    allowlist_digest = None
    allowlist_path = None
    allowlist_file_digest = None
    injected_skills: tuple[dict[str, str], ...] = ()
    group_allowlist_ref = group.skill_allowlist_ref
    if group.skills_enabled:
        if skills_root is None:
            raise ValueError("skills_on requires a skills_root directory")
        if group_allowlist_ref is None:
            raise ValueError("skills_on requires skill_allowlist_ref")
        allowlist = load_skill_allowlist(Path(group_allowlist_ref))
        allowlist_digest = skill_allowlist_sha256(allowlist)
        allowlist_path = str(Path(group_allowlist_ref).resolve())
        import hashlib

        allowlist_file_digest = hashlib.sha256(Path(group_allowlist_ref).read_bytes()).hexdigest()
        missing = [name for name in allowlist.skills if not (skills_root / name).is_dir()]
        if missing:
            raise ValueError(f"skill allowlist contains missing directories: {missing}")
        injected_skills = tuple(
            {
                "name": name,
                "directory": str((skills_root / name).resolve()),
                "content_sha256": skill_directory_sha256(skills_root / name),
            }
            for name in allowlist.skills
        )
        skills = [item["directory"] for item in injected_skills]

    job_config = JobConfig(
        job_name=f"{spec.experiment_id}-{group.id}",
        jobs_dir=output_root / "jobs",
        n_attempts=spec.retry.n_attempts,
        n_concurrent_trials=resource_config.capacity.max_concurrent_trials,
        quiet=True,
        retry=RetryConfig(max_retries=spec.retry.max_retries),
        environment=EnvironmentConfig(
            type=EnvironmentType.DOCKER,
            delete=delete_containers,
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
                kwargs={
                    "version": lock.openclaw.version,
                    "thinking": spec.agent.thinking,
                    "session_to_trajectory": True,
                },
            )
        ],
        verifier=VerifierConfig(import_path="adapters.vgb_verifier:VgbVerifier"),
        tasks=list(tasks),
    )
    network_policies = []
    for task in tasks:
        task_path = Path(task.path)
        task_config = HarborTaskConfig.model_validate_toml(
            (task_path / "task.toml").read_text(encoding="utf-8")
        )
        plan = resolve_trial_network_plan(
            task_config,
            job_config.agents[0],
            job_config.environment,
            None,
            verifier_mode=resolve_task_verifier_mode(task_config),
        )
        network_policies.append(
            {
                "task_name": task_path.name,
                "agent": plan.agent_phase.model_dump(mode="json"),
                "verifier": plan.verifier_phase.model_dump(mode="json"),
            }
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
        skill_allowlist_path=allowlist_path,
        skill_allowlist_file_sha256=allowlist_file_digest,
        skills_root=str(skills_root.resolve()) if group.skills_enabled else None,
        injected_skills=injected_skills,
        network_policies=tuple(network_policies),
        agent_python={
            "python": {
                "command": lock.agent_python.python_command,
                "alias": lock.agent_python.python_alias,
                "version": lock.agent_python.python_version,
            },
            "pip": {
                "command": lock.agent_python.pip_command,
                "alias": lock.agent_python.pip_alias,
                "version": lock.agent_python.pip_version,
            },
            "package_install_policy": lock.agent_python.package_install_policy,
            "preinstalled_packages": list(lock.agent_python.preinstalled_packages),
        },
        agent_chemistry={
            "rdkit_version": lock.agent_chemistry.rdkit_version,
            "rdkit_source": lock.agent_chemistry.rdkit_source,
            "rdkit_wheel_sha256": lock.agent_chemistry.rdkit_wheel_sha256,
            "numpy_version": lock.agent_chemistry.numpy_version,
            "pillow_version": lock.agent_chemistry.pillow_version,
            "xtb_version": lock.agent_chemistry.xtb_version,
            "xtb_package": lock.agent_chemistry.xtb_package,
            "xtb_source": lock.agent_chemistry.xtb_source,
        },
    )


def materialize_paired_job_configs(
    spec: ExperimentSpecV2,
    resource_config: ResourceConfig,
    runtime: VgbRuntime,
    *,
    output_root: Path,
    skills_root: Path | None = None,
    task_settings: TaskRuntimeSettings | None = None,
    delete_containers: bool = True,
) -> MaterializedPairedJobs:
    """Materialize one task set and one native JobConfig per experiment group."""
    lock = _locked_image(spec)
    tasks = materialize_vgb_tasks(
        runtime,
        spec,
        output_root=output_root,
        image=lock.agent_base_image.immutable_reference,
        task_settings=task_settings,
    )
    groups = {
        group.id: materialize_group_job_config(
            spec,
            group,
            resource_config,
            tasks=tasks,
            output_root=output_root,
            skills_root=skills_root,
            delete_containers=delete_containers,
        )
        for group in spec.groups
    }
    return MaterializedPairedJobs(tasks=tasks, groups=groups)
