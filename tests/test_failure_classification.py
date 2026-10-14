"""Tests for failure classification system."""

from __future__ import annotations

import pytest

from harbor_agent_infra.contracts.failure_types import (
    FailureCategory,
    FailureClassification,
)
from harbor_agent_infra.recovery.classifier import classify_failure


class TestFailureClassification:
    """Test the FailureClassification dataclass."""

    def test_capability_must_not_be_substitutable(self) -> None:
        """CAPABILITY failures must have is_substitutable=False."""
        with pytest.raises(ValueError, match="CAPABILITY failures must not"):
            FailureClassification(
                category=FailureCategory.CAPABILITY,
                reason="Test",
                is_substitutable=True,  # Invalid!
                evidence={},
            )

    def test_engineering_must_be_substitutable(self) -> None:
        """ENGINEERING failures must have is_substitutable=True."""
        with pytest.raises(ValueError, match="ENGINEERING failures must be"):
            FailureClassification(
                category=FailureCategory.ENGINEERING,
                reason="Test",
                is_substitutable=False,  # Invalid!
                evidence={},
            )

    def test_confidence_must_be_in_range(self) -> None:
        """Confidence must be between 0 and 1."""
        with pytest.raises(ValueError, match="Confidence must be in"):
            FailureClassification(
                category=FailureCategory.CAPABILITY,
                reason="Test",
                is_substitutable=False,
                evidence={},
                confidence=1.5,  # Invalid!
            )

    def test_valid_classification(self) -> None:
        """Test creating a valid classification."""
        fc = FailureClassification(
            category=FailureCategory.ENGINEERING,
            reason="Network error",
            is_substitutable=True,
            evidence={"type": "network"},
            confidence=0.9,
        )
        assert fc.category == FailureCategory.ENGINEERING
        assert fc.is_substitutable is True
        assert fc.confidence == 0.9


class TestClassifyFailure:
    """Test automatic failure classification."""

    # Known patterns
    def test_classify_agent_timeout(self) -> None:
        """AgentTimeoutError should be classified as CAPABILITY."""
        result = classify_failure("AgentTimeoutError", "Agent exceeded 1800s")
        assert result.category == FailureCategory.CAPABILITY
        assert result.is_substitutable is False
        assert result.confidence == 1.0

    def test_classify_image_pull_error(self) -> None:
        """ImagePullError should be classified as ENGINEERING."""
        result = classify_failure("ImagePullError", "Failed to pull image")
        assert result.category == FailureCategory.ENGINEERING
        assert result.is_substitutable is True
        assert result.confidence == 1.0

    def test_classify_verifier_runtime_error(self) -> None:
        """VerifierRuntimeError should be classified as SCORING."""
        result = classify_failure("VerifierRuntimeError", "VGB crashed")
        assert result.category == FailureCategory.SCORING
        assert result.is_substitutable is False
        assert result.confidence == 1.0

    # Heuristic classification - Network
    def test_classify_network_error_from_message(self) -> None:
        """Network errors detected in message should be ENGINEERING."""
        result = classify_failure(
            "RuntimeError",
            "Connection timeout while accessing API",
        )
        assert result.category == FailureCategory.ENGINEERING
        assert result.is_substitutable is True
        assert result.confidence == 0.9

    def test_classify_network_error_from_logs(self) -> None:
        """Network errors in logs should be detected."""
        result = classify_failure(
            "RuntimeError",
            "Failed",
            logs="Error: connection refused on port 443",
        )
        assert result.category == FailureCategory.ENGINEERING
        assert result.is_substitutable is True

    # Heuristic classification - OOM
    def test_classify_out_of_memory(self) -> None:
        """OOM errors should be classified as ENGINEERING."""
        result = classify_failure(
            "RuntimeError",
            "Container failed",
            logs="Process killed: out of memory",
        )
        assert result.category == FailureCategory.ENGINEERING
        assert result.is_substitutable is True
        assert result.confidence == 0.95

    def test_classify_oom_killed(self) -> None:
        """OOM killed should be detected."""
        result = classify_failure(None, None, logs="Container OOM killed")
        assert result.category == FailureCategory.ENGINEERING
        assert result.is_substitutable is True

    # Heuristic classification - Disk
    def test_classify_disk_full(self) -> None:
        """Disk full errors should be ENGINEERING."""
        result = classify_failure(
            "RuntimeError", "Failed to write", logs="Error: no space left on device"
        )
        assert result.category == FailureCategory.ENGINEERING
        assert result.is_substitutable is True
        assert result.confidence == 0.95

    # Heuristic classification - Docker/Auth
    def test_classify_docker_auth_failure(self) -> None:
        """Docker auth failures should be ENGINEERING."""
        result = classify_failure(
            "RuntimeError",
            "Pull access denied for image",
        )
        assert result.category == FailureCategory.ENGINEERING
        assert result.is_substitutable is True
        assert result.confidence == 0.85

    def test_classify_manifest_unknown(self) -> None:
        """Manifest unknown should be detected."""
        result = classify_failure(None, None, logs="manifest unknown")
        assert result.category == FailureCategory.ENGINEERING
        assert result.is_substitutable is True

    # Heuristic classification - Verifier
    def test_classify_verifier_by_exception_type(self) -> None:
        """Verifier in exception type should trigger SCORING."""
        result = classify_failure("CustomVerifierError", "Something went wrong")
        assert result.category == FailureCategory.SCORING
        assert result.is_substitutable is False
        assert result.confidence == 0.9

    def test_classify_scoring_failure_from_logs(self) -> None:
        """Scoring failures in logs should be detected."""
        result = classify_failure(
            "RuntimeError",
            "Evaluation failed",
            logs="VGB runtime error: invalid output format",
        )
        assert result.category == FailureCategory.SCORING
        assert result.is_substitutable is False

    # Exit code handling
    def test_classify_sigkill_with_timeout_context(self) -> None:
        """Exit 137 with timeout context should be CAPABILITY."""
        result = classify_failure(
            "RuntimeError",
            "Process terminated",
            logs="timeout exceeded",
            exit_code=137,
        )
        assert result.category == FailureCategory.CAPABILITY
        assert result.is_substitutable is False
        assert result.confidence == 0.85

    def test_classify_sigkill_ambiguous(self) -> None:
        """Exit 137 without clear context should be ENGINEERING with low confidence."""
        result = classify_failure(
            "RuntimeError",
            "Process killed",
            exit_code=137,
        )
        assert result.category == FailureCategory.ENGINEERING
        assert result.is_substitutable is True
        assert result.confidence == 0.6

    # Default behavior
    def test_classify_unknown_failure(self) -> None:
        """Unknown failures should default to CAPABILITY with low confidence."""
        result = classify_failure("UnknownError", "Something weird happened")
        assert result.category == FailureCategory.CAPABILITY
        assert result.is_substitutable is False
        assert result.confidence == 0.3
        assert "Unclassified" in result.reason

    def test_classify_with_no_information(self) -> None:
        """Classification with no info should still work."""
        result = classify_failure(None, None)
        assert result.category == FailureCategory.CAPABILITY
        assert result.is_substitutable is False
        assert result.confidence == 0.3


class TestClassificationConsistency:
    """Test that classification rules are self-consistent."""

    def test_all_capability_are_not_substitutable(self) -> None:
        """All CAPABILITY classifications must not be substitutable."""
        test_cases = [
            ("AgentTimeoutError", "timeout"),
            ("AgentError", "internal error"),
        ]

        for exc_type, msg in test_cases:
            result = classify_failure(exc_type, msg)
            if result.category == FailureCategory.CAPABILITY:
                assert not result.is_substitutable, f"Failed for {exc_type}"

    def test_all_engineering_are_substitutable(self) -> None:
        """All ENGINEERING classifications must be substitutable."""
        test_cases = [
            ("ImagePullError", "pull failed"),
            ("NetworkError", "connection lost"),
            (None, None, "out of memory"),
            (None, None, "disk full"),
        ]

        for *args, in test_cases:
            result = classify_failure(*args)
            if result.category == FailureCategory.ENGINEERING:
                assert result.is_substitutable, f"Failed for {args}"

    def test_all_scoring_are_not_substitutable(self) -> None:
        """All SCORING classifications must not be substitutable."""
        test_cases = [
            ("VerifierRuntimeError", "verifier crashed"),
            ("VerifierTimeoutError", "verifier timeout"),
            ("CustomVerifierError", "scoring issue"),
        ]

        for exc_type, msg in test_cases:
            result = classify_failure(exc_type, msg)
            if result.category == FailureCategory.SCORING:
                assert not result.is_substitutable, f"Failed for {exc_type}"
