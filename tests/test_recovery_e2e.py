"""End-to-end integration tests for recovery system.

These tests verify the complete recovery workflow:
audit -> approve -> recover -> merge -> analyze
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from harbor_agent_infra.contracts.failure_types import FailureCategory
from harbor_agent_infra.recovery.analyzer import RecoveryAnalyzer
from harbor_agent_infra.recovery.auditor import audit_run
from harbor_agent_infra.recovery.executor import RecoveryExecutor
from harbor_agent_infra.recovery.manifest import RecoveryManifest
from harbor_agent_infra.recovery.merger import ResultMerger


@pytest.fixture
def sample_run_dir(tmp_path: Path) -> Path:
    """Create a sample run with failed and successful trials."""
    run_dir = tmp_path / "sample-run"
    run_dir.mkdir()

    jobs_dir = run_dir / "jobs"
    jobs_dir.mkdir()

    # Job 1: openclaw-opus with one failed trial (engineering)
    job1_dir = jobs_dir / "openclaw-opus"
    job1_dir.mkdir()

    # Job config
    with open(job1_dir / "config.json", "w") as f:
        json.dump({"task_id": "rdkit_001", "job_name": "openclaw-opus"}, f)

    # Harbor metadata with failed trial
    with open(job1_dir / "harbor.json", "w") as f:
        json.dump(
            {
                "trials": [
                    {
                        "trial_id": "rdkit_001__trial-0",
                        "exception_info": {
                            "exception_type": "DockerException",
                            "exception_message": "Network timeout during image pull",
                        },
                        "result": None,
                    }
                ]
            },
            f,
        )

    job1_trials = job1_dir / "trials"
    job1_trials.mkdir()

    # Failed trial directory
    trial1_dir = job1_trials / "rdkit_001__trial-0"
    trial1_dir.mkdir()
    (trial1_dir / "agent.log").write_text("Failed to pull image...")
    # Add result.json to indicate failure
    with open(trial1_dir / "result.json", "w") as f:
        json.dump({"outcome": "error", "error": "DockerException"}, f)

    # Job 2: hermes-qwen with capability failure
    job2_dir = jobs_dir / "hermes-qwen"
    job2_dir.mkdir()

    # Job config
    with open(job2_dir / "config.json", "w") as f:
        json.dump({"task_id": "rdkit_003", "job_name": "hermes-qwen"}, f)

    # Harbor metadata with failed trial
    with open(job2_dir / "harbor.json", "w") as f:
        json.dump(
            {
                "trials": [
                    {
                        "trial_id": "rdkit_003__trial-0",
                        "exception_info": {
                            "exception_type": "TimeoutError",
                            "exception_message": "Agent timeout after 1800 seconds",
                        },
                        "result": None,
                    }
                ]
            },
            f,
        )

    job2_trials = job2_dir / "trials"
    job2_trials.mkdir()

    trial3_dir = job2_trials / "rdkit_003__trial-0"
    trial3_dir.mkdir()
    (trial3_dir / "agent.log").write_text("Timeout...")
    # Add result.json to indicate failure
    with open(trial3_dir / "result.json", "w") as f:
        json.dump({"outcome": "error", "error": "TimeoutError"}, f)

    return run_dir


@pytest.fixture
def experiment_config(tmp_path: Path) -> Path:
    """Create a minimal experiment config for recovery."""
    config_path = tmp_path / "experiment.toml"

    config_content = """
[experiment]
name = "test-recovery"

[task]
agent_timeout_sec = 1800
verifier_timeout_sec = 120
agent_network_mode = "limited"
agent_allowed_hosts = ["registry.example.com"]
verifier_network_mode = "limited"
verifier_allowed_hosts = []

[[harness]]
name = "openclaw"
version = "2026.6.34"
image = "example.com/openclaw:2026.6.34"
model = "claude-opus-5.5"
thinking = "high"
max_output_tokens = 64000

[[harness]]
name = "hermes"
version = "0.21.6"
image = "example.com/hermes:0.21.6"
model = "qwen3.8-max"
reasoning = "high"
max_output_tokens = 64000

[[benchmark.case]]
track = "open_generation_rdkit"
task_ids = ["rdkit_001", "rdkit_002", "rdkit_003"]
n_attempts = 1
"""

    config_path.write_text(config_content)
    return config_path


class TestEndToEndRecovery:
    """Test complete recovery workflow."""

    def test_full_workflow_audit_to_analysis(
        self,
        sample_run_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Test complete workflow: audit -> approve -> analyze."""
        # Phase 1: Audit
        manifest = audit_run(
            run_dir=sample_run_dir,
            run_name="sample-run",
        )

        # Verify audit results
        assert len(manifest.slots) == 2  # Two failures detected
        engineering_slots = [
            s
            for s in manifest.slots
            if s.failure_classification.category == FailureCategory.ENGINEERING
        ]
        capability_slots = [
            s
            for s in manifest.slots
            if s.failure_classification.category == FailureCategory.CAPABILITY
        ]

        assert len(engineering_slots) == 1
        assert len(capability_slots) == 1

        # Phase 2: Approve (only engineering failure)
        manifest.approve_slot(slot_id=engineering_slots[0].slot_id)

        # Save manifest
        manifest_path = tmp_path / "recovery-manifest.json"
        manifest.save(manifest_path)

        # Verify manifest saved correctly
        loaded_manifest = RecoveryManifest.load(manifest_path)
        assert len(loaded_manifest.get_approved_slots()) == 1

        # Phase 3: Analysis (without actual recovery execution)
        # Create a mock recovery run for analysis
        recovery_dir = tmp_path / "recovery-run"
        recovery_dir.mkdir()

        # Save manifest to recovery directory
        manifest.save(recovery_dir / "recovery-manifest.json")

        # Create mock recovery results
        jobs_dir = recovery_dir / "jobs"
        jobs_dir.mkdir()

        recovery_job = jobs_dir / "openclaw-opus-recovery"
        recovery_job.mkdir()

        # Recovery metadata
        with open(recovery_job / "recovery-metadata.json", "w") as f:
            json.dump(
                {
                    "slot_id": engineering_slots[0].slot_id,
                    "original_job_name": "openclaw-opus",
                    "task_id": "rdkit_001",
                },
                f,
            )

        # Successful recovery trial
        recovery_trial = recovery_job / "trials" / "rdkit_001__trial-0"
        recovery_trial.mkdir(parents=True)
        with open(recovery_trial / "result.json", "w") as f:
            json.dump({"outcome": "success", "score": 1.0, "task_id": "rdkit_001"}, f)

        # Phase 4: Analyze
        analyzer = RecoveryAnalyzer(run_dir=recovery_dir)
        stats = analyzer.analyze()

        assert stats.total_failures == 2
        assert stats.engineering_failures == 1
        assert stats.capability_failures == 1
        assert stats.approved_for_recovery == 1
        assert stats.successfully_recovered == 1
        assert stats.recovery_rate == 1.0

    def test_full_workflow_with_merge(
        self,
        sample_run_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Test audit -> recovery -> merge workflow."""
        # Phase 1: Audit with auto-approve
        manifest = audit_run(
            run_dir=sample_run_dir,
            run_name="sample-run",
        )

        # Auto-approve substitutable slots
        manifest.approve_all_substitutable()

        # Verify auto-approval worked
        approved = manifest.get_approved_slots()
        assert len(approved) == 1  # Only engineering failure auto-approved

        # Phase 2: Create mock recovery run
        recovery_dir = tmp_path / "recovery-run"
        recovery_dir.mkdir()

        manifest.save(recovery_dir / "recovery-manifest.json")

        jobs_dir = recovery_dir / "jobs"
        jobs_dir.mkdir()

        # Create recovery job
        recovery_job = jobs_dir / "openclaw-opus-recovery"
        recovery_job.mkdir()

        # Job config
        with open(recovery_job / "config.json", "w") as f:
            json.dump({"task_id": "rdkit_001", "job_name": "openclaw-opus-recovery"}, f)

        # Recovery metadata
        with open(recovery_job / "recovery-metadata.json", "w") as f:
            json.dump(
                {
                    "slot_id": approved[0].slot_id,
                    "original_job_name": "openclaw-opus",
                    "task_id": "rdkit_001",
                    "substitution_count": 0,  # This is the first recovery attempt
                },
                f,
            )

        # Harbor metadata with successful recovery trial
        with open(recovery_job / "harbor.json", "w") as f:
            json.dump(
                {
                    "trials": [
                        {
                            "trial_id": "rdkit_001__trial-0",
                            "result": {"success": True, "score": 1.0},
                        }
                    ]
                },
                f,
            )

        recovery_trial = recovery_job / "trials" / "rdkit_001__trial-0"
        recovery_trial.mkdir(parents=True)
        with open(recovery_trial / "result.json", "w") as f:
            json.dump({"outcome": "success", "score": 1.0}, f)
        (recovery_trial / "agent.log").write_text("Recovery succeeded")
        (recovery_trial / "solution.txt").write_text("Fixed solution")

        # Phase 3: Merge
        merged_dir = tmp_path / "merged"
        merger = ResultMerger(
            original_run_dir=sample_run_dir,
            recovery_dirs=[recovery_dir],
            output_dir=merged_dir,
        )

        merge_result = merger.merge()

        # Verify merge results
        assert merge_result.merged_slots == 1
        assert len(merge_result.conflicts) == 0

        # Verify merged structure
        merged_trial = (
            merged_dir / "jobs" / "openclaw-opus" / "trials" / "rdkit_001__trial-0"
        )
        assert merged_trial.exists()
        assert (merged_trial / "recovery-marker.json").exists()

        # Verify backup exists
        backup_trial = (
            merged_dir
            / "jobs"
            / "openclaw-opus"
            / "trials"
            / "rdkit_001__trial-0__replaced"
        )
        assert backup_trial.exists()

        # Verify recovery result is in place
        with open(merged_trial / "result.json") as f:
            result = json.load(f)
            assert result["outcome"] == "success"
            assert result["score"] == 1.0

        # Verify original result is backed up
        with open(backup_trial / "result.json") as f:
            result = json.load(f)
            assert result["outcome"] == "error"

    def test_workflow_no_failures(self, tmp_path: Path) -> None:
        """Test workflow with run that has no failures."""
        # Create run with only successful trials
        run_dir = tmp_path / "success-run"
        run_dir.mkdir()

        jobs_dir = run_dir / "jobs"
        jobs_dir.mkdir()

        job_dir = jobs_dir / "openclaw-opus"
        job_dir.mkdir()

        # Job config
        with open(job_dir / "config.json", "w") as f:
            json.dump({"task_id": "rdkit_001", "job_name": "openclaw-opus"}, f)

        # Harbor metadata with successful trial
        with open(job_dir / "harbor.json", "w") as f:
            json.dump(
                {
                    "trials": [
                        {
                            "trial_id": "rdkit_001__trial-0",
                            "result": {"success": True, "score": 1.0},
                        }
                    ]
                },
                f,
            )

        trials_dir = job_dir / "trials"
        trials_dir.mkdir()

        trial_dir = trials_dir / "rdkit_001__trial-0"
        trial_dir.mkdir()

        # Audit should find no failures
        manifest = audit_run(
            run_dir=run_dir,
            run_name="success-run",
        )

        assert len(manifest.slots) == 0

    def test_workflow_multiple_recovery_passes(
        self,
        sample_run_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Test multiple recovery passes for persistent failures."""
        # First audit
        manifest1 = audit_run(
            run_dir=sample_run_dir,
            run_name="sample-run",
        )
        manifest1.approve_all_substitutable()

        # First recovery (fails)
        recovery1_dir = tmp_path / "recovery-pass-1"
        recovery1_dir.mkdir()
        manifest1.save(recovery1_dir / "recovery-manifest.json")

        jobs_dir = recovery1_dir / "jobs"
        jobs_dir.mkdir()

        recovery_job = jobs_dir / "openclaw-opus-recovery-1"
        recovery_job.mkdir()

        approved = manifest1.get_approved_slots()

        # Job config
        with open(recovery_job / "config.json", "w") as f:
            json.dump({"task_id": "rdkit_001", "job_name": "openclaw-opus-recovery-1"}, f)

        # Recovery metadata
        with open(recovery_job / "recovery-metadata.json", "w") as f:
            json.dump(
                {
                    "slot_id": approved[0].slot_id,
                    "original_job_name": "openclaw-opus",
                    "task_id": "rdkit_001",
                    "substitution_count": 0,  # This is the first recovery attempt
                },
                f,
            )

        # Harbor metadata with failed trial
        with open(recovery_job / "harbor.json", "w") as f:
            json.dump(
                {
                    "trials": [
                        {
                            "trial_id": "rdkit_001__trial-0",
                            "exception_info": {
                                "exception_type": "DockerException",
                                "exception_message": "Still failing",
                            },
                            "result": None,
                        }
                    ]
                },
                f,
            )

        # First recovery fails
        trial_dir = recovery_job / "trials" / "rdkit_001__trial-0"
        trial_dir.mkdir(parents=True)
        with open(trial_dir / "result.json", "w") as f:
            json.dump({"outcome": "error", "error": "Still failing"}, f)

        # Second audit (of recovery run)
        manifest2 = audit_run(
            run_dir=recovery1_dir,
            run_name="recovery-pass-1",
        )
        manifest2.approve_all_substitutable()

        # Should detect the failed recovery
        assert len(manifest2.slots) == 1
        assert manifest2.slots[0].substitution_count == 1

        # Verify can still substitute (limit is 2)
        assert manifest2.slots[0].can_substitute

    def test_report_generation(
        self,
        tmp_path: Path,
    ) -> None:
        """Test that analysis report contains expected sections."""
        # Create minimal recovery run
        recovery_dir = tmp_path / "recovery"
        recovery_dir.mkdir()

        manifest = RecoveryManifest(
            run_name="test",
            run_category=None,
            created_at=datetime.now(),
            slots=[],
        )
        manifest.save(recovery_dir / "recovery-manifest.json")

        # Generate report
        analyzer = RecoveryAnalyzer(run_dir=recovery_dir)
        report = analyzer.generate_report()

        # Verify report structure
        assert "Recovery Analysis Report" in report
        assert "Failure Overview" in report
        assert "Recovery Execution" in report
        assert "Top Failure Reasons" in report

    def test_stats_serialization_round_trip(
        self,
        sample_run_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Test that stats can be serialized and used for reporting."""
        # Create recovery run
        manifest = audit_run(
            run_dir=sample_run_dir,
            run_name="sample-run",
        )
        manifest.approve_all_substitutable()

        recovery_dir = tmp_path / "recovery"
        recovery_dir.mkdir()
        manifest.save(recovery_dir / "recovery-manifest.json")

        # Generate stats
        analyzer = RecoveryAnalyzer(run_dir=recovery_dir)
        stats = analyzer.analyze()

        # Serialize
        stats_dict = stats.to_dict()
        stats_json = json.dumps(stats_dict)

        # Verify can deserialize
        reloaded = json.loads(stats_json)
        assert reloaded["total_failures"] == stats.total_failures
        assert reloaded["engineering_failures"] == stats.engineering_failures
        assert reloaded["recovery_rate"] == stats.recovery_rate
