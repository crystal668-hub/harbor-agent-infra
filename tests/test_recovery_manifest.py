"""Tests for recovery manifest generation and persistence."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from harbor_agent_infra.contracts.failure_types import (
    FailureCategory,
    FailureClassification,
)
from harbor_agent_infra.contracts.run_category import RunCategory
from harbor_agent_infra.recovery.auditor import audit_run
from harbor_agent_infra.recovery.manifest import RecoveryManifest, RecoverySlot


class TestRecoverySlot:
    """Test RecoverySlot functionality."""

    def test_slot_id_generation(self) -> None:
        """Slot ID should combine job_name and task_id."""
        fc = FailureClassification(
            category=FailureCategory.CAPABILITY,
            reason="Test",
            is_substitutable=False,
            evidence={},
        )
        slot = RecoverySlot(
            job_name="openclaw-opus-rdkit_001",
            task_id="rdkit_001",
            original_trial_id="trial-0",
            failure_classification=fc,
        )
        assert slot.slot_id == "openclaw-opus-rdkit_001::rdkit_001"

    def test_can_substitute_true(self) -> None:
        """Engineering failures with count < max should be substitutable."""
        fc = FailureClassification(
            category=FailureCategory.ENGINEERING,
            reason="Network error",
            is_substitutable=True,
            evidence={},
        )
        slot = RecoverySlot(
            job_name="job1",
            task_id="task1",
            original_trial_id="trial-0",
            failure_classification=fc,
            substitution_count=0,
            max_substitutions=2,
        )
        assert slot.can_substitute is True

    def test_can_substitute_false_not_substitutable(self) -> None:
        """Capability failures should not be substitutable."""
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
        assert slot.can_substitute is False

    def test_can_substitute_false_max_reached(self) -> None:
        """Slots at max substitutions should not be substitutable."""
        fc = FailureClassification(
            category=FailureCategory.ENGINEERING,
            reason="Network error",
            is_substitutable=True,
            evidence={},
        )
        slot = RecoverySlot(
            job_name="job1",
            task_id="task1",
            original_trial_id="trial-0",
            failure_classification=fc,
            substitution_count=2,
            max_substitutions=2,
        )
        assert slot.can_substitute is False

    def test_serialization_round_trip(self) -> None:
        """Slot should serialize and deserialize correctly."""
        fc = FailureClassification(
            category=FailureCategory.ENGINEERING,
            reason="OOM",
            is_substitutable=True,
            evidence={"exit_code": 137},
            confidence=0.9,
        )
        original = RecoverySlot(
            job_name="job1",
            task_id="task1",
            original_trial_id="trial-0",
            failure_classification=fc,
            substitution_count=1,
            original_run="run-123",
            approved=True,
        )

        data = original.to_dict()
        restored = RecoverySlot.from_dict(data)

        assert restored.job_name == original.job_name
        assert restored.task_id == original.task_id
        assert restored.original_trial_id == original.original_trial_id
        assert restored.substitution_count == original.substitution_count
        assert restored.approved == original.approved
        assert restored.failure_classification.category == fc.category
        assert restored.failure_classification.reason == fc.reason


class TestRecoveryManifest:
    """Test RecoveryManifest functionality."""

    def test_approve_slot(self) -> None:
        """Approving a slot should update both approved_slot_ids and slot.approved."""
        fc = FailureClassification(
            category=FailureCategory.ENGINEERING,
            reason="Test",
            is_substitutable=True,
            evidence={},
        )
        slot = RecoverySlot(
            job_name="job1",
            task_id="task1",
            original_trial_id="trial-0",
            failure_classification=fc,
        )

        manifest = RecoveryManifest(
            run_name="test-run",
            run_category=RunCategory.FORMAL,
            created_at=datetime.now(),
            slots=[slot],
        )

        manifest.approve_slot(slot.slot_id)

        assert slot.slot_id in manifest.approved_slot_ids
        assert slot.approved is True

    def test_approve_all_substitutable(self) -> None:
        """Should auto-approve only substitutable slots."""
        fc_eng = FailureClassification(
            category=FailureCategory.ENGINEERING,
            reason="Network",
            is_substitutable=True,
            evidence={},
        )
        fc_cap = FailureClassification(
            category=FailureCategory.CAPABILITY,
            reason="Timeout",
            is_substitutable=False,
            evidence={},
        )

        slot1 = RecoverySlot(
            job_name="job1",
            task_id="task1",
            original_trial_id="trial-0",
            failure_classification=fc_eng,
        )
        slot2 = RecoverySlot(
            job_name="job2",
            task_id="task2",
            original_trial_id="trial-0",
            failure_classification=fc_cap,
        )
        slot3 = RecoverySlot(
            job_name="job3",
            task_id="task3",
            original_trial_id="trial-0",
            failure_classification=fc_eng,
            substitution_count=2,
            max_substitutions=2,  # Already maxed out
        )

        manifest = RecoveryManifest(
            run_name="test-run",
            run_category=None,
            created_at=datetime.now(),
            slots=[slot1, slot2, slot3],
        )

        manifest.approve_all_substitutable()

        assert slot1.approved is True  # Engineering, can substitute
        assert slot2.approved is False  # Capability, cannot substitute
        assert slot3.approved is False  # Engineering but maxed out

    def test_get_approved_slots(self) -> None:
        """Should return only approved slots."""
        fc = FailureClassification(
            category=FailureCategory.ENGINEERING,
            reason="Test",
            is_substitutable=True,
            evidence={},
        )

        slot1 = RecoverySlot(
            job_name="job1",
            task_id="task1",
            original_trial_id="trial-0",
            failure_classification=fc,
        )
        slot2 = RecoverySlot(
            job_name="job2",
            task_id="task2",
            original_trial_id="trial-0",
            failure_classification=fc,
        )

        manifest = RecoveryManifest(
            run_name="test-run",
            run_category=None,
            created_at=datetime.now(),
            slots=[slot1, slot2],
        )

        manifest.approve_slot(slot1.slot_id)

        approved = manifest.get_approved_slots()
        assert len(approved) == 1
        assert approved[0].slot_id == slot1.slot_id

    def test_manifest_serialization(self, tmp_path: Path) -> None:
        """Manifest should save and load correctly."""
        fc = FailureClassification(
            category=FailureCategory.ENGINEERING,
            reason="Network",
            is_substitutable=True,
            evidence={"pattern": "timeout"},
        )

        slot = RecoverySlot(
            job_name="job1",
            task_id="task1",
            original_trial_id="trial-0",
            failure_classification=fc,
        )

        original = RecoveryManifest(
            run_name="test-run",
            run_category=RunCategory.TEMPORARY,
            created_at=datetime.now(),
            slots=[slot],
            metadata={"note": "test manifest"},
        )

        original.approve_slot(slot.slot_id)

        # Save and load
        manifest_path = tmp_path / "manifest.json"
        original.save(manifest_path)

        restored = RecoveryManifest.load(manifest_path)

        assert restored.run_name == original.run_name
        assert restored.run_category == original.run_category
        assert len(restored.slots) == 1
        assert restored.slots[0].slot_id == slot.slot_id
        assert restored.slots[0].approved is True
        assert slot.slot_id in restored.approved_slot_ids


class TestAuditRun:
    """Test run auditing functionality."""

    def test_audit_empty_run(self, tmp_path: Path) -> None:
        """Auditing a run with no failures should return empty manifest."""
        run_dir = tmp_path / "run-123"
        jobs_dir = run_dir / "jobs"
        jobs_dir.mkdir(parents=True)

        manifest = audit_run(run_dir, run_name="run-123")

        assert manifest.run_name == "run-123"
        assert len(manifest.slots) == 0

    def test_audit_run_with_failed_trial(self, tmp_path: Path) -> None:
        """Auditing should detect failed trials and classify them."""
        run_dir = tmp_path / "run-123"
        jobs_dir = run_dir / "jobs"
        job_dir = jobs_dir / "openclaw-opus-rdkit_001"
        job_dir.mkdir(parents=True)

        # Create job config
        config = {
            "task_id": "rdkit_001",
            "agent": "openclaw",
            "model": "opus",
        }
        (job_dir / "config.json").write_text(json.dumps(config))

        # Create harbor.json with a failed trial
        harbor = {
            "trials": [
                {
                    "trial_id": "trial-0",
                    "exception_info": {
                        "exception_type": "AgentTimeoutError",
                        "exception_message": "Agent exceeded 1800s",
                    },
                    "result": None,
                }
            ]
        }
        (job_dir / "harbor.json").write_text(json.dumps(harbor))

        manifest = audit_run(run_dir, run_name="run-123", category=RunCategory.FORMAL)

        assert manifest.run_name == "run-123"
        assert manifest.run_category == RunCategory.FORMAL
        assert len(manifest.slots) == 1

        slot = manifest.slots[0]
        assert slot.job_name == "openclaw-opus-rdkit_001"
        assert slot.task_id == "rdkit_001"
        assert slot.original_trial_id == "trial-0"
        assert slot.failure_classification.category == FailureCategory.CAPABILITY
        assert slot.substitution_count == 0

    def test_audit_run_detects_recovery_metadata(self, tmp_path: Path) -> None:
        """Auditing should detect existing recovery substitution count."""
        run_dir = tmp_path / "recovery-run"
        jobs_dir = run_dir / "jobs"
        job_dir = jobs_dir / "job1"
        job_dir.mkdir(parents=True)

        config = {"task_id": "task1"}
        (job_dir / "config.json").write_text(json.dumps(config))

        # This is a recovery job (substitution_attempt = 1)
        harbor = {
            "recovery_metadata": {
                "is_recovery": True,
                "substitution_attempt": 1,
                "original_run": "run-123",
                "original_job": "job1",
            },
            "trials": [
                {
                    "trial_id": "trial-0",
                    "exception_info": {
                        "exception_type": "NetworkError",
                        "exception_message": "Connection failed",
                    },
                }
            ],
        }
        (job_dir / "harbor.json").write_text(json.dumps(harbor))

        manifest = audit_run(run_dir, run_name="recovery-run")

        slot = manifest.slots[0]
        assert slot.substitution_count == 1  # Should detect it's a recovery job
        assert slot.max_substitutions == 2
        assert slot.can_substitute is True  # Can still substitute once more

    def test_audit_run_invalid_directory(self) -> None:
        """Auditing non-existent directory should raise ValueError."""
        with pytest.raises(ValueError, match="does not exist"):
            audit_run(Path("/nonexistent"), run_name="test")

    def test_audit_run_no_jobs_directory(self, tmp_path: Path) -> None:
        """Auditing directory without jobs/ should raise ValueError."""
        run_dir = tmp_path / "run-123"
        run_dir.mkdir()

        with pytest.raises(ValueError, match="No jobs/ directory"):
            audit_run(run_dir, run_name="run-123")
