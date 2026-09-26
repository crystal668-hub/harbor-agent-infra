from __future__ import annotations

import asyncio
import json
import subprocess
import time
from pathlib import Path

import pytest
import yaml
from harbor import Job, JobConfig

from adapters.fake_agent import FakeAgent

pytestmark = pytest.mark.integration


def _config(
    tmp_path: Path,
    *,
    behavior: str,
    retries: int = 0,
    timeout_sec: float | None = None,
    memory_mb: int = 512,
    allocation_mb: int = 1024,
    n_attempts: int = 1,
    n_concurrent_trials: int = 1,
    sleep_seconds: float = 30.0,
) -> JobConfig:
    raw = yaml.safe_load(Path("scripts/fake-agent-job.yaml").read_text())
    raw["job_name"] = f"lifecycle-{behavior}"
    raw["jobs_dir"] = str(tmp_path / "jobs")
    raw["n_attempts"] = n_attempts
    raw["n_concurrent_trials"] = n_concurrent_trials
    raw["retry"] = {"max_retries": retries, "min_wait_sec": 0}
    raw["environment"]["override_memory_mb"] = memory_mb
    raw["agents"][0]["kwargs"] = {
        "behavior": behavior,
        "allocation_mb": allocation_mb,
        "sleep_seconds": sleep_seconds,
    }
    if timeout_sec is not None:
        raw["agents"][0]["override_timeout_sec"] = timeout_sec
    return JobConfig.model_validate(raw)


async def _run(config: JobConfig):
    FakeAgent.clear_lifecycle_events()
    job = await Job.create(config)
    return job, await job.run()


def test_nonzero_exit_is_recorded_as_trial_error(tmp_path: Path) -> None:
    _, result = asyncio.run(_run(_config(tmp_path, behavior="nonzero")))
    trial = result.trial_results[0]
    assert trial.exception_info is not None
    assert trial.exception_info.exception_type == "RuntimeError"
    assert result.stats.n_errored_trials == 1


def test_agent_timeout_is_recorded_and_not_retried(tmp_path: Path) -> None:
    _, result = asyncio.run(
        _run(
            _config(
                tmp_path,
                behavior="sleep",
                timeout_sec=1,
                retries=1,
                sleep_seconds=10,
            )
        )
    )
    trial = result.trial_results[0]
    assert trial.exception_info is not None
    assert trial.exception_info.exception_type == "AgentTimeoutError"
    assert result.stats.n_retries == 0


def test_memory_limit_failure_is_recorded(tmp_path: Path) -> None:
    _, result = asyncio.run(
        _run(
            _config(
                tmp_path,
                behavior="memory",
                memory_mb=64,
                allocation_mb=256,
            )
        )
    )
    trial = result.trial_results[0]
    assert trial.exception_info is not None
    assert trial.exception_info.exception_type == "RuntimeError"


def test_retry_creates_new_trial_context_and_cleans_attempt(tmp_path: Path) -> None:
    _, result = asyncio.run(
        _run(_config(tmp_path, behavior="fail_once", retries=1))
    )
    assert result.stats.n_retries == 1
    assert len(FakeAgent.lifecycle_events) == 2
    assert len({event["trial_id"] for event in FakeAgent.lifecycle_events}) == 2
    assert result.trial_results[0].exception_info is None
    trial_results = list((tmp_path / "jobs").rglob("result.json"))
    assert len(trial_results) == 2


def test_concurrent_trials_overlap(tmp_path: Path) -> None:
    started = time.monotonic()
    _, result = asyncio.run(
        _run(
            _config(
                tmp_path,
                behavior="sleep",
                sleep_seconds=1,
                n_attempts=2,
                n_concurrent_trials=2,
            )
        )
    )
    elapsed = time.monotonic() - started
    events = FakeAgent.lifecycle_events
    assert len(result.trial_results) == 2
    assert len(events) == 2
    assert abs(float(events[0]["started_at"]) - float(events[1]["started_at"])) < 1.5
    assert elapsed < 15


def test_cancellation_persists_cancelled_trial_and_removes_container(tmp_path: Path) -> None:
    async def cancel_job() -> tuple[Path, str]:
        FakeAgent.clear_lifecycle_events()
        config = _config(tmp_path, behavior="sleep", sleep_seconds=60)
        job = await Job.create(config)
        started = asyncio.Event()

        async def on_agent_started(_event) -> None:
            started.set()

        job.on_agent_started(on_agent_started)
        running = asyncio.create_task(job.run())
        await asyncio.wait_for(started.wait(), timeout=30)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        result_path = next(
            path
            for path in (tmp_path / "jobs").rglob("result.json")
            if "exception_info" in json.loads(path.read_text())
        )
        return result_path, FakeAgent.lifecycle_events[0]["environment_session_id"]

    result_path, environment_session_id = asyncio.run(cancel_job())
    result = json.loads(result_path.read_text())
    assert result["exception_info"] is not None
    assert result["exception_info"]["exception_type"] == "CancelledError"
    containers = subprocess.run(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            f"label=com.docker.compose.project={environment_session_id}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert not containers.stdout.strip()
