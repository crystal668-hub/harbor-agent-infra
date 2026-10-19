from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator, model_validator

from harbor_agent_infra.contracts.image import ImageSpec
from integrations.vgb.release_lock import TRACKS


class AgentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter: Literal["openclaw", "hermes", "codex", "claude-code"]
    installation_mode: Literal["runtime_install", "preinstalled"] = Field(
        default="runtime_install", exclude_if=lambda value: value == "runtime_install"
    )
    model: str = Field(min_length=1)
    provider: Literal["openai", "anthropic", "qwen", "deepseek"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    codex_config: dict[str, object] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    base_url_env: str | None = Field(
        default=None, pattern=r"^[A-Z][A-Z0-9_]*$", exclude_if=lambda value: value is None
    )
    thinking: str | None = Field(default=None, min_length=1)
    reasoning: (
        Literal["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"] | None
    ) = None
    reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    max_output_tokens: int | None = Field(
        default=None, gt=0, strict=True, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def validate_thinking(self) -> AgentSpec:
        if self.provider is not None or self.base_url_env is not None:
            if self.adapter not in {"codex", "claude-code"}:
                raise ValueError(
                    "provider and base_url_env are only supported by native CLI agents"
                )
            if self.provider is None:
                raise ValueError("base_url_env requires an explicit provider")
        if self.codex_config is not None:
            self._validate_codex_config()
        if self.adapter != "openclaw" and self.thinking is not None:
            raise ValueError("thinking is only supported by the OpenClaw adapter")
        if self.adapter != "hermes" and self.reasoning is not None:
            raise ValueError("reasoning is only supported by the Hermes adapter")
        if self.adapter not in {"codex", "claude-code"} and self.reasoning_effort is not None:
            raise ValueError("reasoning_effort is only supported by Codex and Claude Code")
        return self

    def _validate_codex_config(self) -> None:
        if self.adapter != "codex":
            raise ValueError("codex_config is only supported by the Codex adapter")
        if self.provider not in {"qwen", "deepseek"}:
            raise ValueError("codex_config requires the Qwen or DeepSeek provider")
        expected_model = {
            "qwen": "qwen3.8-max",
            "deepseek": "deepseek-v4-pro",
        }[self.provider]
        if self.model != expected_model:
            raise ValueError(f"codex_config requires model={expected_model}")
        expected_endpoint = f"CODEX_{self.provider.upper()}_BASE_URL"
        if self.base_url_env != expected_endpoint:
            raise ValueError(f"codex_config requires base_url_env={expected_endpoint}")
        if self.max_output_tokens != 64_000:
            raise ValueError("codex_config requires the 64000-token output-cap bridge")
        if self.reasoning_effort != "high":
            raise ValueError("codex_config requires high reasoning effort")

        provider_id = self.codex_config.get("model_provider")
        providers = self.codex_config.get("model_providers")
        expected_provider_id = f"{self.provider}-responses"
        if provider_id != expected_provider_id:
            raise ValueError(
                f"codex_config requires model_provider={expected_provider_id}"
            )
        if not isinstance(providers, dict) or set(providers) != {provider_id}:
            raise ValueError("codex_config must define exactly the selected custom model provider")
        selected = providers[provider_id]
        expected_provider_fields = {
            "name", "env_key", "wire_api", "requires_openai_auth", "supports_websockets"
        }
        if not isinstance(selected, dict) or set(selected) != expected_provider_fields:
            raise ValueError(
                "codex_config custom provider fields do not match the supported contract"
            )
        expected_provider_name = {
            "qwen": "Qwen Responses via Harbor cap bridge",
            "deepseek": "DeepSeek Responses via Harbor cap bridge",
        }[self.provider]
        if selected.get("name") != expected_provider_name:
            raise ValueError(
                f"the selected custom provider name must be {expected_provider_name!r}"
            )
        if selected.get("wire_api") != "responses":
            raise ValueError("the selected custom provider must use wire_api=responses")
        if selected.get("requires_openai_auth") is not True:
            raise ValueError("the selected custom provider must use OpenAI API-key authentication")
        if selected.get("env_key") != "OPENAI_API_KEY":
            raise ValueError("the selected custom provider must read OPENAI_API_KEY")
        if selected.get("supports_websockets") is not False:
            raise ValueError("the selected custom provider must disable unsupported WebSockets")
        if "base_url" in selected:
            raise ValueError("omit custom provider base_url; Harbor binds the CODEX_* bridge URL")
        if "openai_base_url" in self.codex_config:
            raise ValueError("openai_base_url is supplied by Harbor from the CODEX_* bridge URL")
        if set(self.codex_config) != {"model_provider", "model_providers"}:
            raise ValueError(
                "codex_config may only select and define the custom Responses provider"
            )


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
    groups: list[ExperimentGroupSpec] = Field(min_length=1, max_length=2)
    agent: AgentSpec
    image: ImageSpec
    resources: ResourceRef
    retry: RetrySpec = Field(default_factory=RetrySpec)

    @model_validator(mode="after")
    def validate_groups(self) -> ExperimentSpecV2:
        group_ids = [group.id for group in self.groups]
        if group_ids != ["skills_off"] and (
            len(group_ids) != 2 or set(group_ids) != {"skills_on", "skills_off"}
        ):
            raise ValueError(
                "groups must contain skills_off alone or exactly skills_on and skills_off"
            )
        return self


ExperimentConfig = ExperimentSpec | ExperimentSpecV2
