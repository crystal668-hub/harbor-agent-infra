from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path

import pytest
import yaml
from harbor import Job, JobConfig

from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock

pytestmark = pytest.mark.integration


async def _run_native_install() -> None:
    if os.environ.get("RUN_OPENCLAW_NATIVE_INSTALL") != "1":
        pytest.skip("set RUN_OPENCLAW_NATIVE_INSTALL=1 to run the networked npm install gate")

    raw = yaml.safe_load(Path("scripts/fake-agent-job.yaml").read_text(encoding="utf-8"))
    lock = load_runtime_lock(Path("runtime-lock.json"))
    task_root = Path(tempfile.mkdtemp(prefix="openclaw-native-task-"))
    shutil.copytree("tests/fixtures/fake-agent/task", task_root, dirs_exist_ok=True)
    task_config = task_root / "task.toml"
    fixture_image = (
        "docker_image = \"hai-fake-agent@sha256:"
        "197902e2ec6c47c8ac10fa0656fec7d548e0e9b69a9d7926fdb9b1986434eab1\""
    )
    task_config.write_text(
        task_config.read_text(encoding="utf-8").replace(
            fixture_image,
            f'docker_image = "{lock.agent_base_image.immutable_reference}"',
        ),
        encoding="utf-8",
    )
    raw.update(
        {
            "job_name": "openclaw-native-install",
            "jobs_dir": str(task_root / "jobs"),
            "install_only": True,
            "tasks": [{"path": str(task_root)}],
            "agents": [
                {
                    "import_path": "adapters.openclaw.adapter:OpenClawAgent",
                    "model_name": "openai/fixture-model",
                    "kwargs": {"version": "2026.6.34"},
                }
            ],
        }
    )
    config = JobConfig.model_validate(raw)
    job = await Job.create(config)
    result = await job.run()
    trial = result.trial_results[0]
    assert trial.exception_info is None
    assert trial.agent_info.version == "2026.6.34"


def test_harbor_native_openclaw_install_only() -> None:
    asyncio.run(_run_native_install())
