"""Opt-in native Docker lifecycle gate; no provider or private VGB data."""
from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
from pathlib import Path

import pytest
from harbor import Job, JobConfig

from adapters.fake_agent import FakeAgent
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock
from harbor_agent_infra.resume.executor import resume_run
from harbor_agent_infra.resume.io import write_object
from harbor_agent_infra.resume.lifecycle import attach_checkpoints

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("with_answer", [False, True])
def test_resume_original_docker_job_after_cancellation(tmp_path, monkeypatch, with_answer):
    if os.environ.get("RUN_HAI_RESUME") != "1":
        pytest.skip("set RUN_HAI_RESUME=1 for the local synthetic Docker gate")
    image = load_runtime_lock(Path("runtime-lock.json")).execution_image(
        "openclaw", "preinstalled").immutable_reference
    subprocess.run(["docker", "image", "inspect", image], check=True, capture_output=True)
    root = tmp_path / "original"
    task = root / "tasks/fixture__one"
    (task / "environment").mkdir(parents=True)
    (task / "tests").mkdir()
    (task / "instruction.md").write_text("Synthetic final answer: 42")
    (task / "tests/test.sh").write_text("#!/bin/sh\nexit 0\n")
    (task / "task.toml").write_text(
        'schema_version = "1.4"\n[environment]\n' + f'docker_image = "{image}"\n')
    config = JobConfig(job_name="resume-skills_off", jobs_dir=root / "jobs", quiet=True,
        n_attempts=1, n_concurrent_trials=1, retry={"max_retries": 0},
        environment={"type": "docker", "delete": True,
                     "override_cpus": 1, "override_memory_mb": 512},
        agents=[{"import_path": "adapters.fake_agent:FakeAgent",
                 "kwargs": {"openclaw_response": "42"}}],
        verifier={"import_path": "adapters.vgb_verifier:VgbVerifier",
                  "env": {"VGB_AGENT_NAME": "openclaw"}}, tasks=[{"path": task}])
    write_object(root / "runtime-manifest.json", {
        "schema_version": "harbor-single-group-runtime-manifest.v1",
        "run_id": root.name, "status": "running", "selected_group": "skills_off",
        "launch_source": {"workspace": str(tmp_path)},
        "groups": [{"group_id": "skills_off", "agent_name": "openclaw",
                    "job_config": config.model_dump(mode="json")}],
    })
    calls, scores = [], []

    class Runtime:
        def metadata(self):
            return {"tracks": ["fixture"]}

        def evaluate(self, track, answer):
            scores.append(answer)
            assert answer["response"] == "42"
            return {"status": "scored", "task_id": "one", "scores": {"score": 0}}

    async def checked(context, plan):
        return {"skills_off": Runtime()}

    monkeypatch.setattr("harbor_agent_infra.resume.executor.preflight", checked)
    monkeypatch.setattr("adapters.vgb_verifier.VgbRuntime.from_environment", lambda: Runtime())
    monkeypatch.setattr("integrations.vgb.evaluator.validate_track", lambda *args: None)
    original_run = FakeAgent.run

    async def exercise():
        ready = asyncio.Event()

        async def run(self, instruction, environment, context):
            calls.append(str(self.context_id))
            if with_answer or len(calls) > 1:
                await original_run(self, instruction, environment, context)
                payload = json.dumps({"meta": {"finalAssistantVisibleText": "42",
                                              "stopReason": "stop"}})
                await environment.exec(command=
                    f"printf '%s' {shlex.quote(payload)} > /logs/agent/openclaw.txt")
            if len(calls) == 1:
                ready.set()
                await asyncio.Event().wait()

        monkeypatch.setattr(FakeAgent, "run", run)
        job = await Job.create(config)
        attach_checkpoints(job)
        running = asyncio.create_task(job.run())
        try:
            await asyncio.wait_for(ready.wait(), 90)
        finally:
            running.cancel()
            await asyncio.gather(running, return_exceptions=True)
        paths = list(job.job_dir.glob("*/result.json"))
        assert len(paths) == 1
        old_trial = paths[0].parent
        old = json.loads(paths[0].read_text())
        assert old["exception_info"]["exception_type"] == "CancelledError"
        result = await resume_run(str(root))
        assert result["complete"]
        native = json.loads((job.job_dir / "result.json").read_text())
        assert native["id"] == str(job.id)
        assert len(scores) == 1
        assert len(calls) == (1 if with_answer else 2)
        assert old_trial.exists() == with_answer
        rows = json.loads((root / "results.json").read_text())["results"]
        assert len(rows) == 1 and rows[0]["vgb_domain_result"]["scores"]["score"] == 0
        assert not (root / "resume").exists()

    asyncio.run(exercise())
