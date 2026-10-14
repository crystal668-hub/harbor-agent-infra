"""Tests for recovery analyzer."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from harbor_agent_infra.contracts.failure_types import (
    FailureCategory,
    FailureClassification,
)
from harbor_agent_infra.recovery.analyzer import RecoveryAnalyzer
from harbor_agent_infra.recovery.manifest import RecoveryManifest, RecoverySlot


@pytest.fixture
def recovery_run_dir(tmp_path: Path) -> Path:
    """Create a mock recovery run directory with manifest and results."""
    run_dir = tmp_path / "recovery-run"
    run_dir.mkdir()

    # Create recovery manifest with mixed failure types
    slots = [
        # Engineering failure - approved and recovered successfully
        RecoverySlot(
            job_name="openclaw-opus",
            task_id="rdkit_001",
            original_trial_id="trial-0",
            failure_classification=FailureClassification(
                category=FailureCategory.ENGINEERING,
                reason="Network timeout",
                is_substitutable=True,
                evidence={},
            ),
            approved=True,
        ),
        # Engineering failure - approved but recovery failed
        RecoverySlot(
            job_name="openclaw-opus",
            task_id="rdkit_002",
            original_trial_id="trial-0",
            failure_classification=FailureClassification(
                category=FailureCategory.ENGINEERING,
                reason="Network timeout",
                is_substitutable=True,
                evidence={},
            ),
            approved=True,
        ),
        # Capability failure - not approved
        RecoverySlot(
            job_name="hermes-qwen",
            task_id="rdkit_003",
            original_trial_id="trial-0",
            failure_classification=FailureClassification(
                category=FailureCategory.CAPABILITY,
                reason="Agent timeout",
                is_substitutable=False,
                evidence={},
            ),
            approved=False,
        ),
        # Scoring failure - approved
        RecoverySlot(
            job_name="codex-gpt",
            task_id="rdkit_004",
            original_trial_id="trial-0",
            failure_classification=FailureClassification(
                category=FailureCategory.SCORING,
                reason="Verifier error",
                is_substitutable=True,
                evidence={},
            ),
            approved=True,
        ),
    ]

    manifest = RecoveryManifest(
        run_name="recovery-run",
        run_category=None,
        created_at=datetime.now(),
        slots=slots,
    )

    manifest.save(run_dir / "recovery-manifest.json")

    # Create recovery job results
    jobs_dir = run_dir / "jobs"
    jobs_dir.mkdir()

    # Job 1: Successful recovery
    job1_dir = jobs_dir / "openclaw-opus-recovery-1"
    job1_dir.mkdir()

    metadata1 = {
        "slot_id": "openclaw-opus::rdkit_001",
        "original_job_name": "openclaw-opus",
        "task_id": "rdkit_001",
    }
    with open(job1_dir / "recovery-metadata.json", "w") as f:
        json.dump(metadata1, f)

    trial1_dir = job1_dir / "trials" / "rdkit_001__trial-0"
    trial1_dir.mkdir(parents=True)
    with open(trial1_dir / "result.json", "w") as f:
        json.dump({"outcome": "success", "score": 1.0}, f)

    # Job 2: Failed recovery
    job2_dir = jobs_dir / "openclaw-opus-recovery-2"
    job2_dir.mkdir()

    metadata2 = {
        "slot_id": "openclaw-opus::rdkit_002",
        "original_job_name": "openclaw-opus",
        "task_id": "rdkit_002",
    }
    with open(job2_dir / "recovery-metadata.json", "w") as f:
        json.dump(metadata2, f)

    trial2_dir = job2_dir / "trials" / "rdkit_002__trial-0"
    trial2_dir.mkdir(parents=True)
    with open(trial2_dir / "result.json", "w") as f:
        json.dump({"outcome": "error", "error": "Still failing"}, f)

    # Job 3: Scoring recovery (approved but not executed yet in this fixture)

    return run_dir


class TestRecoveryAnalyzer:
    """Test RecoveryAnalyzer functionality."""

    def test_analyze_basic_counts(self, recovery_run_dir: Path) -> None:
        """Analyzer should count failures by category correctly."""
        analyzer = RecoveryAnalyzer(run_dir=recovery_run_dir)
        stats = analyzer.analyze()

        assert stats.total_failures == 4
        assert stats.engineering_failures == 2
        assert stats.capability_failures == 1
        assert stats.scoring_failures == 1

    def test_analyze_substitutable_counts(self, recovery_run_dir: Path) -> None:
        """Analyzer should identify substitutable failures."""
        analyzer = RecoveryAnalyzer(run_dir=recovery_run_dir)
        stats = analyzer.analyze()

        assert stats.substitutable_failures == 3  # 2 engineering + 1 scoring

    def test_analyze_approval_counts(self, recovery_run_dir: Path) -> None:
        """Analyzer should count approved slots."""
        analyzer = RecoveryAnalyzer(run_dir=recovery_run_dir)
        stats = analyzer.analyze()

        assert stats.approved_for_recovery == 3  # 2 engineering + 1 scoring

    def test_analyze_recovery_outcomes(self, recovery_run_dir: Path) -> None:
        """Analyzer should track recovery success/failure."""
        analyzer = RecoveryAnalyzer(run_dir=recovery_run_dir)
        stats = analyzer.analyze()

        assert stats.successfully_recovered == 1
        assert stats.recovery_failed == 1

    def test_analyze_recovery_rates(self, recovery_run_dir: Path) -> None:
        """Analyzer should calculate recovery rates."""
        analyzer = RecoveryAnalyzer(run_dir=recovery_run_dir)
        stats = analyzer.analyze()

        # 1 success out of 3 approved (but only 2 executed)
        # Overall: 1/3 ≈ 0.33
        assert 0.3 < stats.recovery_rate < 0.4

        # Engineering: 1 success out of 2 approved = 0.5
        assert stats.engineering_recovery_rate == 0.5

    def test_analyze_failure_reasons(self, recovery_run_dir: Path) -> None:
        """Analyzer should aggregate failure reasons."""
        analyzer = RecoveryAnalyzer(run_dir=recovery_run_dir)
        stats = analyzer.analyze()

        assert stats.failure_reasons["Network timeout"] == 2
        assert stats.failure_reasons["Agent timeout"] == 1
        assert stats.failure_reasons["Verifier error"] == 1

    def test_analyze_failures_by_job(self, recovery_run_dir: Path) -> None:
        """Analyzer should aggregate failures by job."""
        analyzer = RecoveryAnalyzer(run_dir=recovery_run_dir)
        stats = analyzer.analyze()

        assert stats.failures_by_job["openclaw-opus"] == 2
        assert stats.failures_by_job["hermes-qwen"] == 1
        assert stats.failures_by_job["codex-gpt"] == 1

    def test_analyze_failures_by_task(self, recovery_run_dir: Path) -> None:
        """Analyzer should aggregate failures by task."""
        analyzer = RecoveryAnalyzer(run_dir=recovery_run_dir)
        stats = analyzer.analyze()

        assert stats.failures_by_task["rdkit_001"] == 1
        assert stats.failures_by_task["rdkit_002"] == 1
        assert stats.failures_by_task["rdkit_003"] == 1
        assert stats.failures_by_task["rdkit_004"] == 1

    def test_analyze_no_manifest(self, tmp_path: Path) -> None:
        """Analyzer should raise error if manifest missing."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        analyzer = RecoveryAnalyzer(run_dir=empty_dir)

        with pytest.raises(FileNotFoundError, match="Recovery manifest not found"):
            analyzer.analyze()

    def test_generate_report(self, recovery_run_dir: Path) -> None:
        """Analyzer should generate human-readable report."""
        analyzer = RecoveryAnalyzer(run_dir=recovery_run_dir)
        report = analyzer.generate_report()

        # Check that report contains key sections
        assert "Recovery Analysis Report" in report
        assert "Failure Overview" in report
        assert "Recovery Execution" in report
        assert "Top Failure Reasons" in report
        assert "Failures by Job" in report
        assert "Top Failed Tasks" in report

        # Check specific values
        assert "Total failures: 4" in report
        assert "Engineering: 2" in report
        assert "Successfully recovered: 1" in report

    def test_stats_to_dict(self, recovery_run_dir: Path) -> None:
        """RecoveryStats should serialize to dict."""
        analyzer = RecoveryAnalyzer(run_dir=recovery_run_dir)
        stats = analyzer.analyze()

        data = stats.to_dict()

        assert data["total_failures"] == 4
        assert data["engineering_failures"] == 2
        assert data["successfully_recovered"] == 1
        assert isinstance(data["failure_reasons"], dict)
        assert isinstance(data["recovery_rate"], float)
