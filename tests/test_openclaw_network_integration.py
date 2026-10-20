"""Real Harbor + pinned OpenClaw + Anthropic SSE, with DNS fault injection only."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import pytest
from harbor.models.trial.config import TrialConfig
from harbor.trial.trial import Trial

from adapters.openclaw.adapter import OpenClawAgent
from adapters.vgb_verifier import VgbVerifier
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock
from scripts.build_preinstalled_image import require_idle_docker

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "outcome", ["normal", "recovered", "exhausted", "paused", "cancel", "timeout", "stream"]
)
def test_native_anthropic_network_retry(tmp_path, monkeypatch, outcome):
    if os.environ.get("RUN_OPENCLAW_NETWORK") != "1":
        pytest.skip("set RUN_OPENCLAW_NETWORK=1 and PREINSTALLED_RUNTIME_LOCK")
    require_idle_docker()
    lock = load_runtime_lock(Path(os.environ["PREINSTALLED_RUNTIME_LOCK"]))
    image = lock.execution_image("openclaw", "preinstalled")
    task = tmp_path / "fixture__network"
    (task / "environment").mkdir(parents=True)
    (task / "tests").mkdir()
    (task / "tests/test.sh").write_text("#!/bin/sh\nexit 0\n")
    (task / "instruction.md").write_text("PARENT_WORK")
    (task / "task.toml").write_text(
        'schema_version = "1.4"\n[environment]\n'
        f'docker_image = "{image.immutable_reference}"\n[agent]\n'
        f'timeout_sec = {35 if outcome == "timeout" else 150}\n'
    )
    install_original = OpenClawAgent.install
    run_original = OpenClawAgent.run

    async def install(self, environment):
        await install_original(self, environment)
        for source, target in [("anthropic_retry_model.py", "/tmp/network-model.py"),
                               ("openclaw_dns_fault.mjs", "/tmp/network-dns.mjs")]:
            await environment.upload_file((Path("tests/fixtures") / source).resolve(), target)
        await environment.exec(command=f"printf {outcome} > /tmp/network-mode")
        await environment.exec(command=(
            "nohup python3 /tmp/network-model.py > /logs/agent/fixture-model.log "
            "2>&1 </dev/null &"
        ))

    async def run(self, instruction, environment, context):
        await environment.exec(command=f"printf {time.time()} > /tmp/agent-start")
        # Scoped to the test trial; inherited by its Gateway. Installed files stay intact.
        with environment.scoped_exec_env({"NODE_OPTIONS": "--import=/tmp/network-dns.mjs"}):
            return await run_original(self, instruction, environment, context)

    monkeypatch.setattr(OpenClawAgent, "install", install)
    monkeypatch.setattr(OpenClawAgent, "run", run)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://retry.fixture.test:18082")
    scores = []

    class Runtime:
        def metadata(self):
            return {"tracks": ["fixture"]}

        def evaluate(self, track, answer):
            assert answer["response"] == "FINAL ANSWER: 42"
            scores.append(answer)
            return {"task_id": "network", "status": "scored", "scores": {"score": 1.0}}

    monkeypatch.setattr("adapters.vgb_verifier.VgbRuntime.from_environment", lambda: Runtime())
    monkeypatch.setattr("integrations.vgb.evaluator.validate_track", lambda *_: None)
    original_verify = VgbVerifier.verify
    verified = []

    async def verify(self):
        state = json.loads((self.trial_paths.agent_dir / "openclaw-status.json").read_text())
        verified.append(state["state"])
        return await original_verify(self)

    monkeypatch.setattr(VgbVerifier, "verify", verify)

    async def execute():
        trial = await Trial.create(TrialConfig.model_validate({
            "trial_name": "network-skills_off-" + outcome,
            "trials_dir": tmp_path / "trials", "task": {"path": task},
            "environment": {"type": "docker", "delete": True, "override_cpus": 1,
                            "override_memory_mb": 2048},
            "agent": {"import_path": "adapters.openclaw.adapter:OpenClawAgent",
                      "model_name": "anthropic/claude-opus-5.5", "kwargs": {
                          "version": "2026.6.34", "preinstalled": {
                              "manifest_sha256": image.manifest_sha256,
                              "image": image.immutable_reference,
                              "parent_image": lock.agent_base_image.immutable_reference,
                              "platform": image.platform}}},
            "verifier": {"import_path": "adapters.vgb_verifier:VgbVerifier"},
        }))
        pending = asyncio.create_task(trial.run())
        log = trial.paths.agent_dir / "openclaw-gateway.log"
        try:
            # Observe a real retry wait: no scoring or Trial completion is allowed yet.
            if outcome not in {"normal", "stream"}:
                async with asyncio.timeout(120):
                    while not pending.done():
                        text = log.read_text() if log.exists() else ""
                        if '"event":"retry"' in text:
                            assert not scores and not verified
                            if outcome == "cancel":
                                pending.cancel()
                            break
                        await asyncio.sleep(0.05)
            if outcome == "cancel":
                with pytest.raises(asyncio.CancelledError):
                    await pending
            else:
                await pending
        finally:
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
        return trial

    trial = asyncio.run(execute())
    result = json.loads(trial.paths.result_path.read_text())
    agent_dir = trial.paths.agent_dir
    text = (agent_dir / "openclaw-gateway.log").read_text()
    retries = [json.loads(line.split("[provider-network-retry] ", 1)[1])
               for line in text.splitlines() if "[provider-network-retry] " in line]
    dns = [json.loads(line) for line in (agent_dir / "fixture-dns.jsonl").read_text().splitlines()]
    failed = [r for r in dns if r["failed"]]
    transcript = [json.loads(line) for line in
                  (agent_dir / "openclaw.session.jsonl").read_text().splitlines()]
    messages = [r["message"] for r in transcript if r.get("type") == "message"]
    tool_calls = [c for m in messages for c in m.get("content", []) if c.get("type") == "toolCall"]
    assert sum(c["name"] == "exec" for c in tool_calls) == 1
    assert sum("PARENT_WORK" in str(m["content"]) for m in messages if m["role"] == "user") == 1
    if outcome in {"recovered", "paused", "normal"}:
        assert result["exception_info"] is None, result["exception_info"]
        assert len(scores) == 1 and verified == ["completed"]
        assert result["verifier_result"]["rewards"]["reward"] == 1.0
        final = json.loads((agent_dir / "harness-final.json").read_text())
        assert final["status"] == "passed"
        assert len(failed) == (0 if outcome == "normal" else 2)
        expected_events = [] if outcome == "normal" else ["retry", "retry", "response"]
        assert [r["event"] for r in retries] == expected_events
        yields = sum(r.get("customType") == "openclaw.sessions_yield" for r in transcript)
        assert yields == int(outcome == "paused")
    else:
        expected = {"cancel": "CancelledError", "timeout": "AgentTimeoutError"}.get(
            outcome, "OpenClawAgentIncompleteError"
        )
        assert result["exception_info"]["exception_type"] == expected, result["exception_info"]
        assert result["verifier_result"] is None and scores == []
        assert verified == (["interrupted"] if outcome == "timeout" else [])
        assert not (agent_dir / "openclaw.txt").exists()
        if outcome == "exhausted":
            assert len(failed) == 4
            assert [r["event"] for r in retries] == ["retry", "retry", "retry", "exhausted"]
        elif outcome == "stream":
            assert not failed and not retries
            requests = (agent_dir / "fixture-requests.jsonl").read_text().splitlines()
            assert len(requests) == 2
        else:
            assert 1 <= len(failed) < 4
            assert all(r["event"] == "retry" for r in retries)
    if retries:
        assert len({r["request_id"] for r in retries}) == 1
        assert all(r["provider"] == "anthropic" and r["session_id"] for r in retries)
