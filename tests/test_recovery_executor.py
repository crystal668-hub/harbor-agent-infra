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


@pytest.fixture
def changed_condition(native_recovery, tmp_path):
    import hashlib

    import yaml

    from harbor_agent_infra.contracts.experiment import ExperimentSpecV2
    from harbor_agent_infra.harness_runner import harness_runner_for
    from harbor_agent_infra.preparation.experiments import experiment_sha256
    from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock

    executor, original, _ = native_recovery
    lock_path = Path("runtime-lock.preinstalled.json").resolve()
    lock = load_runtime_lock(lock_path)
    raw = yaml.safe_load(Path("examples/experiments/claude-code/vgb-qwen.config.yaml").read_text())
    exp = raw["experiment"]
    exp["agent"] = {
        "adapter": "claude-code", "model": "fixture-model",
        "reasoning_effort": "high", "installation_mode": "preinstalled",
    }
    exp["benchmark"]["package_lock"] = str(lock_path)
    exp["groups"] = [{"id": "skills_off", "label": "off", "skills_enabled": False}]
    spec = ExperimentSpecV2.model_validate(exp)
    image = lock.execution_image("claude-code", "preinstalled")
    spec = spec.model_copy(update={"image": spec.image.model_copy(update={
        "reference": image.reference, "digest": image.digest,
        "platform": image.platform, "pull_policy": "never",
    })})
    executor.run_config.experiment = spec
    target = original.model_dump(mode="json")
    target["tasks"] = target["tasks"][:2]
    target["agents"][0]["name"] = None
    expected = harness_runner_for("claude-code").build_agent_config(spec.agent, lock)
    target["agents"][0]["import_path"] = expected.import_path
    target["agents"][0]["kwargs"]["preinstalled"] = expected.kwargs["preinstalled"]
    for task in target["tasks"]:
        before = Path(task["path"])
        after = tmp_path / "preinstalled-tasks" / before.name
        for directory in (before, after):
            directory.mkdir(parents=True)
            (directory / "instruction.md").write_text("fixed public instruction")
        (before / "task.toml").write_text(
            '[agent]\ntimeout_sec=7200\n[environment]\ndocker_image="old@sha256:fixture"\n'
        )
        (after / "task.toml").write_text(
            '[agent]\ntimeout_sec=7200\n[environment]\n'
            f'docker_image="{image.immutable_reference}"\n'
        )
        task["path"] = str(after)
    snapshot = tmp_path / "materialized.json"
    payload = {"experiment_sha256": experiment_sha256(spec),
               "groups": {"skills_off": {"job_config": target}}}
    snapshot.write_text(json.dumps(payload))
    change = {
        "schema_version": "preinstalled-condition-change.v1",
        "condition_id": "fixture-preinstalled",
        "authorization": "User approved preinstalled execution as a new condition",
        "task_names": [s.task_id for s in executor.manifest.slots],
        "runtime_lock": str(lock_path),
        "runtime_lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        "materialized_snapshot": str(snapshot),
        "materialized_snapshot_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
    }
    executor.manifest.metadata["condition_change"] = change
    return executor, original, snapshot


@pytest.mark.asyncio
async def test_explicit_condition_change_uses_preinstalled_tasks_and_records_provenance(
    changed_condition,
):
    executor, original, _ = changed_condition
    jobs = [AsyncMock(), AsyncMock()]
    for job in jobs:
        job.run.return_value = MagicMock(stats=MagicMock(n_errored_trials=0, n_cancelled_trials=0))
    with patch("harbor_agent_infra.recovery.executor.Job.create", new_callable=AsyncMock) as create:
        create.side_effect = jobs
        result = await executor.execute()
    assert result.succeeded == 2
    for call in create.await_args_list:
        config = call.args[0]
        assert config.agents[0].import_path == "adapters.preinstalled:ClaudeCodeAgent"
        assert "preinstalled-tasks" in str(config.tasks[0].path)
        assert config.environment == original.environment
        metadata = json.loads(
            (config.jobs_dir / config.job_name / "recovery-metadata.json").read_text()
        )
        assert metadata["condition_change"]["condition_id"] == "fixture-preinstalled"
        assert metadata["statistical_role"] == "new_condition_observation"


@pytest.mark.asyncio
async def test_preinstalled_image_change_preserves_other_agent_settings(changed_condition):
    executor, original, snapshot = changed_condition
    target = json.loads(snapshot.read_text())["groups"]["skills_off"]["job_config"]
    old = original.model_dump(mode="json")
    old_agent = old["agents"][0]
    old_agent["name"] = None
    old_agent["import_path"] = target["agents"][0]["import_path"]
    old_agent["kwargs"]["preinstalled"] = {
        **target["agents"][0]["kwargs"]["preinstalled"],
        "image": "old@sha256:fixture",
    }
    frozen = JobConfig.model_validate(old)
    change = executor.manifest.metadata["condition_change"]
    change["previous_condition"] = {
        "installation_mode": "preinstalled", "image": "old@sha256:fixture",
    }
    change["target_condition"] = {
        "installation_mode": "preinstalled",
        "image": target["agents"][0]["kwargs"]["preinstalled"]["image"],
    }
    with patch.object(executor, "_load_original_job_config",
                      new=AsyncMock(return_value=frozen)):
        job = await executor.prepare_job_config(executor.manifest.slots[0])
        assert job.agents[0].kwargs["preinstalled"] == (
            target["agents"][0]["kwargs"]["preinstalled"]
        )
        change["previous_condition"]["image"] = "other@sha256:fixture"
        with pytest.raises(ValueError, match="frozen preinstalled image transition"):
            await executor.prepare_job_config(executor.manifest.slots[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["hash", "model", "resources", "prompt", "timeout", "scope"])
async def test_condition_change_rejects_unapproved_drift_before_launch(changed_condition, fault):
    import hashlib

    executor, _, path = changed_condition
    payload = json.loads(path.read_text())
    job = payload["groups"]["skills_off"]["job_config"]
    if fault == "model":
        job["agents"][0]["model_name"] = "other-model"
    elif fault == "resources":
        job["environment"]["override_cpus"] = 100
    elif fault == "scope":
        job["tasks"] = job["tasks"][:1]
    elif fault in ("prompt", "timeout"):
        task = Path(job["tasks"][1]["path"])
        name = "instruction.md" if fault == "prompt" else "task.toml"
        f = task / name
        f.write_text(f.read_text().replace("7200", "14400") if fault == "timeout" else "changed")
    path.write_text(json.dumps(payload) + ("\n" if fault == "hash" else ""))
    if fault != "hash":
        executor.manifest.metadata["condition_change"]["materialized_snapshot_sha256"] = (
            hashlib.sha256(path.read_bytes()).hexdigest()
        )
    with patch("harbor_agent_infra.recovery.executor.Job.create", new_callable=AsyncMock) as create:
        with pytest.raises(ValueError, match="Condition change"):
            await executor.execute()
    create.assert_not_awaited()
    assert not executor.output_dir.exists()


@pytest.mark.asyncio
async def test_explicit_single_concurrency_serializes_recovery_and_preserves_jobs(native_recovery):
    import asyncio

    from harbor_agent_infra.recovery.executor import SlotExecutionResult

    executor, original, _ = native_recovery
    executor.manifest.metadata['batch_concurrency'] = 1
    before = original.model_dump(mode='json')
    assert await executor.concurrency_limit() == 1
    for slot in executor.manifest.get_approved_slots():
        job = await executor.prepare_job_config(slot)
        assert job.n_concurrent_trials == 1
        assert job.agents == original.agents
        assert job.environment == original.environment
        assert job.retry == original.retry
        assert job.verifier == original.verifier
    active = peak = 0

    async def run_slot(slot):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return SlotExecutionResult(slot.slot_id, slot.job_name, slot.task_id, True, True)

    with patch.object(executor, '_execute_slot', side_effect=run_slot):
        result = await executor.execute()
    assert peak == 1 and result.executed == 2
    assert original.model_dump(mode='json') == before
    state = json.loads((executor.output_dir / 'recovery-state.json').read_text())
    assert state['concurrency'] == 1
    saved = RecoveryManifest.load(executor.output_dir / 'recovery-manifest.json')
    assert saved.metadata['batch_concurrency'] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [0, -1, 3, True, '1', 1.5, None])
async def test_batch_concurrency_rejects_invalid_or_increased_limit(native_recovery, value):
    executor, _, _ = native_recovery
    executor.manifest.metadata['batch_concurrency'] = value
    with pytest.raises(ValueError, match='batch_concurrency'):
        await executor.concurrency_limit()
    with pytest.raises(ValueError, match='batch_concurrency'):
        await executor.prepare_job_config(executor.manifest.slots[0])
    with patch.object(executor, '_execute_slot', new_callable=AsyncMock) as run_slot:
        with pytest.raises(ValueError, match='batch_concurrency'):
            await executor.execute()
        run_slot.assert_not_called()
    assert not executor.output_dir.exists()


@pytest.mark.asyncio
async def test_single_concurrency_is_recorded_in_job_provenance(native_recovery):
    executor, _, _ = native_recovery
    executor.manifest.metadata['batch_concurrency'] = 1
    job = AsyncMock()
    job.run.return_value = MagicMock(stats=MagicMock(n_errored_trials=0, n_cancelled_trials=0))
    with patch('harbor_agent_infra.recovery.executor.Job.create', new_callable=AsyncMock) as create:
        create.return_value = job
        result = await executor.execute()
    assert result.succeeded == 2
    for call in create.await_args_list:
        config = call.args[0]
        assert config.n_concurrent_trials == 1
        metadata_path = config.jobs_dir / config.job_name / 'recovery-metadata.json'
        meta = json.loads(metadata_path.read_text())
        assert meta['batch_concurrency'] == 1
