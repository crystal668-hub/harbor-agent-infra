"""Provider-free Docker checks; never compete with an existing experiment container."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from harbor import Job, JobConfig

from adapters.fake_agent import FakeAgent
from harbor_agent_infra.contracts.failure_types import FailureCategory, FailureClassification
from harbor_agent_infra.recovery.executor import RecoveryExecutor
from harbor_agent_infra.recovery.manifest import RecoveryManifest, RecoverySlot

pytestmark = pytest.mark.integration


def docker_fixture(tmp_path):
    if shutil.which("docker") is None:
        pytest.skip("Docker unavailable")
    check = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True)
    if check.returncode:
        pytest.skip("Docker unavailable")
    if check.stdout.strip():
        pytest.skip("Existing experiment containers are running; preserve their resources")
    config = yaml.safe_load(Path("scripts/fake-agent-job.yaml").read_text())
    image = subprocess.run(
        ["docker", "image", "inspect", "hai-fake-agent:acceptance"], capture_output=True
    )
    if image.returncode:
        pytest.skip("Build the existing fake-agent acceptance image before this test")
    original = tmp_path / "original"
    tasks = []
    for i in range(3):
        target = original / "tasks" / f"fixture-{i}"
        shutil.copytree("tests/fixtures/fake-agent/task", target)
        tasks.append({"path": str(target)})
    config.update(
        job_name="fixture-job",
        jobs_dir=str(original / "jobs"),
        tasks=tasks,
        n_attempts=1,
        n_concurrent_trials=2,
        retry={"max_retries": 0},
    )
    config["agents"][0]["kwargs"] = {"behavior": "sleep", "sleep_seconds": 3}
    frozen = JobConfig.model_validate(config)
    path = original / "jobs/fixture-job/config.json"
    path.parent.mkdir(parents=True)
    path.write_text(frozen.model_dump_json())
    classification = FailureClassification(FailureCategory.ENGINEERING, "fixture", True, {})
    slots = [
        RecoverySlot(
            "fixture-job",
            f"fixture-{i}",
            f"original-{i}",
            classification,
            original_run="original",
            approved=True,
        )
        for i in range(3)
    ]
    manifest = RecoveryManifest("original", None, datetime.now(), slots)
    executor = RecoveryExecutor(
        manifest,
        SimpleNamespace(run=SimpleNamespace(output_dir=str(original))),
        tmp_path / "recovery",
    )
    return executor


@pytest.mark.parametrize("cancel", [False, True])
def test_recovery_two_containers_and_cancellation_cleanup(tmp_path, monkeypatch, cancel):
    executor = docker_fixture(tmp_path)
    FakeAgent.clear_lifecycle_events()
    actual_create = Job.create
    active = 0
    peak = 0
    two_started = asyncio.Event()

    async def create(config):
        job = await actual_create(config)

        async def started(event):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if active == 2:
                two_started.set()

        async def ended(event):
            nonlocal active
            active -= 1

        job.on_agent_started(started)
        job.on_trial_ended(ended)
        return job

    monkeypatch.setattr("harbor_agent_infra.recovery.executor.Job.create", create)

    async def execute():
        task = asyncio.create_task(executor.execute())
        try:
            await asyncio.wait_for(two_started.wait(), 60)
            if cancel:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                result = await asyncio.wait_for(task, 60)
                assert result.executed == result.succeeded == 3
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(execute())
    assert peak == 2
    for event in FakeAgent.lifecycle_events:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                f"label=com.docker.compose.project={event['environment_session_id']}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        assert not result.stdout.strip()
    state = json.loads((executor.output_dir / "recovery-state.json").read_text())
    assert state["status"] == ("interrupted" if cancel else "finished")
