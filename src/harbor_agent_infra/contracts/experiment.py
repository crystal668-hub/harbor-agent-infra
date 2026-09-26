from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from harbor_agent_infra.contracts.image import ImageSpec


class AgentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter: Literal["openclaw"]
    model: str = Field(min_length=1)


class RetrySpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    n_attempts: PositiveInt = 1
    max_retries: int = Field(default=0, ge=0)


class ResourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: str = Field(min_length=1)
    config_file: str = Field(min_length=1)


class VgbSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    package_lock: str = Field(min_length=1)
    track: str = Field(min_length=1)
    task_ids: list[str] = Field(min_length=1)


class ExperimentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["experiment.v1"]
    experiment_id: str = Field(min_length=1)
    domain: Literal["verifier-grounded"]
    tracks: list[str] = Field(min_length=1)
    agent: AgentSpec
    image: ImageSpec
    resources: ResourceRef
    vgb: VgbSpec
    retry: RetrySpec = Field(default_factory=RetrySpec)
