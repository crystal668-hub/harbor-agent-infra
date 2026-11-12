"""Run artifact categorization for formal vs temporary experiments."""

from __future__ import annotations

from enum import StrEnum


class RunCategory(StrEnum):
    """Category of experiment run artifacts."""

    FORMAL = "formal"
    """Official experiments following frozen protocol, for final analysis."""

    TEMPORARY = "temporary"
    """Temporary tests, smoke runs, debugging, and historical data."""

    def __str__(self) -> str:
        return self.value
