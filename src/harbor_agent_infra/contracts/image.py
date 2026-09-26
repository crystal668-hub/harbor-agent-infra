from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class ImageSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reference: str = Field(min_length=1)
    digest: str
    platform: str = Field(min_length=1)
    pull_policy: str = Field(min_length=1)

    @field_validator("digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if not _DIGEST.fullmatch(value):
            raise ValueError("digest must be sha256 followed by 64 lowercase hex characters")
        return value

    @field_validator("reference")
    @classmethod
    def reject_unresolved_reference(cls, value: str) -> str:
        if "${" in value or "}" in value:
            raise ValueError("reference must not contain an unresolved placeholder")
        return value
