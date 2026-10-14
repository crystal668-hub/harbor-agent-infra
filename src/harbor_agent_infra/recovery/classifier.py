"""Automatic failure classification for recovery decisions."""

from __future__ import annotations

import re
from typing import Any

from harbor_agent_infra.contracts.failure_types import (
    KNOWN_PATTERNS,
    FailureCategory,
    FailureClassification,
)


def classify_failure(
    exception_type: str | None,
    exception_message: str | None,
    logs: str | None = None,
    exit_code: int | None = None,
    **extra_context: Any,
) -> FailureClassification:
    """Automatically classify a failure for recovery decision-making.

    Args:
        exception_type: The exception class name (e.g., "AgentTimeoutError").
        exception_message: The exception message text.
        logs: Container or agent logs (optional).
        exit_code: Process exit code (optional).
        **extra_context: Additional context for classification.

    Returns:
        FailureClassification with category, reason, and substitutability.

    Example:
        >>> classify_failure("AgentTimeoutError", "Agent exceeded 1800s limit")
        FailureClassification(
            category=FailureCategory.CAPABILITY,
            reason="Agent exceeded time limit",
            is_substitutable=False,
            evidence={'type': 'timeout'},
            confidence=1.0
        )
    """
    # Check known patterns by exception type
    if exception_type and exception_type in KNOWN_PATTERNS:
        return KNOWN_PATTERNS[exception_type]

    # Heuristic classification based on message and logs
    all_text = " ".join(
        filter(None, [exception_type or "", exception_message or "", logs or ""])
    )

    # Engineering failures
    if _contains_any(
        all_text,
        [
            "connection refused",
            "connection timeout",
            "network unreachable",
            "no route to host",
            "dns resolution failed",
        ],
    ):
        return FailureClassification(
            category=FailureCategory.ENGINEERING,
            reason="Network connectivity issue detected in logs",
            is_substitutable=True,
            evidence={"pattern": "network", "source": "heuristic"},
            confidence=0.9,
        )

    if _contains_any(
        all_text,
        [
            "out of memory",
            "oom killed",
            "cannot allocate memory",
            "memory limit exceeded",
        ],
    ):
        return FailureClassification(
            category=FailureCategory.ENGINEERING,
            reason="Out of memory error",
            is_substitutable=True,
            evidence={"pattern": "oom", "source": "heuristic"},
            confidence=0.95,
        )

    if _contains_any(
        all_text, ["disk full", "no space left", "quota exceeded", "enospc"]
    ):
        return FailureClassification(
            category=FailureCategory.ENGINEERING,
            reason="Disk space exhausted",
            is_substitutable=True,
            evidence={"pattern": "disk", "source": "heuristic"},
            confidence=0.95,
        )

    if _contains_any(
        all_text,
        [
            "manifest unknown",
            "image not found",
            "pull access denied",
            "unauthorized",
            "authentication required",
        ],
    ):
        return FailureClassification(
            category=FailureCategory.ENGINEERING,
            reason="Docker image pull or authentication failure",
            is_substitutable=True,
            evidence={"pattern": "docker_auth", "source": "heuristic"},
            confidence=0.85,
        )

    # Scoring failures
    if exception_type and "verifier" in exception_type.lower():
        return FailureClassification(
            category=FailureCategory.SCORING,
            reason="VGB verifier failure",
            is_substitutable=False,
            evidence={"type": "verifier", "source": "exception_type"},
            confidence=0.9,
        )

    if _contains_any(
        all_text, ["vgb runtime error", "verifier crashed", "scoring failed"]
    ):
        return FailureClassification(
            category=FailureCategory.SCORING,
            reason="Scoring system failure detected",
            is_substitutable=False,
            evidence={"pattern": "scoring", "source": "heuristic"},
            confidence=0.8,
        )

    # Capability failures (timeout is already handled by known patterns)
    if exit_code in (137, 143):  # SIGKILL or SIGTERM
        # Could be timeout or OOM - need more context
        if "timeout" in all_text.lower():
            return FailureClassification(
                category=FailureCategory.CAPABILITY,
                reason="Process terminated due to timeout",
                is_substitutable=False,
                evidence={"exit_code": exit_code, "source": "heuristic"},
                confidence=0.85,
            )
        # Ambiguous - default to engineering with lower confidence
        return FailureClassification(
            category=FailureCategory.ENGINEERING,
            reason="Process killed (ambiguous cause)",
            is_substitutable=True,
            evidence={"exit_code": exit_code, "source": "heuristic"},
            confidence=0.6,
        )

    # Default: treat as capability failure with low confidence
    # Requires manual review
    return FailureClassification(
        category=FailureCategory.CAPABILITY,
        reason=f"Unclassified failure: {exception_type or 'unknown'}",
        is_substitutable=False,
        evidence={
            "exception_type": exception_type,
            "exception_message": exception_message,
            "exit_code": exit_code,
            "source": "default",
        },
        confidence=0.3,
    )


def _contains_any(text: str, patterns: list[str]) -> bool:
    """Check if text contains any of the patterns (case-insensitive)."""
    text_lower = text.lower()
    return any(pattern.lower() in text_lower for pattern in patterns)
