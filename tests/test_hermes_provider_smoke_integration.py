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

_MARKER = "HARBOR_HERMES_SMOKE_OK"


async def _run_provider_smoke() -> None:
    if os.environ.get("RUN_HERMES_PROVIDER_SMOKE") != "1":
        pytest.skip("set RUN_HERMES_PROVIDER_SMOKE=1 to run the provider-backed gate")
    if not os.environ.get("QWEN_API_KEY") or not os.environ.get("QWEN_BASE_URL"):
        pytest.skip("QWEN_API_KEY and QWEN_BASE_URL are required for the configured model")

    model = os.environ.get("OPENCLAW_MODEL")
    if not model or not model.startswith("qwen/"):
        raise RuntimeError("OPENCLAW_MODEL must select the configured qwen provider")

    raw = yaml.safe_load(Path("scripts/fake-agent-job.yaml").read_text(encoding="utf-8"))
    lock = load_runtime_lock(Path("runtime-lock.json"))
    task_root = Path(tempfile.mkdtemp(prefix="hermes-provider-smoke-"))
    shutil.copytree("tests/fixtures/fake-agent/task", task_root, dirs_exist_ok=True)
    task_config = task_root / "task.toml"
    task_config.write_text(
        task_config.read_text(encoding="utf-8").replace(
            "hai-fake-agent@sha256:197902e2ec6c47c8ac10fa0656fec7d548e0e9b69a9d7926fdb9b1986434eab1",
            lock.agent_base_image.immutable_reference,
        ),
        encoding="utf-8",
    )
    (task_root / "instruction.md").write_text(
        f"Reply with exactly {_MARKER} and nothing else.\n", encoding="utf-8"
    )
    (task_root / "tests/test.sh").write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "test -s /logs/agent/hermes.txt\n"
        f"grep -q '{_MARKER}' /logs/agent/hermes.txt\n"
        "printf '1\\n' > /logs/verifier/reward.txt\n",
        encoding="utf-8",
    )
    (task_root / "tests/test.sh").chmod(0o755)
    raw.update(
        {
            "job_name": "hermes-provider-smoke",
            "jobs_dir": str(task_root / "jobs"),
            "n_attempts": 1,
            "retry": {"max_retries": 0},
            "tasks": [{"path": str(task_root)}],
            "environment": {
                "type": "docker",
                "delete": True,
                "cpu_enforcement_policy": "limit",
                "memory_enforcement_policy": "limit",
                "override_cpus": 4,
                "override_memory_mb": 4096,
            },
            "agents": [
                {
                    "import_path": "adapters.hermes.adapter:HermesAgent",
                    "model_name": model,
                    "override_setup_timeout_sec": 1200,
                    "kwargs": {
                        "version": lock.hermes.source_tag,
                        "source_commit": lock.hermes.source_commit,
                        "install_branch": lock.hermes.install_branch,
                    },
                }
            ],
        }
    )
    result = await (await Job.create(JobConfig.model_validate(raw))).run()
    trial = result.trial_results[0]
    assert trial.exception_info is None
    assert trial.agent_info.version == lock.hermes.source_tag
    trial_dir = next(
        result_path.parent
        for result_path in (task_root / "jobs").rglob("result.json")
        if (result_path.parent / "agent/hermes.txt").is_file()
    )
    assert _MARKER in (trial_dir / "agent/hermes.txt").read_text(encoding="utf-8")
    assert (trial_dir / "agent/hermes-session.jsonl").stat().st_size > 0
    assert (trial_dir / "agent/trajectory.json").stat().st_size > 0


def test_hermes_provider_smoke() -> None:
    asyncio.run(_run_provider_smoke())
