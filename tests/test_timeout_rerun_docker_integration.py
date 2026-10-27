"""Short native Docker gate; no providers or private scoring data."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from test_timeout_rerun_plan import timeout_fixture

from harbor_agent_infra.resume.io import read_object
from harbor_agent_infra.timeout_rerun import plan as planning
from harbor_agent_infra.timeout_rerun.execution import run_campaign

pytestmark = pytest.mark.integration


def test_short_timeout_native_persistence_and_idempotent_restart(tmp_path, monkeypatch):
    if os.environ.get("RUN_HAI_TIMEOUT_RERUN") != "1":
        pytest.skip("set RUN_HAI_TIMEOUT_RERUN=1 for the synthetic Docker gate")
    source = timeout_fixture(tmp_path)
    build = planning.target_job

    def synthetic_target(slot, root, lock):
        config = build(slot, root, lock)
        # Production budget is tested separately; exercise the same Harbor path in seconds.
        config["agents"] = [
            {
                "import_path": "adapters.fake_agent:FakeAgent",
                "override_timeout_sec": 0.5,
                "max_timeout_sec": 0.5,
                "kwargs": {"behavior": "sleep", "sleep_seconds": 10},
            }
        ]
        config["verifier"] = {"disable": True}
        config["environment"].update(override_cpus=1, override_memory_mb=512, delete=True)
        return config

    async def checked(*args):
        return None

    monkeypatch.setattr(planning, "target_job", synthetic_target)
    monkeypatch.setattr("harbor_agent_infra.timeout_rerun.execution.preflight", checked)
    plan = planning.create_plan([source], tmp_path / "campaign", Path("runtime-lock.json"))
    manifest = Path(plan["root"]) / "manifest.json"
    result = asyncio.run(run_campaign(manifest))
    assert result["complete"]
    entry = next(iter(result["slots"].values()))
    assert entry["status"] == "capability_zero" and len(entry["attempts"]) == 1
    trial = read_object(Path(entry["attempts"][0]["path"]))
    assert trial["exception_info"]["exception_type"] == "AgentTimeoutError"
    assert trial["config"]["agent"]["override_timeout_sec"] == 0.5
    assert asyncio.run(run_campaign(manifest))["slots"] == result["slots"]
    assert len(list(Path(plan["root"]).glob("jobs/*/timeout-dispatch.json"))) == 1
