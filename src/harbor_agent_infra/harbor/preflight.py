from __future__ import annotations

from dataclasses import dataclass

from harbor.environments.docker.docker import DockerEnvironment
from harbor.environments.resource_policies import (
    validate_resource_capabilities,
    validate_resource_values,
)
from harbor.models.trial.config import ResourceMode

from harbor_agent_infra.contracts.resource_profile import ResourceProfile


@dataclass(frozen=True)
class CapabilityPreflight:
    provider: str
    cpu_limit: bool
    memory_limit: bool


def preflight_docker_resources(profile: ResourceProfile) -> CapabilityPreflight:
    """Validate the profile against Harbor's declared Docker capabilities."""
    capabilities = DockerEnvironment.resource_capabilities()
    if capabilities is None:
        raise ValueError("Harbor Docker provider did not declare resource capabilities")
    validate_resource_capabilities(
        environment_label="docker",
        resource_capabilities=capabilities,
        cpu_enforcement_policy=ResourceMode(profile.cpu_enforcement_policy),
        memory_enforcement_policy=ResourceMode(profile.memory_enforcement_policy),
    )
    if not float(profile.cpus).is_integer():
        raise ValueError("Harbor Docker override_cpus requires an integer CPU value")
    validate_resource_values(
        cpu_enforcement_policy=ResourceMode(profile.cpu_enforcement_policy),
        memory_enforcement_policy=ResourceMode(profile.memory_enforcement_policy),
        cpus=int(profile.cpus),
        memory_mb=profile.memory_mb,
    )
    return CapabilityPreflight(
        provider="docker",
        cpu_limit=capabilities.cpu_limit,
        memory_limit=capabilities.memory_limit,
    )
