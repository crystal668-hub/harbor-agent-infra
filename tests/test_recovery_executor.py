"""Tests for recovery execution engine."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from harbor_agent_infra.contracts.failure_types import (
    FailureCategory,
    FailureClassification,
)
from harbor_agent_infra.contracts.run_category import RunCategory
from harbor_agent_infra.harbor.job_config import JobConfig
from harbor_agent_infra.preparation.run_config import RunConfig
from harbor_agent_infra.recovery.executor import RecoveryExecutor, RecoveryResult
from harbor_agent_infra.recovery.manifest import RecoveryManifest, RecoverySlot


@pytest.fixture
def mock_run_config(tmp_path: Path) -> RunConfig:
    """Create a mock run config."""
    config_dict = {
        "run": {
            "output_dir": str(tmp_path / "output"),
            "vgb_python": "/usr/bin/python3",
            "skills_root": str(tmp_path / "skills"),
        },
        "docker": {
            "delete_containers": True,
        },
        "task": {
            "agent_timeout_sec": 1800,
            "verifier_timeout_sec": 120,
            "agent_network_mode": "restricted",
            "agent_allowed_hosts": [],
            "verifier_network_mode": "restricted",
            "verifier_allowed_hosts": [],
        },
    }

    # Create a minimal run config
    class MockRunSection:
        def __init__(self):
            self.output_dir = config_dict["run"]["output_dir"]
            self.vgb_python = Path(config_dict["run"]["vgb_python"])
            self.skills_root = config_dict["run"]["skills_root"]

    class MockConfig:
        def __init__(self):
            self.run = MockRunSection()

    return MockConfig()


@pytest.fixture
def sample_manifest(tmp_path: Path) -> RecoveryManifest:
    """Create a sample recovery manifest."""
    fc1 = FailureClassification(
        category=FailureCategory.ENGINEERING,
        reason="Network timeout",
        is_substitutable=True,
        evidence={},
    )
    fc2 = FailureClassification(
        category=FailureCategory.CAPABILITY,
        reason="Agent timeout",
        is_substitutable=False,
        evidence={},
    )

    slot1 = RecoverySlot(
        job_name="openclaw-opus-rdkit_001",
        task_id="rdkit_001",
        original_trial_id="trial-0",
        failure_classification=fc1,
        original_run="run-123",
    )

    slot2 = RecoverySlot(
        job_name="openclaw-opus-rdkit_002",
        task_id="rdkit_002",
        original_trial_id="trial-0",
        failure_classification=fc2,
        original_run="run-123",
    )

    manifest = RecoveryManifest(
        run_name="run-123",
        run_category=RunCategory.FORMAL,
        created_at=datetime.now(),
        slots=[slot1, slot2],
    )

    # Approve only the substitutable slot
    manifest.approve_slot(slot1.slot_id)

    return manifest


class TestRecoveryExecutor:
    """Test RecoveryExecutor functionality."""

    @pytest.mark.asyncio
    async def test_execute_no_approved_slots(
        self, tmp_path: Path, mock_run_config: RunConfig
    ) -> None:
        """Executor should return empty result when no slots are approved."""
        manifest = RecoveryManifest(
            run_name="test-run",
            run_category=None,
            created_at=datetime.now(),
            slots=[],
        )

        executor = RecoveryExecutor(
            manifest=manifest,
            run_config=mock_run_config,
            output_dir=tmp_path / "recovery",
        )

        result = await executor.execute()

        assert result.total_slots == 0
        assert result.executed == 0
        assert result.succeeded == 0
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_execute_creates_recovery_directory(
        self,
        tmp_path: Path,
        mock_run_config: RunConfig,
        sample_manifest: RecoveryManifest,
    ) -> None:
        """Executor should create recovery run directory."""
        output_dir = tmp_path / "recovery-run"

        executor = RecoveryExecutor(
            manifest=sample_manifest,
            run_config=mock_run_config,
            output_dir=output_dir,
        )

        # Mock Job.create and job.run to avoid actual execution
        with patch("harbor_agent_infra.recovery.executor.Job") as mock_job_class:
            mock_job = AsyncMock()
            mock_job.run = AsyncMock()
            mock_job.run.return_value = MagicMock(
                stats=MagicMock(n_errored_trials=0, n_cancelled_trials=0)
            )
            mock_job_class.create = AsyncMock(return_value=mock_job)

            # Mock original job config loading
            with patch.object(
                executor, "_load_original_job_config"
            ) as mock_load_config:
                mock_load_config.return_value = JobConfig(
                    job_name="test-job",
                    jobs_dir=tmp_path / "jobs",
                    tasks=[{"name": "task1"}],  # Use 'name' instead of 'task_id'
                    agents=[{"harness": "openclaw"}],
                    verifier={"image": "test:latest"},
                    n_attempts=1,
                )

                await executor.execute()

        assert output_dir.exists()
        assert (output_dir / "recovery-manifest.json").exists()

    @pytest.mark.asyncio
    async def test_execute_slot_cannot_substitute(
        self, tmp_path: Path, mock_run_config: RunConfig
    ) -> None:
        """Executor should skip slots that cannot be substituted."""
        fc = FailureClassification(
            category=FailureCategory.CAPABILITY,
            reason="Timeout",
            is_substitutable=False,
            evidence={},
        )

        slot = RecoverySlot(
            job_name="job1",
            task_id="task1",
            original_trial_id="trial-0",
            failure_classification=fc,
        )

        manifest = RecoveryManifest(
            run_name="test",
            run_category=None,
            created_at=datetime.now(),
            slots=[slot],
        )

        # Force approve (even though it shouldn't be substitutable)
        manifest.approve_slot(slot.slot_id)

        executor = RecoveryExecutor(
            manifest=manifest,
            run_config=mock_run_config,
            output_dir=tmp_path / "recovery",
        )

        result = await executor.execute()

        assert result.executed == 0
        assert result.skipped == 1
        assert "Cannot substitute" in result.slot_results[0].error

    @pytest.mark.asyncio
    async def test_execute_slot_original_config_not_found(
        self, tmp_path: Path, mock_run_config: RunConfig
    ) -> None:
        """Executor should handle missing original job config."""
        fc = FailureClassification(
            category=FailureCategory.ENGINEERING,
            reason="Network",
            is_substitutable=True,
            evidence={},
        )

        slot = RecoverySlot(
            job_name="job1",
            task_id="task1",
            original_trial_id="trial-0",
            failure_classification=fc,
            original_run="nonexistent-run",
        )

        manifest = RecoveryManifest(
            run_name="test",
            run_category=None,
            created_at=datetime.now(),
            slots=[slot],
        )

        manifest.approve_slot(slot.slot_id)

        executor = RecoveryExecutor(
            manifest=manifest,
            run_config=mock_run_config,
            output_dir=tmp_path / "recovery",
        )

        result = await executor.execute()

        assert result.executed == 0
        assert result.skipped == 1
        assert "Could not load original job config" in result.slot_results[0].error


class TestRecoveryResult:
    """Test RecoveryResult functionality."""

    def test_to_dict_serialization(self) -> None:
        """RecoveryResult should serialize correctly."""
        from harbor_agent_infra.recovery.executor import SlotExecutionResult

        slot_result = SlotExecutionResult(
            slot_id="job1::task1",
            job_name="job1",
            task_id="task1",
            executed=True,
            success=True,
            recovery_job_dir="/path/to/job",
        )

        result = RecoveryResult(
            recovery_run_name="recovery-123",
            total_slots=1,
            executed=1,
            succeeded=1,
            failed=0,
            skipped=0,
            slot_results=[slot_result],
        )

        data = result.to_dict()

        assert data["recovery_run_name"] == "recovery-123"
        assert data["total_slots"] == 1
        assert data["succeeded"] == 1
        assert len(data["slot_results"]) == 1
        assert data["slot_results"][0]["success"] is True
