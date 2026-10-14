"""Failure classification types for recovery system."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class FailureCategory(str, Enum):
    """Categories of failures for recovery decision-making.

    CAPABILITY: Agent failed due to its own limitations (timeout, bad answer, low score).
                These are valid observations and should NOT be retried.

    ENGINEERING: Infrastructure/environment failures (image pull, network, auth, OOM).
                 These are substitutable and can be retried (max 2 times).

    SCORING: VGB runtime or verifier failures (not agent failures).
             Agent output should be preserved and only re-scored.
    """

    CAPABILITY = "capability"
    ENGINEERING = "engineering"
    SCORING = "scoring"


@dataclass(frozen=True)
class FailureClassification:
    """Classification of a trial failure.

    Attributes:
        category: The failure category.
        reason: Human-readable explanation of the failure.
        is_substitutable: Whether this failure can be replaced with a retry.
        evidence: Structured evidence supporting the classification.
        confidence: Confidence level (0.0-1.0) of automatic classification.
    """

    category: FailureCategory
    reason: str
    is_substitutable: bool
    evidence: dict[str, Any]
    confidence: float = 1.0

    def __post_init__(self) -> None:
        """Validate consistency between category and substitutability."""
        if self.category == FailureCategory.CAPABILITY and self.is_substitutable:
            raise ValueError("CAPABILITY failures must not be substitutable")
        if self.category == FailureCategory.ENGINEERING and not self.is_substitutable:
            raise ValueError("ENGINEERING failures must be substitutable")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be in [0, 1], got {self.confidence}")


# Known failure patterns
KNOWN_PATTERNS: dict[str, FailureClassification] = {
    # Engineering failures
    "ImagePullError": FailureClassification(
        category=FailureCategory.ENGINEERING,
        reason="Failed to pull Docker image",
        is_substitutable=True,
        evidence={"type": "docker", "operation": "pull"},
    ),
    "NetworkError": FailureClassification(
        category=FailureCategory.ENGINEERING,
        reason="Network connectivity issue",
        is_substitutable=True,
        evidence={"type": "network"},
    ),
    "AuthenticationError": FailureClassification(
        category=FailureCategory.ENGINEERING,
        reason="Authentication failure",
        is_substitutable=True,
        evidence={"type": "auth"},
    ),
    "OutOfMemoryError": FailureClassification(
        category=FailureCategory.ENGINEERING,
        reason="Container ran out of memory",
        is_substitutable=True,
        evidence={"type": "resource", "resource": "memory"},
    ),
    "DiskFullError": FailureClassification(
        category=FailureCategory.ENGINEERING,
        reason="Disk space exhausted",
        is_substitutable=True,
        evidence={"type": "resource", "resource": "disk"},
    ),
    # Capability failures
    "AgentTimeoutError": FailureClassification(
        category=FailureCategory.CAPABILITY,
        reason="Agent exceeded time limit",
        is_substitutable=False,
        evidence={"type": "timeout"},
    ),
    "AgentError": FailureClassification(
        category=FailureCategory.CAPABILITY,
        reason="Agent encountered an internal error",
        is_substitutable=False,
        evidence={"type": "agent_error"},
    ),
    # Scoring failures
    "VerifierRuntimeError": FailureClassification(
        category=FailureCategory.SCORING,
        reason="VGB verifier runtime error",
        is_substitutable=False,  # Rescore only, don't rerun agent
        evidence={"type": "verifier_runtime"},
    ),
    "VerifierTimeoutError": FailureClassification(
        category=FailureCategory.SCORING,
        reason="VGB verifier timed out",
        is_substitutable=False,
        evidence={"type": "verifier_timeout"},
    ),
}
