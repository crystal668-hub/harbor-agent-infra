"""Run artifact categorization for formal vs temporary experiments."""

from __future__ import annotations

from enum import Enum


class RunCategory(str, Enum):
    """Category of experiment run artifacts."""

    FORMAL = "formal"
    """Official experiments following frozen protocol, for final analysis."""

    TEMPORARY = "temporary"
    """Temporary tests, smoke runs, debugging, and historical data."""

    def __str__(self) -> str:
        return self.value
