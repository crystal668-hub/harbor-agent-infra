"""Validated campaign policy, frozen before any timeout replacement is dispatched."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TimeoutPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    repeat: int = Field(default=1, ge=1)
    source_timeout_sec: int = Field(default=7200, gt=0)
    agent_timeout_sec: int = Field(default=43200, gt=0)
    concurrency: int = Field(default=2, ge=1)
    group: Literal["skills_off"] = "skills_off"
    engineering_replacements: Literal[2] = 2
    scoring_retries: Literal[2] = 2

    @model_validator(mode="after")
    def require_extension(self):
        if self.agent_timeout_sec <= self.source_timeout_sec:
            raise ValueError("Rerun timeout must exceed the source timeout")
        return self


def timeout_label(seconds: int) -> str:
    return f"{seconds // 3600}h" if seconds % 3600 == 0 else f"{seconds}s"
