from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator, model_validator

from harbor_agent_infra.contracts.image import ImageSpec
from integrations.vgb.release_lock import TRACKS


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


class BenchmarkCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    track: str = Field(min_length=1)
    task_ids: list[str] = Field(min_length=1)

    @field_validator("task_ids")
    @classmethod
    def validate_task_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("task_ids must not contain duplicates")
        if any(not task_id.strip() for task_id in value):
            raise ValueError("task_ids must not contain blank values")
        return value


class BenchmarkSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    package_lock: str = Field(min_length=1)
    cases: list[BenchmarkCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cases(self) -> BenchmarkSpec:
        unknown_tracks = sorted({case.track for case in self.cases} - set(TRACKS))
        if unknown_tracks:
            raise ValueError(f"unsupported VGB tracks: {unknown_tracks}")
        seen: set[str] = set()
        for case in self.cases:
            overlap = seen.intersection(case.task_ids)
            if overlap:
                raise ValueError(f"task_ids must be unique across cases: {sorted(overlap)}")
            seen.update(case.task_ids)
        return self


class ExperimentGroupSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Literal["skills_on", "skills_off"]
    label: str = Field(min_length=1)
    skills_enabled: bool
    skill_allowlist_ref: str | None = None

    @model_validator(mode="after")
    def validate_skill_mode(self) -> ExperimentGroupSpec:
        expected_enabled = self.id == "skills_on"
        if self.skills_enabled != expected_enabled:
            raise ValueError(f"group {self.id} has an invalid skills_enabled value")
        if self.id == "skills_on" and not self.skill_allowlist_ref:
            raise ValueError("skills_on requires skill_allowlist_ref")
        if self.id == "skills_off" and self.skill_allowlist_ref is not None:
            raise ValueError("skills_off must not define skill_allowlist_ref")
        return self


class SkillAllowlist(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["skill-allowlist.v1"]
    skills: list[str] = Field(min_length=1)

    @field_validator("skills")
    @classmethod
    def validate_skills(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("skills must not contain duplicates")
        if any(not skill.strip() for skill in value):
            raise ValueError("skills must not contain blank values")
        return value


class ExperimentSpecV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["experiment.v2"]
    experiment_id: str = Field(min_length=1)
    domain: Literal["verifier-grounded"]
    benchmark: BenchmarkSpec
    groups: list[ExperimentGroupSpec] = Field(min_length=2, max_length=2)
    agent: AgentSpec
    image: ImageSpec
    resources: ResourceRef
    retry: RetrySpec = Field(default_factory=RetrySpec)

    @model_validator(mode="after")
    def validate_groups(self) -> ExperimentSpecV2:
        group_ids = [group.id for group in self.groups]
        if set(group_ids) != {"skills_on", "skills_off"}:
            raise ValueError("groups must contain exactly skills_on and skills_off")
        return self


ExperimentConfig = ExperimentSpec | ExperimentSpecV2
