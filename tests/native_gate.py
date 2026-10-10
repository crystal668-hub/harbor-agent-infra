"""Real Harbor gates for the two built-in CLI agents; no provider calls on import."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest
from harbor import Job, JobConfig

from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock


def run_install_gate(agent_name: str, gate: str) -> None:
    if os.environ.get(gate) != "1":
        pytest.skip(f"set {gate}=1 to run the networked install gate")
    asyncio.run(_install(agent_name))


async def _install(agent_name: str) -> None:
    lock = load_runtime_lock(Path("runtime-lock.json"))
    version = lock.codex.version if agent_name == "codex" else lock.claude_code.version
    root = Path(tempfile.mkdtemp(prefix=f"hai-{agent_name}-install-"))
    task = root / "task"
    (task / "environment").mkdir(parents=True)
    (task / "tests").mkdir()
    (task / "instruction.md").write_text("Install only.\n")
    (task / "tests/test.sh").write_text("#!/bin/sh\nexit 0\n")
    (task / "task.toml").write_text(
        'schema_version = "1.4"\n[environment]\n'
        f'docker_image = "{lock.agent_base_image.immutable_reference}"\n'
    )
    config = JobConfig.model_validate(
        {
            "job_name": f"{agent_name}-install",
            "jobs_dir": str(root / "jobs"),
            "install_only": True,
            "quiet": True,
            "n_attempts": 1,
            "n_concurrent_trials": 1,
            "retry": {"max_retries": 0},
            "environment": {
                "type": "docker",
                "delete": True,
                "override_cpus": 2,
                "override_memory_mb": 4096,
                "cpu_enforcement_policy": "limit",
                "memory_enforcement_policy": "limit",
            },
            "agents": [
                {
                    "name": agent_name,
                    "model_name": "fixture-model",
                    "override_setup_timeout_sec": 1200,
                    "kwargs": {"version": version},
                }
            ],
            "tasks": [{"path": str(task)}],
        }
    )
    assert config.agents[0].name == agent_name
    assert config.agents[0].import_path is None
    result = await (await Job.create(config)).run()
    trial = result.trial_results[0]
    assert trial.exception_info is None, f"Install failed; inspect {root}"
    assert trial.agent_info.version == version
    (root / "report.json").write_text(
        json.dumps(
            {
                "agent": agent_name,
                "version": version,
                "status": "pass",
            }
        )
    )
