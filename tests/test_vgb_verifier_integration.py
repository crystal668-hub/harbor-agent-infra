from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from harbor import Job
from harbor.viewer import create_app
from test_task_materializer import _resources, _spec

from harbor_agent_infra.harbor.job_config import materialize_group_job_config
from harbor_agent_infra.harbor.task_materializer import materialize_vgb_tasks
from integrations.vgb.runtime import VgbRuntime

pytestmark = pytest.mark.integration


def test_docker_harbor_verifier_matches_official_vgb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not os.environ.get("VGB_PYTHON"):
        pytest.skip("VGB_PYTHON is required for official VGB Docker integration")
    monkeypatch.setenv("VGB_PYTHON", str(Path(os.environ["VGB_PYTHON"]).absolute()))
    spec = _spec(tmp_path)
    runtime = VgbRuntime.from_environment()
    tasks = materialize_vgb_tasks(
        runtime,
        spec,
        output_root=tmp_path / "run",
        image=f"{spec.image.reference}@{spec.image.digest}",
    )
    group = materialize_group_job_config(
        spec, spec.groups[1], _resources(), tasks=tasks, output_root=tmp_path / "run"
    )
    config = group.job_config.model_copy(deep=True)
    config.agents[0].import_path = "adapters.fake_agent:FakeAgent"
    config.agents[0].kwargs = {
        "openclaw_response": "FINAL ANSWER: CCOc1ccc2[nH]c(C(=O)N3CCCCC3)cc2c1"
    }
    config.agents[0].skills = []
    assert "VGB_PYTHON" not in config.agents[0].env
    assert "VGB_PYTHON" not in config.environment.env

    async def run():
        job = await Job.create(config)
        return await job.run()

    result = asyncio.run(run())
    trial = result.trial_results[0]
    assert trial.exception_info is None
    score = trial.verifier_result.rewards["vgb_score"]
    assert score > 0
    assert trial.verifier_result.rewards["reward"] == score
    trial_dir = Path(trial.trial_uri.removeprefix("file://"))
    artifact = json.loads((trial_dir / "verifier/vgb-evaluation.json").read_text())
    assert artifact["vgb_status"] == "scored"
    assert artifact["domain_result"]["scores"]["score"] == score
    viewer = TestClient(create_app(config.jobs_dir, mode="jobs"))
    task_summary = viewer.get(f"/api/jobs/{config.job_name}/tasks").json()["items"]
    assert task_summary[0]["avg_reward"] == score
