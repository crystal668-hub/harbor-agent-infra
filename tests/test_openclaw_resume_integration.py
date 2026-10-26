from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest
from harbor import Job, JobConfig

from adapters.openclaw.adapter import OpenClawAgent
from adapters.vgb_verifier import VgbVerifier
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("outcome", ["resumed", "normal", "timeout", "reconnected"])
def test_real_gateway_resumes_parent_in_same_harbor_trial(tmp_path, monkeypatch, outcome):
    if os.environ.get("RUN_OPENCLAW_RESUME") != "1":
        pytest.skip("set RUN_OPENCLAW_RESUME=1 for the local Docker Gateway gate")
    lock = load_runtime_lock(Path(os.environ.get(
        "PREINSTALLED_RUNTIME_LOCK", "runtime-lock.json"
    )))
    pause = outcome != "normal"
    image = lock.execution_image("openclaw", "preinstalled")
    task = tmp_path / "fixture__resume"
    (task / "environment").mkdir(parents=True)
    (task / "tests").mkdir()
    (task / "tests/test.sh").write_text("#!/bin/sh\nexit 0\n")
    (task / "instruction.md").write_text("PARENT_WORK" if pause else "NO_PAUSE")
    (task / "task.toml").write_text(
        'schema_version = "1.4"\n[environment]\n'
        f'docker_image = "{image.immutable_reference}"\n[agent]\n'
        f'timeout_sec = {35 if outcome == "timeout" else 150}\n'
    )
    original = OpenClawAgent.install
    original_upload = OpenClawAgent._upload_config_text

    async def upload(self, environment, *, content, remote_path, filename):
        if outcome == "reconnected" and filename == "gateway_session.mjs":
            # Withhold the subscription during both native recovery rounds.
            content = content.replace(
                "this.paused = true;",
                'this.paused = true; process.emit("fixture-disconnect");',
            )
        if outcome == "reconnected" and filename == "gateway_driver.mjs":
            # Recreate only the SDK connection; the Gateway, parent and children
            # keep running. Use public SDK methods without exposing test hooks.
            content = content.replace("client = new GatewayClient({", "const options = {")
            content = content.replace(
                "});\n    client.start();",
                '};\n    process.once("fixture-disconnect", () => { client.stop(); '
                "setTimeout(() => {client = new GatewayClient(options); client.start();}, "
                "12000); });\n    client = new GatewayClient(options); client.start();",
            )
            content = content.replace(
                "session.run(client)",
                "session.run({request: (...args) => client.request(...args)})",
            )
        await original_upload(
            self, environment, content=content, remote_path=remote_path, filename=filename
        )

    async def install(self, environment):
        await original(self, environment)
        await environment.upload_file(
            Path("tests/fixtures/openclaw_model.py").resolve(), "/tmp/openclaw-model.py"
        )
        await environment.exec(
            command=(
                "nohup python3 /tmp/openclaw-model.py "
                + ("--pause-forever " if outcome == "timeout" else "")
                + "> /logs/agent/fixture-model.log "
                "2>&1 </dev/null &"
            )
        )

    calls = []

    class Runtime:
        def metadata(self):
            return {"tracks": ["fixture"]}

        def evaluate(self, track, answer):
            calls.append(answer)
            assert answer["response"] == "FINAL ANSWER: 42"
            return {"task_id": "resume", "status": "scored", "scores": {"score": 1.0}}

    monkeypatch.setattr(OpenClawAgent, "install", install)
    monkeypatch.setattr(OpenClawAgent, "_upload_config_text", upload)
    monkeypatch.setattr("adapters.vgb_verifier.VgbRuntime.from_environment", lambda: Runtime())
    monkeypatch.setattr("integrations.vgb.evaluator.validate_track", lambda *args: None)
    monkeypatch.setenv("QWEN_API_KEY", "fixture")
    monkeypatch.setenv("QWEN_BASE_URL", "http://127.0.0.1:18081/v1")
    verified = []
    original_verify = VgbVerifier.verify

    async def verify(self):
        state = json.loads((self.trial_paths.agent_dir / "openclaw-status.json").read_text())
        assert state["state"] == "completed"
        verified.append(state)
        return await original_verify(self)

    monkeypatch.setattr(VgbVerifier, "verify", verify)
    config = JobConfig.model_validate(
        {
            "job_name": "openclaw-resume-skills_off",
            "jobs_dir": str(tmp_path / "jobs"),
            "quiet": True,
            "n_attempts": 1,
            "n_concurrent_trials": 1,
            "retry": {"max_retries": 0},
            "environment": {
                "type": "docker",
                "delete": True,
                "override_cpus": 1,
                "override_memory_mb": 2048,
            },
            "agents": [
                {
                    "import_path": "adapters.openclaw.adapter:OpenClawAgent",
                    "model_name": "qwen/test",
                    "kwargs": {
                        "version": "2026.6.34",
                        "preinstalled": {
                            "manifest_sha256": image.manifest_sha256,
                            "image": image.immutable_reference,
                            "parent_image": lock.agent_base_image.immutable_reference,
                            "platform": image.platform,
                        },
                    },
                }
            ],
            "verifier": {"import_path": "adapters.vgb_verifier:VgbVerifier"},
            "tasks": [{"path": str(task)}],
        }
    )

    async def run():
        return await (await Job.create(config)).run()

    result = asyncio.run(run())
    trial = result.trial_results[0]
    agent_dir = Path(trial.trial_uri.removeprefix("file://")) / "agent"
    if outcome == "timeout":
        assert trial.exception_info.exception_type == "AgentTimeoutError"
        assert trial.verifier_result is None
        assert calls == verified == []
        state = json.loads((agent_dir / "openclaw-status.json").read_text())
        assert state["state"] == "interrupted"
        assert state["paused"] is True
        assert '"customType":"openclaw.sessions_yield"' in (
            agent_dir / "openclaw.session.jsonl"
        ).read_text()
        assert not (agent_dir / "openclaw-driver.pid").exists()
        assert not (agent_dir / "openclaw.txt").exists()
        return
    assert trial.exception_info is None, trial.exception_info
    assert len(calls) == len(verified) == 1
    assert trial.verifier_result.rewards["reward"] == 1.0
    events = [
        json.loads(line) for line in (agent_dir / "openclaw-turns.jsonl").read_text().splitlines()
    ]
    parent = next(e for e in events if e["kind"] == "lifecycle" and e["data"]["phase"] == "start")
    parent_starts = [
        e
        for e in events
        if e["kind"] == "lifecycle"
        and e.get("sessionKey") == parent["sessionKey"]
        and e["data"]["phase"] == "start"
    ]
    if outcome == "reconnected":
        assert any(e["kind"] == "reconnected" for e in events)
        assert any(e["kind"] == "completed" and e["reconciled"] for e in events)
    else:
        assert len(parent_starts) == (3 if pause else 1)
    assert {e["sessionId"] for e in parent_starts} == {parent["sessionId"]}
    transcript = [
        json.loads(line) for line in (agent_dir / "openclaw.session.jsonl").read_text().splitlines()
    ]
    messages = [row["message"] for row in transcript if row.get("type") == "message"]
    assert sum(
        "PARENT_WORK" in str(m.get("content")) for m in messages if m["role"] == "user"
    ) == int(pause)
    assert sum(row.get("customType") == "openclaw.sessions_yield" for row in transcript) == (
        2 if pause else 0
    )
    assert trial.agent_result.n_output_tokens == sum(
        m.get("usage", {}).get("output", 0) for m in messages if m["role"] == "assistant"
    )
