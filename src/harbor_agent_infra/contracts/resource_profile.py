from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt

EnforcementPolicy = Literal["auto", "limit", "ignore"]


class ResourceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cpus: PositiveFloat
    memory_mb: PositiveInt
    cpu_enforcement_policy: EnforcementPolicy = "auto"
    memory_enforcement_policy: EnforcementPolicy = "auto"


class ResourceCapacity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal["harbor-job"]
    max_concurrent_trials: PositiveInt


class ResourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["resource-profiles.v1"]
    capacity: ResourceCapacity
    profiles: dict[str, ResourceProfile] = Field(min_length=1)
