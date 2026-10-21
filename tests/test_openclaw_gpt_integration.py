"""Real pinned GPT Responses transport; no paid provider or private scoring data."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest
from harbor.models.trial.config import TrialConfig
from harbor.trial.trial import Trial

from adapters.openclaw.adapter import OpenClawAgent
from adapters.vgb_verifier import VgbVerifier
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("mode", ["normal", "noop", "encrypted", "exhausted", "schema",
                                  "paused", "compact"])
def test_native_gpt_two_fixes(tmp_path, monkeypatch, mode):
    if os.environ.get("RUN_OPENCLAW_GPT_FIXES") != "1":
        pytest.skip("set RUN_OPENCLAW_GPT_FIXES=1 and PREINSTALLED_RUNTIME_LOCK")
    lock = load_runtime_lock(Path(os.environ["PREINSTALLED_RUNTIME_LOCK"]))
    image = lock.execution_image("openclaw", "preinstalled")
    task = tmp_path / "fixture__gpt"
    (task / "environment").mkdir(parents=True)
    (task / "tests").mkdir()
    (task / "tests/test.sh").write_text("#!/bin/sh\nexit 0\n")
    (task / "instruction.md").write_text("PARENT_WORK")
    (task / "task.toml").write_text(
        'schema_version = "1.4"\n[environment]\n'
        f'docker_image = "{image.immutable_reference}"\n[agent]\ntimeout_sec = 150\n'
    )
    install_original = OpenClawAgent.install

    async def install(self, environment):
        await install_original(self, environment)
        for name in ["openclaw_responses_model.py", "openclaw_edit_contract.mjs",
                     "openclaw_encrypted_contract.mjs"]:
            await environment.upload_file((Path("tests/fixtures") / name).resolve(), "/tmp/" + name)
        result = await environment.exec(command=(
            '. ~/.nvm/nvm.sh && nvm use 22 >/dev/null && '
            'node /tmp/openclaw_edit_contract.mjs "$(npm root -g)/openclaw" '
            '> /logs/agent/fixture-edit-contract.json'
        ))
        assert result.return_code == 0, result.stderr
        result = await environment.exec(command=(
            '. ~/.nvm/nvm.sh && nvm use 22 >/dev/null && '
            'node /tmp/openclaw_encrypted_contract.mjs "$(npm root -g)/openclaw" '
            '> /logs/agent/fixture-encrypted-contract.json'
        ))
        assert result.return_code == 0, result.stderr
        await environment.exec(command=f"printf {mode} > /tmp/responses-mode")
        await environment.exec(command=(
            "nohup python3 /tmp/openclaw_responses_model.py > /logs/agent/fixture-model.log "
            "2>&1 </dev/null &"
        ))

    monkeypatch.setattr(OpenClawAgent, "install", install)
    monkeypatch.setenv("OPENAI_API_KEY", "fixture")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:18083/v1")
    scores = []
    verified = []

    class Runtime:
        def metadata(self):
            return {"tracks": ["fixture"]}

        def evaluate(self, track, answer):
            assert answer["response"] == "FINAL ANSWER: 42"
            scores.append(answer)
            return {"task_id": "gpt", "status": "scored", "scores": {"score": 1.0}}

    monkeypatch.setattr("adapters.vgb_verifier.VgbRuntime.from_environment", lambda: Runtime())
    monkeypatch.setattr("integrations.vgb.evaluator.validate_track", lambda *_: None)
    original_verify = VgbVerifier.verify

    async def verify(self):
        state = json.loads((self.trial_paths.agent_dir / "openclaw-status.json").read_text())
        verified.append(state["state"])
        return await original_verify(self)

    monkeypatch.setattr(VgbVerifier, "verify", verify)

    async def execute():
        trial = await Trial.create(TrialConfig.model_validate({
            "trial_name": "gptfix-skills_off-" + mode,
            "trials_dir": tmp_path / "trials", "task": {"path": task},
            "environment": {"type": "docker", "delete": True, "override_cpus": 1,
                            "override_memory_mb": 2048},
            "agent": {"import_path": "adapters.openclaw.adapter:OpenClawAgent",
                      "model_name": "openai/gpt-6.1-sol", "kwargs": {
                          "version": "2026.6.34", "thinking": "high",
                          "openclaw_config": {"models": {"providers": {"openai": {
                              "request": {"allowPrivateNetwork": True},
                              "models": [{"id": "gpt-6.1-sol", "name": "fixture",
                                          "contextWindow": 200000, "maxTokens": 4096}]
                          }}}},
                          "preinstalled": {
                              "manifest_sha256": image.manifest_sha256,
                              "image": image.immutable_reference,
                              "parent_image": lock.agent_base_image.immutable_reference,
                              "platform": image.platform}}},
            "verifier": {"import_path": "adapters.vgb_verifier:VgbVerifier"},
        }))
        pending = asyncio.create_task(trial.run())
        ready = trial.paths.agent_dir / "fixture-final-ready"
        released = False
        try:
            while not pending.done():
                if ready.exists() and not released:
                    assert not verified and not scores
                    state = json.loads(
                        (trial.paths.agent_dir / "openclaw-status.json").read_text()
                    )
                    assert state["state"] == "running"
                    await trial.agent_environment.exec(
                        command="touch /logs/agent/fixture-final-release"
                    )
                    released = True
                await asyncio.sleep(0.02)
            await pending
        finally:
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
        return trial

    trial = asyncio.run(execute())
    result = json.loads(trial.paths.result_path.read_text())
    agent = trial.paths.agent_dir
    assert json.loads((agent / "fixture-edit-contract.json").read_text())["cases"] == 6
    assert json.loads((agent / "fixture-encrypted-contract.json").read_text())["cases"] == 7
    records = [
        json.loads(line) for line in (agent / "fixture-responses.jsonl").read_text().splitlines()
    ]
    failures = [row for row in records if row["error"] == "encrypted"]
    if mode in {"exhausted", "schema"}:
        assert result["exception_info"]["exception_type"] == "OpenClawAgentIncompleteError"
        assert scores == verified == []
        assert result["verifier_result"] is None
    else:
        assert result["exception_info"] is None, result["exception_info"]
        assert len(scores) == 1 and verified == ["completed"]
        assert json.loads((agent / "harness-final.json").read_text())["status"] == "passed"
    assert len(failures) == (2 if mode == "exhausted" else int(mode in {
        "encrypted", "paused", "compact",
    }))
    for index, row in enumerate(records):
        if row["error"] != "encrypted" or (mode == "exhausted" and not row["encrypted"]):
            continue
        assert row["encrypted"]
        retry = records[index + 1]
        assert not retry["encrypted"]
        expected = json.loads(json.dumps(row["body"]))
        for item in expected["input"]:
            item.pop("encrypted_content", None)
        assert retry["body"] == expected
    if mode == "schema":
        assert len([row for row in records if row["error"]]) == 1
    elif mode == "normal":
        assert len(records) == 1
    transcript = [
        json.loads(line) for line in (agent / "openclaw.session.jsonl").read_text().splitlines()
    ]
    calls = [part for row in transcript for part in row.get("message", {}).get("content", [])
             if part.get("type") == "toolCall"]
    if mode != "normal":
        assert sum(call["name"] == "exec" for call in calls) == 1
        assert sum(call["name"] == "edit" for call in calls) == 1
    run = json.loads((agent / "openclaw-run.json").read_text())
    events = [
        json.loads(line) for line in (agent / "openclaw-turns.jsonl").read_text().splitlines()
    ]
    parent_events = [event for event in events if event["kind"] == "lifecycle"
                     and event.get("sessionKey", "").lower() == run["sessionKey"].lower()]
    assert parent_events and {event["sessionId"] for event in parent_events} == {run["sessionId"]}
    users = [row["message"] for row in transcript if row.get("message", {}).get("role") == "user"]
    assert sum(
        "".join(part.get("text", "") for part in message["content"]) == "PARENT_WORK"
        for message in users
    ) == 1
    if mode != "normal":
        assert any("No changes made to" in str(row.get("message", {}).get("content"))
                   for row in transcript if row.get("message", {}).get("role") == "toolResult")
    if mode == "paused":
        assert any(row.get("customType") == "openclaw.sessions_yield" for row in transcript)
    if mode == "compact":
        assert any(row.get("type") == "compaction" for row in transcript)
