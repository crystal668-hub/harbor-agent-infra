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
            with patch.object(executor, "_load_original_job_config") as mock_load_config:
                mock_load_config.return_value = JobConfig(
                    job_name="test-job",
                    jobs_dir=tmp_path / "jobs",
                    tasks=[{"name": "rdkit_001"}],
                    agents=[{"harness": "openclaw"}],
                    verifier={"image": "test:latest"},
                    n_attempts=1,
                )

                result = await executor.execute()

            assert result.executed == result.succeeded == 1
            mock_job.run.assert_awaited_once()

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


@pytest.fixture
def native_recovery(tmp_path, mock_run_config, sample_manifest):
    """One native group Job contains two failed tasks and one successful task."""
    original = tmp_path / "formal" / "native-run"
    job_dir = original / "jobs" / "native-run-skills_off"
    job_dir.mkdir(parents=True)
    tasks = [{"path": tmp_path / "tasks" / f"track__task-{i}"} for i in range(3)]
    snapshot = JobConfig(
        job_name=job_dir.name,
        jobs_dir=job_dir.parent,
        tasks=tasks,
        agents=[
            {
                "name": "claude-code",
                "model_name": "fixture-model",
                "kwargs": {"version": "2.1.296", "reasoning_effort": "high"},
                "env": {"ANTHROPIC_API_KEY": "${FIXTURE_PROVIDER_KEY}"},
            }
        ],
        environment={"override_cpus": 4, "override_memory_mb": 6144},
        retry={"max_retries": 0},
        n_attempts=1,
        n_concurrent_trials=2,
    )
    (job_dir / "config.json").write_text(snapshot.model_dump_json())
    first = sample_manifest.slots[0]
    slots = [
        RecoverySlot(
            job_name=job_dir.name,
            task_id=f"track__task-{i}",
            original_trial_id=f"trial-{i}",
            failure_classification=first.failure_classification,
            original_run="unknown",  # Historical manifests omitted the original run.
            approved=True,
        )
        for i in range(2)
    ]
    manifest = RecoveryManifest(
        run_name=original.name,
        run_category=RunCategory.FORMAL,
        created_at=datetime.now(),
        slots=slots,
    )
    mock_run_config.run.output_dir = str(original)
    executor = RecoveryExecutor(manifest, mock_run_config, tmp_path / "recovery")
    return executor, snapshot, original


@pytest.mark.asyncio
@pytest.mark.parametrize("use_manifest_dir", [False, True])
async def test_native_recovery_loads_snapshot_and_runs_each_failed_task_once(
    native_recovery, use_manifest_dir
):
    executor, snapshot, original = native_recovery
    snapshot_path = original / "jobs" / snapshot.job_name / "config.json"
    original_bytes = snapshot_path.read_bytes()
    if use_manifest_dir:
        executor.manifest.metadata["run_dir"] = str(original)
        executor.run_config.run.output_dir = str(original.parent / "different-run")

    jobs = [AsyncMock(), AsyncMock()]
    for job in jobs:
        job.run.return_value = MagicMock(stats=MagicMock(n_errored_trials=0, n_cancelled_trials=0))
    with patch("harbor_agent_infra.recovery.executor.Job.create", new_callable=AsyncMock) as create:
        create.side_effect = jobs
        result = await executor.execute()

    assert result.executed == result.succeeded == 2
    assert result.skipped == result.failed == 0
    configs = [call.args[0] for call in create.await_args_list]
    assert len({config.job_name for config in configs}) == 2
    for i, config in enumerate(configs):
        assert config.tasks == [snapshot.tasks[i]]
        for field in (
            "agents",
            "environment",
            "verifier",
            "retry",
            "n_attempts",
            "n_concurrent_trials",
        ):
            assert getattr(config, field) == getattr(snapshot, field)
        jobs[i].run.assert_awaited_once()
        metadata_path = config.jobs_dir / config.job_name / "recovery-metadata.json"
        metadata = json.loads(metadata_path.read_text())
        assert metadata["slot_id"] == executor.manifest.slots[i].slot_id
        assert metadata["original_run"] == executor.manifest.run_name
        assert metadata["substitution_attempt"] == 1
    assert snapshot_path.read_bytes() == original_bytes


@pytest.mark.asyncio
@pytest.mark.parametrize("task_id", ["missing-task", "task-0"])
async def test_recovery_rejects_unmatched_or_partial_task_name(native_recovery, task_id):
    executor, _, _ = native_recovery
    executor.manifest.slots[0].task_id = task_id
    with patch("harbor_agent_infra.recovery.executor.Job.create", new_callable=AsyncMock) as create:
        result = await executor._execute_slot(executor.manifest.slots[0])
    assert result.executed is False
    assert "Expected one matching explicit task" in result.error
    create.assert_not_awaited()


def test_recover_dry_run_validates_snapshots_without_creating_jobs(
    native_recovery, tmp_path, monkeypatch, capsys
):
    from harbor_agent_infra.cli import main

    executor, _, _ = native_recovery
    manifest_path = tmp_path / "manifest.json"
    executor.manifest.save(manifest_path)
    monkeypatch.setattr("harbor_agent_infra.cli.load_run_config", lambda _: executor.run_config)
    with patch("harbor_agent_infra.recovery.executor.Job.create", new_callable=AsyncMock) as create:
        assert (
            main(
                [
                    "recover",
                    str(manifest_path),
                    "--config",
                    "original.yaml",
                    "--output-dir",
                    str(executor.output_dir),
                    "--dry-run",
                ]
            )
            == 0
        )
    assert capsys.readouterr().out.count("Validated Job:") == 2
    assert not executor.output_dir.exists()
    create.assert_not_awaited()


def test_recover_dry_run_fails_when_snapshot_is_missing(
    native_recovery, tmp_path, monkeypatch, capsys
):
    from harbor_agent_infra.cli import main

    executor, snapshot, original = native_recovery
    (original / "jobs" / snapshot.job_name / "config.json").unlink()
    manifest_path = tmp_path / "manifest.json"
    executor.manifest.save(manifest_path)
    monkeypatch.setattr("harbor_agent_infra.cli.load_run_config", lambda _: executor.run_config)
    with patch("harbor_agent_infra.recovery.executor.Job.create", new_callable=AsyncMock) as create:
        assert (
            main(
                [
                    "recover",
                    str(manifest_path),
                    "--config",
                    "original.yaml",
                    "--output-dir",
                    str(executor.output_dir),
                    "--dry-run",
                ]
            )
            == 1
        )
    assert "Could not load original job config" in capsys.readouterr().out
    assert not executor.output_dir.exists()
    create.assert_not_awaited()


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


@pytest.mark.asyncio
async def test_recovery_uses_two_shared_slots_and_preserves_input_order(native_recovery):
    import asyncio

    executor, _, _ = native_recovery
    first = executor.manifest.slots[0]
    for index in range(2, 5):
        executor.manifest.slots.append(
            RecoverySlot(
                job_name=first.job_name,
                task_id=f"extra-{index}",
                original_trial_id=f"trial-{index}",
                failure_classification=first.failure_classification,
                original_run=first.original_run,
                approved=True,
            )
        )
    active = 0
    peak = 0
    pair_started = asyncio.Event()

    async def run_slot(slot):
        nonlocal active, peak
        from harbor_agent_infra.recovery.executor import SlotExecutionResult

        active += 1
        peak = max(peak, active)
        if active == 2:
            pair_started.set()
        await asyncio.wait_for(pair_started.wait(), 1)
        await asyncio.sleep(0)
        active -= 1
        return SlotExecutionResult(
            slot.slot_id,
            slot.job_name,
            slot.task_id,
            True,
            slot is not first,
            error="fixture failure" if slot is first else None,
        )

    with patch.object(executor, "_execute_slot", side_effect=run_slot):
        result = await executor.execute()
    assert peak == 2
    assert result.executed == 5 and result.failed == 1 and result.succeeded == 4
    assert [r.slot_id for r in result.slot_results] == [s.slot_id for s in executor.manifest.slots]
    state = json.loads((executor.output_dir / "recovery-state.json").read_text())
    assert state["status"] == "finished" and state["concurrency"] == 2
    with pytest.raises(FileExistsError):
        await executor.execute()


@pytest.mark.asyncio
async def test_recovery_cancellation_waits_for_active_cleanup(native_recovery):
    import asyncio

    executor, _, _ = native_recovery
    entered = asyncio.Event()
    active = 0
    cleaned = []

    async def run_slot(slot):
        nonlocal active
        active += 1
        if active == 2:
            entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            cleaned.append(slot.slot_id)

    with patch.object(executor, "_execute_slot", side_effect=run_slot):
        task = asyncio.create_task(executor.execute())
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert len(cleaned) == 2
    state = json.loads((executor.output_dir / "recovery-state.json").read_text())
    assert state["status"] == "interrupted"
    assert set(state["slots"].values()) == {"interrupted"}
