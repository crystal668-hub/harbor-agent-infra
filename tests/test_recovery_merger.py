"""Tests for result merger."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from harbor_agent_infra.contracts.failure_types import (
    FailureCategory,
    FailureClassification,
)
from harbor_agent_infra.recovery.manifest import RecoveryManifest, RecoverySlot
from harbor_agent_infra.recovery.merger import ResultMerger


@pytest.fixture
def original_run_dir(tmp_path: Path) -> Path:
    """Create a mock original run directory with failed trials."""
    run_dir = tmp_path / "original-run"
    run_dir.mkdir()

    # Create jobs directory
    jobs_dir = run_dir / "jobs"
    jobs_dir.mkdir()

    # Create a job with a failed trial
    job_dir = jobs_dir / "openclaw-opus"
    job_dir.mkdir()

    trials_dir = job_dir / "trials"
    trials_dir.mkdir()

    # Create a failed trial
    trial_dir = trials_dir / "rdkit_001__trial-0"
    trial_dir.mkdir()

    result = {
        "outcome": "error",
        "error": "Network timeout",
        "task_id": "rdkit_001",
    }

    with open(trial_dir / "result.json", "w") as f:
        json.dump(result, f)

    return run_dir


@pytest.fixture
def recovery_run_dir(tmp_path: Path) -> Path:
    """Create a mock recovery run directory with successful trial."""
    recovery_dir = tmp_path / "recovery-run"
    recovery_dir.mkdir()

    # Create recovery manifest
    fc = FailureClassification(
        category=FailureCategory.ENGINEERING,
        reason="Network timeout",
        is_substitutable=True,
        evidence={},
    )

    slot = RecoverySlot(
        job_name="openclaw-opus",
        task_id="rdkit_001",
        original_trial_id="trial-0",
        failure_classification=fc,
        original_run="original-run",
    )

    manifest = RecoveryManifest(
        run_name="recovery-run",
        run_category=None,
        created_at=datetime.now(),
        slots=[slot],
    )

    manifest.save(recovery_dir / "recovery-manifest.json")

    # Create recovery job
    jobs_dir = recovery_dir / "jobs"
    jobs_dir.mkdir()

    job_dir = jobs_dir / "openclaw-opus-recovery"
    job_dir.mkdir()

    # Add recovery metadata
    metadata = {
        "slot_id": "openclaw-opus::rdkit_001",
        "original_job_name": "openclaw-opus",
        "task_id": "rdkit_001",
    }

    with open(job_dir / "recovery-metadata.json", "w") as f:
        json.dump(metadata, f)

    # Create successful recovery trial
    trials_dir = job_dir / "trials"
    trials_dir.mkdir()

    trial_dir = trials_dir / "rdkit_001__trial-0"
    trial_dir.mkdir()

    result = {
        "outcome": "success",
        "task_id": "rdkit_001",
        "score": 1.0,
    }

    with open(trial_dir / "result.json", "w") as f:
        json.dump(result, f)

    # Create some trial artifacts
    (trial_dir / "agent.log").write_text("Recovery agent log")
    (trial_dir / "solution.txt").write_text("Recovery solution")

    return recovery_dir


class TestResultMerger:
    """Test ResultMerger functionality."""

    def test_merge_basic(
        self,
        tmp_path: Path,
        original_run_dir: Path,
        recovery_run_dir: Path,
    ) -> None:
        """Merger should successfully merge recovery results."""
        output_dir = tmp_path / "merged"

        merger = ResultMerger(
            original_run_dir=original_run_dir,
            recovery_dirs=[recovery_run_dir],
            output_dir=output_dir,
        )

        result = merger.merge()

        assert result.original_run == "original-run"
        assert result.recovery_runs == ["recovery-run"]
        assert result.total_slots == 1
        assert result.merged_slots == 1
        assert len(result.conflicts) == 0

        # Check that output directory was created
        assert output_dir.exists()
        assert (output_dir / "jobs").exists()
        assert (output_dir / "merge-metadata.json").exists()

    def test_merge_creates_backup(
        self,
        tmp_path: Path,
        original_run_dir: Path,
        recovery_run_dir: Path,
    ) -> None:
        """Merger should backup original failed trial."""
        output_dir = tmp_path / "merged"

        merger = ResultMerger(
            original_run_dir=original_run_dir,
            recovery_dirs=[recovery_run_dir],
            output_dir=output_dir,
        )

        result = merger.merge()

        assert result.merged_slots == 1

        # Check that backup was created
        job_dir = output_dir / "jobs" / "openclaw-opus"
        trials_dir = job_dir / "trials"

        backup_dir = trials_dir / "rdkit_001__trial-0__replaced"
        assert backup_dir.exists()

        # Check that backup contains original result
        with open(backup_dir / "result.json") as f:
            result_data = json.load(f)
            assert result_data["outcome"] == "error"

    def test_merge_adds_recovery_marker(
        self,
        tmp_path: Path,
        original_run_dir: Path,
        recovery_run_dir: Path,
    ) -> None:
        """Merger should add recovery marker to merged trial."""
        output_dir = tmp_path / "merged"

        merger = ResultMerger(
            original_run_dir=original_run_dir,
            recovery_dirs=[recovery_run_dir],
            output_dir=output_dir,
        )

        result = merger.merge()

        assert result.merged_slots == 1

        # Check recovery marker
        job_dir = output_dir / "jobs" / "openclaw-opus"
        trial_dir = job_dir / "trials" / "rdkit_001__trial-0"

        marker_path = trial_dir / "recovery-marker.json"
        assert marker_path.exists()

        with open(marker_path) as f:
            marker = json.load(f)
            assert marker["recovered"] is True
            assert marker["recovery_job"] == "openclaw-opus-recovery"
            assert marker["original_trial_backup"] == "rdkit_001__trial-0__replaced"

    def test_merge_preserves_recovery_artifacts(
        self,
        tmp_path: Path,
        original_run_dir: Path,
        recovery_run_dir: Path,
    ) -> None:
        """Merger should copy all recovery trial artifacts."""
        output_dir = tmp_path / "merged"

        merger = ResultMerger(
            original_run_dir=original_run_dir,
            recovery_dirs=[recovery_run_dir],
            output_dir=output_dir,
        )

        result = merger.merge()

        assert result.merged_slots == 1

        # Check that recovery artifacts were copied
        trial_dir = output_dir / "jobs" / "openclaw-opus" / "trials" / "rdkit_001__trial-0"

        assert (trial_dir / "result.json").exists()
        assert (trial_dir / "agent.log").exists()
        assert (trial_dir / "solution.txt").exists()

        # Check result content
        with open(trial_dir / "result.json") as f:
            result_data = json.load(f)
            assert result_data["outcome"] == "success"
            assert result_data["score"] == 1.0

    def test_merge_no_original_job(
        self,
        tmp_path: Path,
        recovery_run_dir: Path,
    ) -> None:
        """Merger should handle missing original job gracefully."""
        # Create empty original run
        original_dir = tmp_path / "original"
        original_dir.mkdir()
        (original_dir / "jobs").mkdir()

        output_dir = tmp_path / "merged"

        merger = ResultMerger(
            original_run_dir=original_dir,
            recovery_dirs=[recovery_run_dir],
            output_dir=output_dir,
        )

        result = merger.merge()

        assert result.total_slots == 1
        assert result.merged_slots == 0
        assert len(result.conflicts) == 1
        assert "Original job not found" in result.conflicts[0]

    def test_merge_multiple_recovery_runs(
        self,
        tmp_path: Path,
        original_run_dir: Path,
        recovery_run_dir: Path,
    ) -> None:
        """Merger should handle multiple recovery runs."""
        # Create second recovery run
        recovery_dir_2 = tmp_path / "recovery-run-2"
        recovery_dir_2.mkdir()

        fc = FailureClassification(
            category=FailureCategory.ENGINEERING,
            reason="Timeout",
            is_substitutable=True,
            evidence={},
        )

        slot = RecoverySlot(
            job_name="openclaw-opus",
            task_id="rdkit_002",
            original_trial_id="trial-0",
            failure_classification=fc,
        )

        manifest = RecoveryManifest(
            run_name="recovery-run-2",
            run_category=None,
            created_at=datetime.now(),
            slots=[slot],
        )

        manifest.save(recovery_dir_2 / "recovery-manifest.json")

        output_dir = tmp_path / "merged"

        merger = ResultMerger(
            original_run_dir=original_run_dir,
            recovery_dirs=[recovery_run_dir, recovery_dir_2],
            output_dir=output_dir,
        )

        result = merger.merge()

        assert len(result.recovery_runs) == 2
        assert "recovery-run" in result.recovery_runs
        assert "recovery-run-2" in result.recovery_runs

    def test_to_dict_serialization(
        self,
        tmp_path: Path,
        original_run_dir: Path,
        recovery_run_dir: Path,
    ) -> None:
        """MergedResult should serialize correctly."""
        output_dir = tmp_path / "merged"

        merger = ResultMerger(
            original_run_dir=original_run_dir,
            recovery_dirs=[recovery_run_dir],
            output_dir=output_dir,
        )

        result = merger.merge()
        data = result.to_dict()

        assert data["original_run"] == "original-run"
        assert data["total_slots"] == 1
        assert data["merged_slots"] == 1
        assert isinstance(data["conflicts"], list)
        assert "merged_output_path" in data
