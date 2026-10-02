from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat

from harbor_agent_infra.contracts.experiment import ExperimentSpecV2
from harbor_agent_infra.contracts.resource_profile import ResourceConfig

NetworkMode = Literal["no-network", "allowlist", "public"]


class RunPaths(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    output_dir: str = Field(min_length=1)
    skills_root: str = Field(min_length=1)
    vgb_python: str = Field(min_length=1)


class DockerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    delete_containers: bool = True


class TaskSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_timeout_sec: PositiveFloat = 900.0
    verifier_timeout_sec: PositiveFloat = 60.0
    agent_network_mode: NetworkMode = "public"
    agent_allowed_hosts: list[str] = Field(default_factory=list)
    verifier_network_mode: NetworkMode = "public"
    verifier_allowed_hosts: list[str] = Field(default_factory=list)


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["harbor-run.v1"]
    run: RunPaths
    docker: DockerSettings = Field(default_factory=DockerSettings)
    task: TaskSettings = Field(default_factory=TaskSettings)
    resources: ResourceConfig
    experiment: ExperimentSpecV2
